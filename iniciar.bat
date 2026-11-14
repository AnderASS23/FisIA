@echo off
rem FisIA: inicio con doble clic (Windows).
rem La primera vez crea el entorno e instala todo; después solo enciende el servidor.
cd /d "%~dp0"
chcp 65001 >nul

set PY=python
where python >nul 2>nul || set PY=py
where %PY% >nul 2>nul
if errorlevel 1 (
  echo No encontre Python. Instalalo desde https://www.python.org/downloads/ y marca "Add Python to PATH".
  pause
  exit /b 1
)

if not exist venv (
  echo Creando el entorno virtual, un momento...
  %PY% -m venv venv
  if errorlevel 1 (
    echo No pude crear el entorno virtual.
    pause
    exit /b 1
  )
)
call venv\Scripts\activate.bat

python -c "import flask, dotenv, PIL" >nul 2>nul
if errorlevel 1 (
  echo Instalando dependencias, solo la primera vez...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Fallo la instalacion. Revisa tu conexion a internet.
    pause
    exit /b 1
  )
)

if not exist .env (
  copy .env.example .env >nul
  echo Se creo el archivo .env. Pega tu clave de la API donde dice pega_aqui_tu_clave, guarda y cierra el Bloc de notas.
  notepad .env
)
findstr /c:"pega_aqui_tu_clave" .env >nul 2>nul
if not errorlevel 1 (
  echo Falta pegar tu clave de la API en el archivo .env. Puedes abrir la pagina igual, pero no resolvera ejercicios nuevos.
  echo.
)

python app.py
pause
