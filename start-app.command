#!/bin/bash
# Trump Is The Best — double-click launcher (macOS).
# Double-click this file in Finder to start the platform. No commands needed.

cd "$(dirname "$0")" || exit 1

echo "======================================"
echo "        Trump Is The Best"
echo "======================================"

# First run: build the isolated environment and install libraries.
if [ ! -d ".venv" ]; then
  echo "Primera vez: preparando el entorno (puede tardar 1-2 minutos)..."
  python3 -m venv .venv || { echo "No se pudo crear el entorno."; read -r; exit 1; }
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt
fi

# Make sure the required libraries are present (e.g. after an update).
if ! ./.venv/bin/python -c "import flask, matplotlib, requests, dotenv" 2>/dev/null; then
  echo "Instalando/actualizando librerias..."
  ./.venv/bin/pip install --quiet -r requirements.txt
fi

echo ""
echo "Abriendo la plataforma en:  http://127.0.0.1:8502"
echo "(Para cerrarla, cierra esta ventana de Terminal.)"
echo ""

# Open the browser a moment after the server starts.
( sleep 2; open "http://127.0.0.1:8502" ) &

./.venv/bin/python server.py
