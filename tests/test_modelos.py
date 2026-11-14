"""Pruebas del servidor contra un Gemini simulado (sin internet ni clave real). Uso: python tests/test_modelos.py"""
import os,sys,tempfile,json,re,threading
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import fake_gemini as fg
from http.server import ThreadingHTTPServer
DISP=["gemini-2.5-flash","gemini-3.9-flash","gemini-3.8-flash-preview","gemini-3.9-flash-lite","gemini-3.9-flash-tts","gemini-3.9-flash-image","gemini-flash-latest","text-embedding-1"]
MALOS={"gemini-2.5-flash","gemini-3.8-flash","gemini-3.5-flash-lite"}  # 404 en estos
class H(fg.H):
    def do_GET(self):
        ms=[{"name":"models/"+n,"supportedGenerationMethods":["embedContent" if "embedding" in n else "generateContent"]} for n in DISP]
        b=json.dumps({"models":ms}).encode();self.send_response(200);self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_POST(self):
        m=re.match(r"/v1beta/models/([^:]+)",self.path).group(1)
        if m in MALOS or m not in DISP:
            b=json.dumps({"error":{"code":404,"message":"not found"}}).encode();self.send_response(404);self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b);return
        super().do_POST()
srv=ThreadingHTTPServer(("127.0.0.1",0),H);threading.Thread(target=srv.serve_forever,daemon=True).start()
os.environ.update({"FISIA_GEMINI_URL":f"http://127.0.0.1:{srv.server_address[1]}/v1beta","GEMINI_API_KEY":"k","FISIA_RPM":"200","FISIA_CACHE":tempfile.mkdtemp()})
for k in("http_proxy","HTTP_PROXY","https_proxy","HTTPS_PROXY"):os.environ.pop(k,None)
os.environ["NO_PROXY"]="127.0.0.1"
sys.path.insert(0,str(HERE.parent)); import app,ia
n=0
def ok(c,m):
    global n;assert c,"FALLO "+m;n+=1
print(ia.cadena_modelos("default"));print(ia.cadena_modelos("quick"))
ok(ia.cadena_modelos("default")[0]=="gemini-3.9-flash" and "gemini-2.5-flash" not in ia.cadena_modelos("default")[:1],"default elige el más nuevo")
ok(ia.cadena_modelos("quick")[0]=="gemini-3.9-flash-lite","quick elige lite")
ok(not any(x in m for m in ia.cadena_modelos("default") for x in("tts","image","embedding")),"excluye tts/imagen")
c=app.app.test_client()
r=c.post("/api/sample",data={"messages":json.dumps([{"role":"user","content":"ENTRADA DEL ESTUDIANTE x"}]),"kind":"solve"},content_type="multipart/form-data")
ok(r.status_code==200 and "<<<JSON" in r.get_data(as_text=True),"resuelve aunque los modelos configurados no existan")
ok(fg.LOG[-1]["modelo"]=="gemini-3.9-flash","usó el modelo descubierto")
# el último en la lista cuando todo falla
DISP[:]=["gemini-4-argon"]; ia._disp["lista"]=None
r=c.post("/api/sample",data={"messages":json.dumps([{"role":"user","content":"ENTRADA DEL ESTUDIANTE y"}]),"kind":"solve"},content_type="multipart/form-data")
ok(r.status_code==502 and "modelos" in r.get_json()["message"],"error claro si no hay ninguno")
h=c.get("/").get_data(as_text=True);ok("<title>FisIA</title>" in h and "sIA</h1>" in h,"nombre FisIA")
print(n,"OK")
