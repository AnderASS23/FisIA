#!/bin/bash
# FisIA: inicio con doble clic (macOS) o con ./iniciar.command (Linux).
# La primera vez crea el entorno e instala todo; después solo enciende el servidor.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "No encontré Python 3. Instálalo desde https://www.python.org/downloads/"
  read -r -p "Pulsa Enter para cerrar..." _
  exit 1
fi

if [ ! -d venv ]; then
  echo "Creando el entorno virtual, un momento..."
  python3 -m venv venv || { echo "No pude crear el entorno virtual."; read -r -p "Pulsa Enter para cerrar..." _; exit 1; }
fi
# shellcheck disable=SC1091
source venv/bin/activate

if ! python -c "import flask, dotenv, PIL" >/dev/null 2>&1; then
  echo "Instalando dependencias, solo la primera vez..."
  python -m pip install -r requirements.txt || { echo "Falló la instalación. Revisa tu conexión a internet."; read -r -p "Pulsa Enter para cerrar..." _; exit 1; }
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Se creó el archivo .env. Pega tu clave de la API donde dice pega_aqui_tu_clave y guarda."
  (open -e .env 2>/dev/null || "${EDITOR:-nano}" .env)
  read -r -p "Cuando hayas guardado la clave, pulsa Enter para continuar..." _
fi
if grep -q "pega_aqui_tu_clave" .env; then
  echo "Falta pegar tu clave de la API en .env. Puedes abrir la página igual, pero no resolverá ejercicios nuevos."
  echo
fi

python app.py
read -r -p "Pulsa Enter para cerrar..." _
