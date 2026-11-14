# FisIA (versión local en Python, con Gemini gratis)

Aplicación web que resuelve problemas de física con IA. Recibe el ejercicio como texto, imagen, PDF o audio, lo resuelve paso a paso, genera un reporte PDF y un programa Python con gráficas y animaciones.

La IA es **Google Gemini** con una clave gratuita de Google AI Studio: no necesita tarjeta de crédito.

## Qué hay en FisIA

Al abrir la página aparece un átomo animado: toca la pantalla para entrar al menú con tres secciones.

1. **Resolver un ejercicio**: texto, imagen, PDF o audio → resumen, paso a paso, simulación, gráficas, código Python ejecutable y reporte PDF.
2. **Corregir uno ya hecho**: subes tu resolución y FisIA marca qué pasos están bien, dónde está el error, cómo arreglarlo y una nota sugerida.
3. **Tutor IA holográfico**: profesor socrático con avatar holográfico. Te guía con preguntas, proyecta la fórmula clave en el "núcleo holográfico" y valida tu razonamiento. Si vienes de resolver o corregir un ejercicio, mantiene ese problema como contexto.

## Cómo evita errores de saturación de la API

- Máximo 8 peticiones por minuto y 2 respuestas a la vez hacia Gemini (cola de espera en lugar de ráfagas).
- Reintentos automáticos con espera creciente y respeto del tiempo que pide Google.
- Si el modelo principal está saturado o sin cupo, usa un modelo de respaldo (cada modelo tiene su propio cupo gratuito).
- Respuestas guardadas: repetir el mismo ejercicio no gasta cupo ni tokens (carpeta `cache/`, 7 días).
- Chat y tutor envían solo los últimos 10 turnos y tienen tope de tokens de salida más bajo.
- Las imágenes se reducen a 1600 px antes de enviarse.

Se puede ajustar con `FISIA_RPM`, `FISIA_CONCURRENTES`, `FISIA_REINTENTOS`, `FISIA_RESPALDO` y `FISIA_PENSAMIENTO` en `.env`.

## Por qué responde rápido

La resolución (resumen, pasos, gráfica y PDF) se pide primero sin el código Python, que es lo más largo; el código se genera después y aparece solo en la pestaña **Código Python**. El pensamiento interno de la IA está limitado y la ventana negra imprime cuánto tardó cada respuesta (`[FisIA] solve: modelo · primer texto Xs · total Ys`) y avisa si Gemini está ocupado y reintenta.

## Cómo funciona

```
Navegador (static/index.html)  ←→  Servidor Flask (app.py)  ←→  Google Gemini (ia.py)
        └→ jsPDF (reporte PDF) · pdf.js (leer PDF) · Canvas (vista previa animada)
```

- `app.py`: servidor Flask. Prepara las imágenes, envía la conversación a la IA, devuelve la respuesta por partes y transcribe audios.
- `ia.py`: única capa que habla con la IA. Para usar otro proveedor solo se reescriben las funciones `stream` y `transcribir`.
- `static/index.html`: la interfaz (entrada multimodal, resultados, simulación, editor de código, chat, reporte PDF).
- `static/shim.js`: conecta la interfaz con el servidor local.

## Requisitos

- Python 3.10 o superior.
- Conexión a internet (la interfaz carga jsPDF, pdf.js y las fuentes desde internet, y la IA es un servicio de Google).
- Una cuenta de Google para sacar la clave gratuita.

## Forma rápida: doble clic

1. Instala Python (paso 1 de abajo) y consigue tu clave de Gemini (paso 2).
2. Descomprime el `.zip`.
3. **Windows:** doble clic en `iniciar.bat`. **macOS:** doble clic en `iniciar.command` (la primera vez: clic derecho → Abrir). **Linux:** `./iniciar.command`.
4. La primera vez crea el entorno, instala todo y abre el Bloc de notas con el archivo `.env`: pega tu clave y guarda.
5. Se abre el navegador en http://127.0.0.1:5000. Esa ventana negra es el servidor: mientras esté abierta, la página funciona. Ciérrala (o pulsa `Ctrl + C`) para apagarlo.

Las siguientes veces solo hace falta el doble clic.

## Paso a paso (manual)

### 1. Instala Python
Descárgalo de https://www.python.org/downloads/. En Windows marca "Add Python to PATH". Comprueba en una terminal:

```
python --version
```

En macOS y Linux el comando puede ser `python3`.

### 2. Consigue tu clave gratuita de Gemini
1. Entra a https://aistudio.google.com/apikey e inicia sesión con tu cuenta de Google.
2. Pulsa **Create API key** (Crear clave de API) y cópiala.

No pide tarjeta. El plan gratuito tiene límites por minuto y por día (puedes ver los de tu cuenta en AI Studio, en la vista de límites de uso); los cupos diarios se renuevan a medianoche, hora del Pacífico. Para un trabajo universitario alcanza de sobra, pero evita lanzar muchas resoluciones seguidas.

**Privacidad:** en el plan gratuito, Google puede usar lo que envías para mejorar sus productos. No subas datos personales ni fotos de personas.

### 3. Abre una terminal en la carpeta del proyecto
Descomprime el `.zip` y entra a la carpeta:

```
cd fisia
```

### 4. Crea y activa un entorno virtual

