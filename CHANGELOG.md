# Registro de cambios

## 1.1.0 — 2026-11
- Soporte de Gemini 4 (Hydrogen por defecto, Argon para el nivel complejo): usa `thinkingLevel` en lugar de `thinkingBudget` y un tope de tokens mayor, porque el pensamiento cuenta dentro del tope.
- Ajustes nuevos: `FISIA_NIVEL`, `FISIA_TIMEOUT`, `FISIA_MODELO_PROFUNDO`, `FISIA_RESPALDO_PROFUNDO`.
- Si un modelo no está permitido para la clave (403), pasa al siguiente en vez de fallar.

## 1.0.0 — 2026-11
- Interfaz nueva: portada con átomo animado, menú de tres secciones.
- Secciones: resolver ejercicio, corregir uno ya hecho, tutor IA socrático con avatar holográfico.
- Gemini gratuito vía API REST; transcripción de audio con Gemini.
- Selección automática de modelo según los que tenga la clave.
- Control de tráfico: 8 peticiones/min, 2 simultáneas, reintentos con espera, modelo de respaldo, caché de 7 días.
- Resolución rápida: el código Python se genera en una segunda petición.
- Nombre del proyecto: FisIA.
