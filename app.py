"""FisIA (versión local).

Servidor Flask que sirve la página y la conecta con Google Gemini
(resolver ejercicios, responder preguntas, leer imágenes y transcribir audio).

Uso:  python app.py
"""
import base64
import collections
import hashlib
import io
import json
import os
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")  # debe ir antes de importar ia

from flask import Flask, Response, jsonify, request, send_from_directory  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402

import ia  # noqa: E402

app = Flask(__name__, static_folder=str(BASE / "static"), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024

TIERS = {"quick", "default", "complex"}
KINDS = {"solve", "check", "chat", "tutor", "code"}
CACHEABLES = {"solve", "check", "code"}  # el chat y el tutor dependen de la conversación: no se guardan
MAX_TURNOS = 10  # en chat y tutor solo viajan los últimos turnos: menos tokens por consulta
MAX_SYSTEM = 24000
MAX_IMAGENES = 4
MAX_AUDIO = 14 * 1024 * 1024  # Gemini acepta ~20 MB por solicitud y base64 agranda un tercio
MIME_AUDIO = {
    ".mp3": "audio/mp3",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".m4a": "audio/aac",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
}


def error_json(code, message, status, retry_after=None):
    cuerpo = {"code": code, "message": message}
    if retry_after:
        cuerpo["retry_after"] = int(retry_after)
    return jsonify(cuerpo), status


class Cache:
    """Respuestas ya generadas (memoria + archivo). Repetir un ejercicio no gasta cupo ni tokens,
    y sirve para la defensa si falla el internet."""

    def __init__(self, ruta, maximo=40, vigencia=7 * 24 * 3600):
        self.ruta, self.maximo, self.vigencia = ruta, maximo, vigencia
        self.lock = threading.Lock()
        self.datos = collections.OrderedDict()
        try:
            crudo = json.loads(ruta.read_text(encoding="utf-8"))
            for k, v in crudo.items():
                if isinstance(v, dict) and isinstance(v.get("t"), str) and time.time() - v.get("ts", 0) < vigencia:
                    self.datos[k] = v
        except (OSError, ValueError):
            pass

    def get(self, clave):
        with self.lock:
            v = self.datos.get(clave)
            if v and time.time() - v["ts"] < self.vigencia:
                self.datos.move_to_end(clave)
                return v["t"]
        return None

    def put(self, clave, texto):
        with self.lock:
            self.datos[clave] = {"t": texto, "ts": time.time()}
            self.datos.move_to_end(clave)
            while len(self.datos) > self.maximo:
                self.datos.popitem(last=False)
            try:
                self.ruta.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(dir=str(self.ruta.parent), suffix=".tmp")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.datos, f, ensure_ascii=False)
                os.replace(tmp, self.ruta)
            except OSError:
                pass  # sin disco no pasa nada: queda en memoria


cache = Cache(Path(os.getenv("FISIA_CACHE", str(BASE / "cache"))) / "respuestas.json")


def clave_cache(mensajes, imagenes, tier, kind, system):
    h = hashlib.sha256()
    h.update(json.dumps([mensajes, tier, kind, system or ""], ensure_ascii=False, sort_keys=True).encode())
    for tipo, datos in imagenes:
        h.update(tipo.encode())
        h.update(hashlib.sha256(datos.encode()).digest())
    return h.hexdigest()


def validar_mensajes(raw):
    try:
        msgs = json.loads(raw)
    except (TypeError, ValueError):
        raise ia.ErrorIA("invalid_request", "Mensajes ilegibles.", 400)
    if not isinstance(msgs, list) or not msgs:
        raise ia.ErrorIA("invalid_request", "No hay mensajes.", 400)
    limpios, total = [], 0
    for m in msgs:
        if (
            not isinstance(m, dict)
            or m.get("role") not in ("user", "assistant")
            or not isinstance(m.get("content"), str)
            or not m["content"].strip()
        ):
            raise ia.ErrorIA("invalid_request", "Mensaje con formato inválido.", 400)
        total += len(m["content"])
        limpios.append({"role": m["role"], "content": m["content"]})
    if limpios[0]["role"] != "user" or limpios[-1]["role"] != "user":
        raise ia.ErrorIA("invalid_request", "La conversación debe empezar y terminar con un turno del usuario.", 400)
    if total > 262144:
        raise ia.ErrorIA("prompt_too_large", "El contenido es demasiado largo.", 413)
    return limpios


def recortar_turnos(mensajes, kind):
    """En chat y tutor se conservan solo los últimos turnos (el primero siempre debe ser del usuario)."""
    if kind not in ("chat", "tutor") or len(mensajes) <= MAX_TURNOS:
        return mensajes
    cola = mensajes[-MAX_TURNOS:]
    while cola and cola[0]["role"] != "user":
        cola = cola[1:]
    return cola or mensajes[-1:]


