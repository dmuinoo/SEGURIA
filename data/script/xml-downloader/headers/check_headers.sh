#!/bin/bash
set -euo pipefail

ERROR=0

has_marker() {
  local file="$1"
  # Busca marcador en las primeras líneas (cabecera)
  head -n 30 "$file" | grep -qiE 'Proyecto:\s*ia|\*\*Proyecto:\*\*\s*ia'
}

# Comprueba solo ficheros staged; si no hay staged, comprueba todos
FILES=$(git diff --cached --name-only | grep -E '\.(py|js|ts|md)$' || true)

if [ -z "$FILES" ]; then
  FILES=$(git ls-files | grep -E '\.(py|js|ts|md)$' || true)
fi

for f in $FILES; do
  # Salta vendor/venv y binarios por seguridad
  case "$f" in
    .venv/*|venv/*|node_modules/*|dist/*|build/*) continue ;;
  esac

  if ! has_marker "$f"; then
    echo "ERROR: falta cabecera en $f"
    ERROR=1
  fi
done

exit $ERROR