```
python -m venv venv
venv\Scripts\activate           # Windows (PowerShell o CMD)
source venv/bin/activate        # macOS / Linux
```

Si PowerShell bloquea la activación, ejecuta una vez: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### 5. Instala las dependencias

```
pip install -r requirements.txt
```

### 6. Configura tu clave
Copia `.env.example` como `.env` y pega tu clave:

```
copy .env.example .env          # Windows
cp .env.example .env            # macOS / Linux
```

Abre `.env` con un editor y reemplaza `pega_aqui_tu_clave` por tu clave real.

### 7. Ejecuta

```
python app.py
```

Se abre el navegador en http://127.0.0.1:5000. Para detener el servidor pulsa `Ctrl + C` en la terminal.

### 8. Úsalo
1. Elige el formato de entrada: Texto, Imagen, PDF o Audio. El audio acepta MP3, WAV, OGG, FLAC o AAC de hasta 14 MB; Gemini lo transcribe y puedes corregir el texto antes de resolver.
2. Pulsa **Resolver con FisIA**. Verás el progreso mientras la IA analiza, resuelve y escribe el código.
3. Revisa las pestañas **Resumen**, **Paso a paso**, **Simulación**, **Código Python** y **Preguntas**.
4. Pulsa **Descargar reporte PDF** (puedes poner tu nombre y la asignatura en "Datos para la portada").
5. En **Código Python**, copia o descarga el programa y ejecútalo con `python archivo.py` para ver la animación completa.

## Abrirlo desde otro dispositivo o compartir un enlace

Por defecto la página solo se abre en tu computadora. **Quien abra el enlace usa el cupo de tu clave de Gemini**, así que compártelo solo durante la demostración.

- **Mismo wifi (celular, otra laptop, el salón):** en `.env` agrega `FISIA_HOST=0.0.0.0` y reinicia. La terminal mostrará una dirección como `http://192.168.1.25:5000`: ábrela desde el otro dispositivo. Si el firewall de Windows lo pregunta, permite el acceso en redes privadas.
- **Enlace por internet:** con el servidor encendido, usa un túnel como Cloudflare Tunnel (`cloudflared tunnel --url http://127.0.0.1:5000`) o ngrok (`ngrok http 5000`). Te dan un enlace público temporal. Ciérralo al terminar.

## Cómo entregarlo al profesor

- Entrega la carpeta como `.zip` **sin** `venv/` y **sin** `.env`. El archivo `.env` contiene tu clave personal: nunca lo compartas ni lo subas a internet.
- Incluye este README. Quien lo revise necesita su propia clave gratuita de Gemini (2 minutos) para resolver ejercicios nuevos.
- Sin clave, la interfaz abre igual: el ejemplo precargado permite ver el resumen, los pasos, la simulación animada, el código y descargar el PDF. Lo único que no funciona sin clave es resolver ejercicios nuevos.
- Para la defensa, prepara una demostración en vivo y una captura o video de un ejercicio resuelto, por si falla el internet o se agota el cupo gratuito.

## Problemas frecuentes

| Síntoma | Solución |
| --- | --- |
| `python` no se reconoce | Reinstala Python marcando "Add to PATH", o prueba `py` o `python3`. |
| `No module named flask` | No activaste el entorno virtual o falta `pip install -r requirements.txt`. |
| La página dice "La IA no está activa" | Falta la clave en `.env`, sigue el texto `pega_aqui_tu_clave` o el archivo no se llama exactamente `.env`. Reinicia el servidor después de editarlo. |
| "La clave de Gemini no es válida" | Copia la clave completa desde https://aistudio.google.com/apikey, sin espacios ni comillas. |
| "Llegaste al límite gratuito de Gemini" | Espera un minuto. Si persiste, el cupo diario se renueva a medianoche (hora del Pacífico). También puedes elegir el nivel "Rápida". |
| "Ninguno de los modelos de Gemini está disponible" | FisIA consulta a Google qué modelos tiene tu clave y elige el más nuevo automáticamente. Si sale este error, crea una clave nueva en https://aistudio.google.com/apikey y borra `FISIA_MODELO` del `.env` si lo habías puesto. Al iniciar, la ventana negra muestra los modelos que usará. |
| "Gemini no está disponible en tu región" | La clave gratuita no funciona en algunos países; prueba desde otra red o con otra cuenta. |
| "Gemini está saturado" | Es temporal; intenta de nuevo en unos segundos. |
| El puerto 5000 está ocupado | Agrega `PORT=5001` en `.env`. |
| No transcribe un audio | Usa MP3 o WAV de menos de 14 MB. |
| No lee un PDF | Prueba con el rango de páginas, o sube una foto del ejercicio. |

## Estructura

```
fisia/
├── app.py                 servidor Flask
├── ia.py                  conexión con Gemini (reintentos, respaldo, límite de tráfico)
├── iniciar.bat            inicio con doble clic (Windows)
├── iniciar.command        inicio con doble clic (macOS / Linux)
├── requirements.txt       dependencias
├── .env.example           plantilla de configuración
└── static/
    ├── index.html         interfaz
    ├── profe.jpg          avatar del tutor
    └── shim.js            puente interfaz ↔ servidor
```

Las resoluciones generadas por IA pueden contener errores: revisa los cálculos y las unidades antes de entregar un trabajo.
