# Arquitectura

```
Navegador (static/index.html + shim.js)
        │  POST /api/sample  (texto en streaming)
        │  POST /api/transcribir
        │  GET  /api/estado
        ▼
Servidor Flask (app.py)
  · valida la entrada, reduce imágenes (Pillow, máx. 1600 px)
  · caché en disco (cache/, 7 días)
        ▼
Capa de IA (ia.py)
  · límite de tráfico (RPM + concurrencia)
  · reintentos con espera, modelo de respaldo
  · descubre los modelos de la clave (ListModels)
        ▼
Google Gemini (API REST, streamGenerateContent)
```

## Archivos

| Archivo | Función |
| --- | --- |
| `app.py` | Rutas de Flask, validación, caché, inicio del servidor (`PORT`, `FISIA_HOST`). |
| `ia.py` | Única capa que habla con Gemini: `stream`, `transcribir`, `modelos_disponibles`, `cadena_modelos`, limitador. Para cambiar de proveedor solo hay que reescribir esta capa. |
| `static/index.html` | Toda la interfaz: portada, menú, resolver, corregir, tutor, simulación en canvas, editor de código, reporte PDF. |
| `static/shim.js` | Puente entre la interfaz y el servidor (`window.claude.use('sample')`). |
| `static/profe.jpg` | Avatar del tutor. |
| `tests/` | Pruebas contra un Gemini simulado (`fake_gemini.py`). |

## Flujo de «Resolver»

1. La página arma el prompt (`REGLAS_SOLO_JSON`) y lo envía con las imágenes, si hay.
2. El servidor responde en streaming; la página lee el JSON (tema, datos, pasos, resultado, vista previa).
3. Se renderiza resumen, pasos y simulación; el reporte PDF se arma en el navegador con jsPDF.
4. En segundo plano se pide el código Python (`kind: code`) y aparece en su pestaña.

## Control de la API gratuita

- Límite de peticiones por minuto y de respuestas simultáneas.
- Ante 429/503: espera creciente, respeto de `retryAfter`, luego modelo de respaldo.
- Caché por contenido: repetir un ejercicio no gasta cupo.
- Historial recortado a 10 turnos y topes de tokens por tipo de petición.

## Variables de entorno

Ver `.env.example`: `GEMINI_API_KEY`, `FISIA_MODELO`, `FISIA_MODELO_RAPIDO`, `PORT`, `FISIA_HOST`, `FISIA_RPM`, `FISIA_CONCURRENTES`, `FISIA_REINTENTOS`, `FISIA_RESPALDO`, `FISIA_MODELO_PROFUNDO`, `FISIA_NIVEL`, `FISIA_TIMEOUT`.

## Modelos
Por defecto se usa Gemini 4 Hydrogen, con respaldo en `gemini-3.8-flash`. Gemini 4 no admite `thinkingBudget`: `ia._ajustar` envía `thinkingLevel` (`FISIA_NIVEL`, por defecto `low`) y sube `maxOutputTokens` a 32768 como mínimo. Los modelos que la clave realmente tiene se descubren con ListModels, así que un nombre retirado no rompe la app.
