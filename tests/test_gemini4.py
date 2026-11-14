"""Comprueba cómo se adapta la petición a Gemini 4 (thinkingLevel) y a modelos anteriores. Uso: python tests/test_gemini4.py"""
import os, sys
from pathlib import Path
os.environ["GEMINI_API_KEY"] = "k"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ia
base = {"generationConfig": {"maxOutputTokens": 1500, "thinkingConfig": {"thinkingBudget": 256}}}
g4 = ia._ajustar(base, "gemini-4-hydrogen", "tutor")["generationConfig"]
assert g4["thinkingConfig"] == {"thinkingLevel": ia.NIVEL} and g4["maxOutputTokens"] >= 32768, g4
arg = ia._ajustar(base, "gemini-4-argon", "solve")["generationConfig"]
assert arg["thinkingConfig"]["thinkingLevel"] in ("low", "medium", "high"), arg
g3 = ia._ajustar(base, "gemini-3.8-flash", "tutor")["generationConfig"]
assert g3["thinkingConfig"] == {"thinkingBudget": 256} and g3["maxOutputTokens"] == 1500, g3
assert base["generationConfig"]["maxOutputTokens"] == 1500  # no modifica el original
print("4 comprobaciones OK")
