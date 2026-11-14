"""Pruebas del servidor contra un Gemini simulado (sin internet ni clave real). Uso: python tests/test_servidor.py"""
import os,sys,tempfile,io,json,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import fake_gemini as fg
srv=fg.start(0)
os.environ.update({"FISIA_GEMINI_URL":f"http://127.0.0.1:{srv.server_address[1]}/v1beta","GEMINI_API_KEY":"k","FISIA_MODELO":"m-ok","FISIA_RESPALDO":"m-bk","FISIA_MODELO_RAPIDO":"m-f","FISIA_RESPALDO_RAPIDO":"","FISIA_RPM":"200","FISIA_CACHE":tempfile.mkdtemp()})
for k in("http_proxy","HTTP_PROXY","https_proxy","HTTPS_PROXY"):os.environ.pop(k,None)
os.environ["NO_PROXY"]="127.0.0.1"
sys.path.insert(0,str(HERE.parent)); import app,ia
ia.REINTENTOS=1
c=app.app.test_client()
def post(msgs,kind="solve",**kw):
    d={"messages":json.dumps(msgs),"kind":kind};d.update(kw);return c.post("/api/sample",data=d,content_type="multipart/form-data")
U=[{"role":"user","content":"ENTRADA DEL ESTUDIANTE hola"}]
n=0
def ok(c_,m):
    global n;assert c_,"FALLO "+m;n+=1
r=post(U);ok(r.status_code==200 and "<<<JSON" in r.get_data(as_text=True),"solve")
antes=len(fg.LOG);r=post(U);ok(r.headers.get("X-Fisia-Cache")=="hit" and len(fg.LOG)==antes,"cache sin gastar peticion")
# respaldo cuando principal da 503
fg.MODO["fallo"]=("m-ok",503);U2=[{"role":"user","content":"ENTRADA DEL ESTUDIANTE otro"}]
t=time.time();r=post(U2);ok(r.status_code==200 and fg.LOG[-1]["modelo"]=="m-bk","respaldo tras 503");fg.MODO["fallo"]=None
# 429 en ambos -> error limpio
fg.MODO["fallo"]=("m-ok",429);ia.RESPALDOS["default"]="";U3=[{"role":"user","content":"ENTRADA DEL ESTUDIANTE tres"}]
ia.time.sleep=lambda s:None
r=post(U3);ok(r.status_code==429 and r.get_json()["code"]=="rate_limited","429 final");fg.MODO["fallo"]=None
# tutor: system, recorte de turnos
msgs=[{"role":"user" if i%2==0 else "assistant","content":f"m{i}"} for i in range(21)]
r=post(msgs,"tutor",system="Eres el Tutor IA");b=fg.LOG[-1]["body"]
ok("systemInstruction" in b and sum(len(x["parts"]) for x in b["contents"])<=11 and b["contents"][0]["role"]=="user","tutor recorta y system")
ok(b["generationConfig"]["maxOutputTokens"]==1500,"tope tokens tutor")
# limitador RPM
L=ia.Limitador(3,2);[L.turno() for _ in range(3)]
try: L.turno(espera_max=0.2);ok(False,"rpm")
except ia.ErrorIA as e: ok(e.code=="rate_limited","limitador rpm")
h=c.get("/").get_data(as_text=True);ok("<title>FisIA</title>" in h,"titulo");ok(c.get("/static/profe.jpg").status_code==200,"avatar")
print(n,"comprobaciones OK")