def preparar_imagen(datos):
    """Reduce y normaliza la imagen para enviarla más rápido y sin pasar el límite de tamaño."""
    try:
        img = Image.open(io.BytesIO(datos))
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((1600, 1600))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
    except Exception:  # noqa: BLE001
        raise ia.ErrorIA("image_rejected", "No pude leer la imagen. Usa JPG, PNG o WebP.", 400)
    return "image/jpeg", base64.b64encode(buf.getvalue()).decode()


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/estado")
def estado():
    return jsonify(ia=ia.disponible(), audio=ia.disponible())


@app.post("/api/sample")
def sample():
    try:
        mensajes = validar_mensajes(request.form.get("messages"))
        tier = request.form.get("tier", "default")
        if tier not in TIERS:
            tier = "default"
        kind = request.form.get("kind", "solve")
        if kind not in KINDS:
            kind = "solve"
        system = (request.form.get("system") or "").strip()[:MAX_SYSTEM] or None
        mensajes = recortar_turnos(mensajes, kind)
        archivos = request.files.getlist("images")
        if len(archivos) > MAX_IMAGENES:
            raise ia.ErrorIA("image_rejected", "Demasiadas imágenes.", 400)
        imagenes = [preparar_imagen(f.read()) for f in archivos]

        clave = clave_cache(mensajes, imagenes, tier, kind, system) if kind in CACHEABLES else None
        if clave:
            guardado = cache.get(clave)
            if guardado:
                def desde_cache():
                    for i in range(0, len(guardado), 1200):
                        yield guardado[i:i + 1200]
                return Response(
                    desde_cache(),
                    mimetype="text/plain; charset=utf-8",
                    headers={"Cache-Control": "no-cache", "X-FisIA-Cache": "hit"},
                )

        info = {}
        t0 = time.monotonic()
        it = ia.stream(mensajes, imagenes, tier, kind, system, info)
        try:
            primero = next(it)
        except StopIteration:
            raise ia.ErrorIA("empty_completion", "La IA no devolvió texto.", 502)
    except ia.ErrorIA as e:
        return error_json(e.code, e.message, e.status, e.retry_after)

    def generar():
        partes = [primero]
        t1 = time.monotonic() - t0
        yield primero
        try:
            for trozo in it:
                partes.append(trozo)
                yield trozo
        except ia.ErrorIA as e:
            # Un error a mitad de la respuesta viaja dentro del flujo, tras un separador.
            yield "\x1e" + json.dumps({"code": e.code, "message": e.message, "retry_after": e.retry_after})
            return
        print(f"  [FisIA] {kind}: {info.get('modelo', '?')} · primer texto {t1:.1f}s · total {time.monotonic() - t0:.1f}s · {sum(map(len, partes))} caracteres", flush=True)
        if clave and info.get("fin") == "STOP":
            cache.put(clave, "".join(partes))  # solo respuestas completas

    return Response(
        generar(),
        mimetype="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/transcribir")
def transcribir():
    f = request.files.get("audio")
    if not f:
        return error_json("invalid_request", "No llegó ningún audio.", 400)
    ext = Path(f.filename or "").suffix.lower()
    mime = MIME_AUDIO.get(ext)
    if not mime:
        return error_json("invalid_request", "Formato de audio no compatible. Usa MP3, WAV, OGG, FLAC o AAC.", 400)
    datos = f.read()
    if len(datos) > MAX_AUDIO:
        return error_json("prompt_too_large", "El audio es demasiado grande (máximo 14 MB). Recórtalo o comprímelo.", 413)
    try:
        return jsonify(texto=ia.transcribir(datos, mime))
    except ia.ErrorIA as e:
        return error_json(e.code, e.message, e.status, e.retry_after)


if __name__ == "__main__":
    puerto = int(os.getenv("PORT", "5000"))
    # 127.0.0.1: solo tu computadora. 0.0.0.0: también otros equipos de tu red (ver README).
    host = os.getenv("FISIA_HOST", "127.0.0.1")
    url = f"http://127.0.0.1:{puerto}"
    print(f"\n  FisIA listo en {url}")
    if host == "0.0.0.0":
        try:
            import socket

            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            print(f"  Desde otro equipo de tu red: http://{s.getsockname()[0]}:{puerto}")
            s.close()
        except OSError:
            print("  No pude detectar la IP de tu red; búscala con ipconfig (Windows) o ifconfig (macOS/Linux).")
        print("  ATENCIÓN: quien abra ese enlace gasta el cupo de tu clave de Gemini.")
    print("  (Ctrl+C para detenerlo)\n")
    if not ia.disponible():
        print("  AVISO: falta GEMINI_API_KEY. Copia .env.example como .env y pega tu clave.\n")
    if ia.disponible():
        def _modelos():
            cadena = ia.cadena_modelos("default")
            print(f"  Modelos que usará FisIA (en este orden): {', '.join(cadena) if cadena else 'ninguno'}\n")
        threading.Thread(target=_modelos, daemon=True).start()
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=puerto, debug=False, threaded=True)
