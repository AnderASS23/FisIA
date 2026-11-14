"""Gemini simulado para probar la interfaz sin red."""
import json, re, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

SOLVE = {"valido": True, "mensaje": "", "tema": "Cinemática", "subtema": "MRU", "tipo": "Movimiento uniforme", "nivel": "Básico",
 "enunciado": "Un auto viaja a 20 m/s durante 5 s. ¿Qué distancia recorre?",
 "datos": [{"simbolo": "v", "valor": "20 m/s", "descripcion": "rapidez"}, {"simbolo": "t", "valor": "5 s", "descripcion": "tiempo"}],
 "incognitas": [{"simbolo": "d", "descripcion": "distancia"}], "leyes": [{"nombre": "MRU", "formula": "d = v·t"}],
 "pasos": [{"titulo": "Aplicar MRU", "explicacion": "La rapidez es constante.", "calculo": "d = 20 · 5 = 100 m"}],
 "resultado": "d = 100 m", "verificacion": "Unidades coherentes.",
 "vista_previa": {"titulo": "x(t)", "t_min": 0, "t_max": 5, "eje_x": "t (s)", "eje_y": "x (m)", "curvas": [{"nombre": "x", "x": "t", "y": "20*t"}]}}
CHECK = {"valido": True, "mensaje": "", "tema": "Cinemática", "subtema": "MRU", "enunciado": "Un auto viaja a 20 m/s durante 5 s.",
 "veredicto": "Con errores", "nota": 6.5, "resumen": "Planteaste bien la fórmula pero te equivocaste en el cálculo.",
 "revision": [{"paso": "Elegir la fórmula", "estado": "ok", "comentario": "d = v·t es correcta.", "correccion": ""},
              {"paso": "Sustituir", "estado": "error", "comentario": "Usaste 4 s en lugar de 5 s.", "correccion": "d = 20 · 5 = 100 m"},
              {"paso": "Unidades", "estado": "aviso", "comentario": "Faltó escribir m.", "correccion": ""}],
 "errores": [{"tipo": "Cálculo", "descripcion": "Dato de tiempo mal copiado."}],
 "resultado_estudiante": "80 m", "resultado_correcto": "100 m", "consejos": ["Subraya los datos del enunciado."]}
TUTOR = "Buena pregunta. Piensa en **qué fuerzas** actúan. Si el cuerpo no acelera, $\\sum F = 0$.\n\n[[ \\sum \\vec{F} = m\\vec{a} ]]\n\n¿Qué fuerzas actúan sobre el bloque?"
LOG = []
MODO = {"fallo": None}

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n))
        u = urlparse(self.path); modelo, metodo = re.match(r"/v1beta/models/([^:]+):(\w+)", u.path).groups()
        LOG.append({"modelo": modelo, "metodo": metodo, "body": body})
        if MODO["fallo"] and modelo == MODO["fallo"][0]:
            code = MODO["fallo"][1]; cuerpo = json.dumps({"error": {"code": code, "message": "x", "status": "X"}}).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(cuerpo))); self.end_headers(); self.wfile.write(cuerpo); return
        if metodo == "generateContent":
            cuerpo = json.dumps({"candidates": [{"content": {"parts": [{"text": "Un auto viaja a 20 m/s."}]}}]}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(cuerpo))); self.end_headers(); self.wfile.write(cuerpo); return
        prompt = json.dumps(body["contents"], ensure_ascii=False)
        if "systemInstruction" in body: texto = TUTOR
        elif "YA RESUELTO" in prompt: texto = "<<<JSON\n" + json.dumps(CHECK, ensure_ascii=False) + "\nJSON>>>"
        elif "Escribe el programa" in prompt: texto = "```python\nimport numpy as np\nprint('hola')\n```"
        elif "ENTRADA DEL ESTUDIANTE" in prompt: texto = "<<<JSON\n" + json.dumps(SOLVE, ensure_ascii=False) + "\nJSON>>>"
        else: texto = "Claro: la distancia es $d=vt$ = 100 m."
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        trozos = [texto[i:i + 40] for i in range(0, len(texto), 40)]
        for k, t in enumerate(trozos):
            ev = {"candidates": [{"content": {"role": "model", "parts": [{"text": t}]}}]}
            if k == len(trozos) - 1: ev["candidates"][0]["finishReason"] = "STOP"
            self.wfile.write(b"data: " + json.dumps(ev).encode() + b"\r\n\r\n"); self.wfile.flush(); time.sleep(0.03)

def start(port=0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H); threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv
if __name__ == "__main__":
    s = start(int(sys.argv[1]) if len(sys.argv) > 1 else 8765); print("fake gemini on", s.server_address[1], flush=True)
    while True: time.sleep(3600)
