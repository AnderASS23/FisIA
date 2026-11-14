"""Capa de acceso a la IA de FisIA: Google Gemini (clave gratuita de AI Studio).

Incluye reintentos con espera creciente, modelo de respaldo y control de ráfagas
(ver `Limitador`) para no saturar la API gratuita.

Se usa la API REST con la biblioteca estándar de Python, así que no hace falta
instalar ningún SDK. Este es el ÚNICO archivo que habría que cambiar para usar
otro proveedor: basta con reescribir `stream` y `transcribir`.
"""
import base64
import collections
import http.client
import json
import os
import random
import re
import threading
import time
import urllib.error
import urllib.request

BASE = os.getenv("FISIA_GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")

# Modelos por nivel. Se pueden cambiar desde el archivo .env.
MODELOS = {
    "quick": os.getenv("FISIA_MODELO_RAPIDO", "gemini-4-hydrogen"),
    "default": os.getenv("FISIA_MODELO", "gemini-4-hydrogen"),
    # Argon es el modelo para tareas complejas, pero NO está en el nivel gratuito: si tu clave es
    # gratuita, falla y se pasa solo al respaldo (Hydrogen).
    "complex": os.getenv("FISIA_MODELO_PROFUNDO", "gemini-4-argon"),
}
# Si el modelo principal está saturado, sin cupo o no existe, se prueba con estos (cada modelo
# tiene su propio cupo gratuito). Déjalos vacíos en .env para desactivar el respaldo.
RESPALDOS = {
    "quick": os.getenv("FISIA_RESPALDO_RAPIDO", "gemini-3.5-flash-lite"),
    "default": os.getenv("FISIA_RESPALDO", "gemini-3.8-flash"),
    "complex": os.getenv("FISIA_RESPALDO_PROFUNDO", "gemini-4-hydrogen"),
}
# Tope de tokens de salida por tipo de petición: una pregunta de chat no necesita 16 000.
MAX_TOKENS = {
    "solve": int(os.getenv("FISIA_MAX_TOKENS", "6000")),
    "check": 5000,
    "chat": 1200,
    "tutor": 1500,
    "code": 6000,
}
# Presupuesto de "pensamiento" interno (tokens). Pensar de más gasta cupo sin mejorar chats cortos.
# Si el modelo no lo admite, se desactiva solo. FISIA_PENSAMIENTO=off lo apaga desde el inicio.
PENSAMIENTO = {"solve": 1024, "check": 1024, "chat": 0, "tutor": 256, "code": 0}
_pensar = os.getenv("FISIA_PENSAMIENTO", "on").strip().lower() not in ("off", "0", "no")
# Gemini 4 (Hydrogen y Argon) no admite thinkingBudget ni apagar el pensamiento: usa thinkingLevel
# (low, medium, high; xhigh solo Hydrogen). "low" equivale al pensamiento corto de antes y es lo
# más rápido; súbelo con FISIA_NIVEL=medium si quieres más razonamiento a cambio de velocidad.
NIVEL = os.getenv("FISIA_NIVEL", "low").strip().lower()
if NIVEL not in ("low", "medium", "high", "xhigh"):
    NIVEL = "low"
# En Gemini 4 el pensamiento cuenta dentro de maxOutputTokens: con topes bajos la respuesta se corta.
MIN_TOKENS_G4 = 32768

REINTENTOS = int(os.getenv("FISIA_REINTENTOS", "2"))   # reintentos por modelo, con espera creciente
PLAZO_APERTURA = 45                                    # segundos máximos para lograr que Gemini responda
RPM = int(os.getenv("FISIA_RPM", "8"))                 # peticiones por minuto que se envían a Gemini
CONCURRENTES = int(os.getenv("FISIA_CONCURRENTES", "2"))
TIMEOUT = int(os.getenv("FISIA_TIMEOUT", "180"))   # segundos sin recibir nada (Gemini 4 piensa antes de responder)
PROMPT_AUDIO = (
    "Transcribe literalmente este audio, que es el enunciado de un problema de física. "
    "Escribe los números, unidades y símbolos como se usarían en un texto (por ejemplo 25 m/s, 40°). "
    "Devuelve únicamente la transcripción, sin comentarios."
)


class ErrorIA(Exception):
    """Error con un código que la página sabe traducir a un mensaje claro."""

    def __init__(self, code, message, status=502, retry=False, retry_after=None, detalle=""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retry = retry              # ¿vale la pena reintentar con el mismo modelo?
        self.retry_after = retry_after  # segundos sugeridos por Gemini (o None)
        self.detalle = detalle          # texto original de Gemini (solo para decidir, no se muestra)


def _clave():
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()


def disponible():
    clave = _clave()
    return bool(clave) and "pega_aqui" not in clave


def construir_contenido(messages, images=()):
    """Convierte los turnos al formato de Gemini: junta turnos seguidos del mismo rol
    y pone las imágenes antes del texto del último turno."""
    fusion = []
    for m in messages:
        rol = "model" if m["role"] == "assistant" else "user"
        if fusion and fusion[-1]["role"] == rol:
            fusion[-1]["parts"][0]["text"] += "\n\n" + m["content"]
        else:
            fusion.append({"role": rol, "parts": [{"text": m["content"]}]})
    if images:
        bloques = [{"inline_data": {"mime_type": tipo, "data": datos}} for tipo, datos in images]
        fusion[-1]["parts"] = bloques + fusion[-1]["parts"]
    return fusion


def _retry_after(cabecera, cuerpo):
    """Segundos de espera que sugiere Gemini (cabecera Retry-After o campo retryDelay del cuerpo)."""
    try:
        if cabecera:
            return min(float(cabecera), 60.0)
    except ValueError:
        pass
    for d in (cuerpo.get("error") or {}).get("details") or []:
        v = d.get("retryDelay") if isinstance(d, dict) else None
        if isinstance(v, str) and v.endswith("s"):
            try:
                return min(float(v[:-1]), 60.0)
            except ValueError:
                pass
    return None


def traducir_http(status, mensaje, espera=None):
    bajo = (mensaje or "").lower()
    if status in (400, 401, 403) and ("api key" in bajo or "api_key" in bajo or status == 401):
        return ErrorIA("api_key", "La clave de Gemini no es válida. Revisa GEMINI_API_KEY en el archivo .env.", 401)
    if status == 403 and "location" in bajo:
        return ErrorIA("upstream_error", "Gemini no está disponible en tu región con esta clave.", 403)
    if status == 403:
        return ErrorIA("api_key", "Tu clave no tiene permiso para usar Gemini. Crea otra en aistudio.google.com/apikey.", 403)
    if status == 404:
        return ErrorIA("upstream_error", "Ninguno de los modelos de Gemini está disponible con tu clave. Crea una clave nueva en aistudio.google.com/apikey o borra FISIA_MODELO del archivo .env.", 502, detalle=mensaje or "")
    if status == 429:
        diario = "perday" in bajo.replace(" ", "").replace("_", "") or "per day" in bajo
        return ErrorIA(
            "rate_limited",
            "Llegaste al límite gratuito de Gemini. Espera un minuto; si sigue, el cupo diario se renueva a medianoche (hora del Pacífico).",
            429,
            retry=not diario,
            retry_after=espera,
            detalle=mensaje or "",
        )
    if status == 400:
        return ErrorIA("invalid_request", "Gemini rechazó la solicitud.", 400, detalle=mensaje or "")
    if status >= 500:
        return ErrorIA("upstream_error", "Gemini está saturado en este momento. Intenta de nuevo en unos segundos.", 502, retry=True, retry_after=espera)
    return ErrorIA("upstream_error", "Error al contactar a Gemini.", 502)


# ---------------------------------------------------------------------------
# Control de tráfico: evita ráfagas de peticiones y respeta el cupo gratuito.
# ---------------------------------------------------------------------------
class Limitador:
    """Máximo `rpm` peticiones por ventana de 60 s y `concurrentes` respuestas a la vez."""

    def __init__(self, rpm, concurrentes):
        self.rpm = max(1, rpm)
        self.sem = threading.BoundedSemaphore(max(1, concurrentes))
        self.marcas = collections.deque()
        self.lock = threading.Lock()

    def entrar(self, espera_max=45.0):
        if not self.sem.acquire(timeout=espera_max):
            raise ErrorIA("rate_limited", "Hay muchas consultas a la vez. Intenta de nuevo en unos segundos.", 429, retry_after=10)

    def salir(self):
        try:
            self.sem.release()
        except ValueError:
            pass

    def turno(self, espera_max=45.0):
        """Reserva un hueco para enviar una petición; espera si ya se enviaron `rpm` en el último minuto."""
        limite = time.monotonic() + espera_max
        while True:
            with self.lock:
                ahora = time.monotonic()
                while self.marcas and ahora - self.marcas[0] >= 60.0:
                    self.marcas.popleft()
                if len(self.marcas) < self.rpm:
                    self.marcas.append(ahora)
                    return
                falta = 60.0 - (ahora - self.marcas[0]) + 0.05
            if time.monotonic() + falta > limite:
                raise ErrorIA("rate_limited", "Muchas consultas seguidas. Espera unos segundos para no agotar tu cupo gratuito.", 429, retry_after=round(falta))
            time.sleep(min(falta, 1.0))


limitador = Limitador(RPM, CONCURRENTES)


def _solicitud(metodo, modelo, cuerpo, sse=False):
    limitador.turno()
    url = f"{BASE}/models/{modelo}:{metodo}?key={_clave()}" + ("&alt=sse" if sse else "")
    req = urllib.request.Request(
        url,
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        return urllib.request.urlopen(req, timeout=TIMEOUT)
    except urllib.error.HTTPError as e:
        try:
            crudo = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            crudo = {}
        mensaje = (crudo.get("error") or {}).get("message", "") if isinstance(crudo, dict) else ""
        espera = _retry_after(e.headers.get("Retry-After") if e.headers else None, crudo if isinstance(crudo, dict) else {})
        raise traducir_http(e.code, mensaje, espera) from None  # sin encadenar: la URL lleva la clave
    except (urllib.error.URLError, OSError):
        raise ErrorIA("upstream_error", "No hay conexión con Gemini. Revisa tu internet.", 502, retry=True) from None


_EXCLUIR = ("tts", "image", "live", "audio", "embedding", "robotics", "computer", "customtools", "dialog", "cyber", "omni", "transcribe")
_RE_MODELO = re.compile(r"^gemini-(\d+(?:\.\d+)?)-(flash-lite|flash|hydrogen|argon)(?:-(.*))?$")
_disp = {"lista": None, "ts": 0.0}


def modelos_disponibles(forzar=False):
    """Modelos de Gemini que ESTA clave puede usar (consulta ListModels y guarda el resultado 30 min).
    Devuelve una lista de nombres, o None si no se pudo consultar."""
    ahora = time.monotonic()
    if not forzar and _disp["lista"] is not None and ahora - _disp["ts"] < 1800:
        return _disp["lista"]
    nombres, token = [], ""
    try:
        for _ in range(5):
            url = f"{BASE}/models?pageSize=200&key={_clave()}" + (f"&pageToken={token}" if token else "")
            with urllib.request.urlopen(urllib.request.Request(url), timeout=20) as r:
                dato = json.loads(r.read().decode("utf-8", "replace"))
            for m in dato.get("models") or []:
                if "generateContent" in (m.get("supportedGenerationMethods") or []):
                    nombres.append(str(m.get("name", "")).split("/")[-1])
            token = dato.get("nextPageToken") or ""
            if not token:
                break
    except Exception:  # noqa: BLE001  (sin red, clave mala, etc.: se sigue con los nombres configurados)
        return _disp["lista"]
    if not nombres:
        return _disp["lista"]
    _disp["lista"], _disp["ts"] = nombres, ahora
    return nombres


def _clave_orden(nombre):
    m = _RE_MODELO.match(nombre)
    ver = tuple(int(x) for x in m.group(1).split("."))
    estable = 0 if not (m.group(3) or "") else 1  # sin sufijo (estable) antes que preview/exp
    return (-ver[0], -(ver[1] if len(ver) > 1 else 0), estable, nombre)


def _descubiertos(tier, disp):
    """Modelos Hydrogen / Flash / Flash-Lite (y Argon para el nivel complejo) de la lista de la clave,
    del más nuevo al más viejo."""
    util = [n for n in disp if _RE_MODELO.match(n) and not any(x in n for x in _EXCLUIR)]
    ligeros = sorted((n for n in util if _RE_MODELO.match(n).group(2) == "flash-lite"), key=_clave_orden)
    normales = sorted((n for n in util if _RE_MODELO.match(n).group(2) in ("flash", "hydrogen")), key=_clave_orden)
    profundos = sorted((n for n in util if _RE_MODELO.match(n).group(2) == "argon"), key=_clave_orden)
    if tier == "quick":
        orden = ligeros + normales
    elif tier == "complex":
        orden = profundos + normales + ligeros
    else:
        orden = normales + ligeros
    alias = [a for a in ("gemini-flash-lite-latest", "gemini-flash-latest") if a in disp]
    if tier != "quick":
        alias.reverse()
    return orden + alias


def cadena_modelos(tier):
    """Modelos a probar, en orden: el configurado, su respaldo y los que la clave realmente tiene.
    Si Google cambia o retira un nombre, FisIA sigue con otro modelo disponible en vez de fallar."""
    preferidos = [m for m in (MODELOS.get(tier, MODELOS["default"]), RESPALDOS.get(tier, RESPALDOS["default"])) if m]
    disp = modelos_disponibles()
    lista = []
    if disp is None:
        candidatos = preferidos
    else:
        principal, respaldo = preferidos[0], (preferidos[1] if len(preferidos) > 1 else None)
        candidatos = [m for m in (principal,) if m in disp] + _descubiertos(tier, disp) + [m for m in (respaldo,) if m in disp]
    for m in candidatos:
        if m not in lista:
            lista.append(m)
    return lista[:5] or preferidos


_refrescado = {"hecho": False}


def _abrir(metodo, tier, cuerpo, sse=False, info=None, kind="solve"):
    """Abre la conexión con Gemini con reintentos (espera creciente) y modelo de respaldo.

    Solo se reintenta ANTES de recibir el primer byte, así que nunca se duplica texto."""
    global _pensar
    plazo = time.monotonic() + PLAZO_APERTURA
    ultimo = None
    for modelo in cadena_modelos(tier):
        intento = 0
        while True:
            cuerpo_env = _ajustar(cuerpo, modelo, kind)
            try:
                resp = _solicitud(metodo, modelo, cuerpo_env, sse)
                if info is not None:
                    info["modelo"] = modelo
                return resp
            except ErrorIA as e:
                ultimo = e
                if e.code == "invalid_request" and "thinking" in e.detalle.lower() and _pensar and not _es_g4(modelo):
                    _pensar = False  # este modelo no admite límite de pensamiento: se apaga para todos
                    continue
                if e.code == "api_key" and e.status == 403:
                    break  # este modelo no está permitido para tu clave (ej. Argon sin plan de pago): probar otro
                if e.code == "api_key" or e.status in (400, 413) and e.code != "rate_limited":
                    raise
                if e.retry and intento < REINTENTOS:
                    espera = e.retry_after if e.retry_after else min(2 ** intento + random.random(), 8)
                    espera = min(espera, 20) + random.random() * 0.5
                    if time.monotonic() + espera < plazo:
                        print(f"  [FisIA] Gemini ocupado ({e.code}) con {modelo}: reintento en {espera:.0f}s", flush=True)
                        time.sleep(espera)
                        intento += 1
                        continue
                break  # sin más reintentos: probar el siguiente modelo
    if ultimo is not None and ultimo.status == 502 and "modelo" in ultimo.message and not _refrescado["hecho"]:
        _refrescado["hecho"] = True
        try:
            if modelos_disponibles(forzar=True):
                return _abrir(metodo, tier, cuerpo, sse, info, kind)
        finally:
            _refrescado["hecho"] = False
    raise ultimo or ErrorIA("upstream_error", "Error al contactar a Gemini.", 502)


def _es_g4(modelo):
    return modelo.startswith("gemini-4-")


def _ajustar(cuerpo, modelo, kind):
    """Devuelve una copia del cuerpo adaptada al modelo.
    - Modelos anteriores a Gemini 4: igual que siempre (thinkingBudget, apagable).
    - Gemini 4 (Hydrogen/Argon): thinkingLevel en vez de thinkingBudget y tope de tokens suficiente.
      Los parámetros de muestreo (temperature, topP...) ya no se envían: Gemini 4 los ignora."""
    cuerpo_env = json.loads(json.dumps(cuerpo))
    cfg = cuerpo_env.setdefault("generationConfig", {})
    if _es_g4(modelo):
        cfg.pop("thinkingConfig", None)
        nivel = NIVEL if _pensar else "low"
        if nivel == "xhigh" and "argon" in modelo:
            nivel = "high"  # Argon solo admite low, medium y high
        cfg["thinkingConfig"] = {"thinkingLevel": nivel}
        cfg["maxOutputTokens"] = max(int(cfg.get("maxOutputTokens", 0)), MIN_TOKENS_G4)
    elif not _pensar:
        cfg.pop("thinkingConfig", None)
    return cuerpo_env


def _config(kind):
    cfg = {"maxOutputTokens": MAX_TOKENS.get(kind, MAX_TOKENS["solve"])}
    if _pensar and kind in PENSAMIENTO:
        cfg["thinkingConfig"] = {"thinkingBudget": PENSAMIENTO[kind]}
    return cfg


def _textos(dato):
    """Texto visible de un fragmento de respuesta (omite los pensamientos internos)."""
    for cand in dato.get("candidates") or []:
        for parte in (cand.get("content") or {}).get("parts") or []:
            if parte.get("text") and not parte.get("thought"):
                yield parte["text"]


def _bloqueo(dato):
    razon = (dato.get("promptFeedback") or {}).get("blockReason")
    if razon:
        return razon
    for cand in dato.get("candidates") or []:
        if cand.get("finishReason") in ("SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "RECITATION"):
            return cand["finishReason"]
    return None


def stream(messages, images=(), tier="default", kind="solve", system=None, info=None):
    """Genera el texto de la respuesta por partes.

    `info` (dict opcional) recibe "modelo" y "fin" (motivo de fin; "STOP" = respuesta completa)."""
    if not disponible():
        raise ErrorIA("api_key", "Falta GEMINI_API_KEY. Copia .env.example como .env y pega tu clave.", 401)
    info = info if info is not None else {}
    cuerpo = {
        "contents": construir_contenido(messages, images),
        "generationConfig": _config(kind),
    }
    if system:
        cuerpo["systemInstruction"] = {"parts": [{"text": system}]}
    limitador.entrar()
    try:
        resp = _abrir("streamGenerateContent", tier, cuerpo, sse=True, info=info, kind=kind)
        emitio = False
        try:
            with resp:
                for linea in iter(resp.readline, b""):
                    texto = linea.decode("utf-8", "replace").strip()
                    if not texto.startswith("data:"):
                        continue
                    carga = texto[5:].strip()
                    if not carga or carga == "[DONE]":
                        continue
                    try:
                        dato = json.loads(carga)
                    except ValueError:
                        continue
                    for trozo in _textos(dato):
                        emitio = True
                        yield trozo
                    for cand in dato.get("candidates") or []:
                        if cand.get("finishReason"):
                            info["fin"] = cand["finishReason"]
                    if not emitio and _bloqueo(dato):
                        raise ErrorIA("refused", "Gemini no pudo procesar esta entrada. Reformula el enunciado o usa otra imagen.", 400)
        except ErrorIA:
            raise
        except (OSError, http.client.HTTPException):
            raise ErrorIA("upstream_error", "Se interrumpió la conexión con Gemini.", 502) from None
    finally:
        limitador.salir()


def transcribir(datos, mime):
    """Transcribe un audio con Gemini (acepta MP3, WAV, OGG, FLAC, AAC, AIFF)."""
    if not disponible():
        raise ErrorIA("api_key", "Falta GEMINI_API_KEY. Copia .env.example como .env y pega tu clave.", 401)
    cuerpo = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": PROMPT_AUDIO},
                {"inline_data": {"mime_type": mime, "data": base64.b64encode(datos).decode()}},
            ],
        }],
        "generationConfig": {"maxOutputTokens": 4000},
    }
    limitador.entrar()
    try:
        with _abrir("generateContent", "default", cuerpo, kind="audio") as resp:
            dato = json.loads(resp.read().decode("utf-8", "replace"))
    except (OSError, http.client.HTTPException, ValueError):
        raise ErrorIA("upstream_error", "Se interrumpió la conexión con Gemini.", 502) from None
    finally:
        limitador.salir()
    texto = "".join(_textos(dato)).strip()
    if not texto:
        if _bloqueo(dato):
            raise ErrorIA("refused", "Gemini no pudo procesar ese audio.", 400)
        raise ErrorIA("empty_completion", "No se detectó voz en el audio.", 422)
    return texto
