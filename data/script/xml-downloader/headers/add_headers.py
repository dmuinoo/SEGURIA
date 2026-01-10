#!/usr/bin/env python3
import os

HEADER_PY = """# -----------------------------------------------------------------------------
# Proyecto: ia
# Autor: Diego Muiño Orallo
# Con asistencia técnica mediante Vibecoding
# Año: 2025
#
# Este archivo forma parte del proyecto "ia".
# Se distribuye bajo los términos de la Licencia Pública de la Unión Europea
# v. 1.2 (EUPL-1.2). Consulte los archivos LICENSE y NOTICE para más detalles.
#
# De acuerdo con la EUPL, cualquier modificación de este archivo deberá incluir
# una indicación clara de los cambios realizados y su fecha.
# -----------------------------------------------------------------------------

"""

HEADER_JS = """/*
------------------------------------------------------------------------------
 Proyecto: ia
 Autor: Diego Muiño Orallo
 Con asistencia técnica mediante Vibecoding
 Año: 2025

 Este archivo forma parte del proyecto "ia".
 Se distribuye bajo la Licencia Pública de la Unión Europea v. 1.2 (EUPL-1.2).
 Consulte LICENSE y NOTICE para información detallada.

 De acuerdo con la EUPL, cualquier modificación de este archivo deberá 
 indicar claramente los cambios realizados y la fecha de modificación.
------------------------------------------------------------------------------
*/

"""

HEADER_MD = """> **Proyecto:** ia  
> **Autor:** Diego Muiño Orallo  
> **Con asistencia de:** Vibecoding  
> **Año:** 2025  
>  
> Este documento forma parte del proyecto "ia" y se distribuye bajo la  
> Licencia Pública de la Unión Europea v. 1.2 (EUPL-1.2).  
> Consulte los archivos `LICENSE` y `NOTICE` para más detalles.  

"""

# Marcadores (para detectar cabecera ya presente)
MARK_PY = "Proyecto: ia"
MARK_JS = "Proyecto: ia"
MARK_MD = "**Proyecto:** ia"  # importante: coincide con tu cabecera real

SKIP_DIR_FRAGMENTS = (
    "/.git/",
    "/.venv/",
    "/venv/",
    "/node_modules/",
    "/dist/",
    "/build/",
)


def should_skip_path(path: str) -> bool:
    p = path.replace("\\", "/")
    return any(frag in p for frag in SKIP_DIR_FRAGMENTS)


def add_header_to_file(path: str, header: str, marker: str) -> bool:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Detecta cabecera en el comienzo del archivo (evita falsos positivos)
    if marker in content[:3000]:
        return False

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + content)

    return True


def main():
    modified = 0

    for root, _, files in os.walk("."):
        # Salta directorios típicos
        if should_skip_path(root + "/"):
            continue

        for name in files:
            path = os.path.join(root, name)

            if should_skip_path(path):
                continue

            # Nunca tocar binarios típicos
            if name.endswith((".png", ".jpg", ".jpeg", ".pdf", ".zip", ".bin", ".exe")):
                continue

            if name.endswith(".py"):
                if add_header_to_file(path, HEADER_PY, MARK_PY):
                    modified += 1

            elif name.endswith((".js", ".ts")):
                if add_header_to_file(path, HEADER_JS, MARK_JS):
                    modified += 1

            elif name.endswith(".md"):
                if add_header_to_file(path, HEADER_MD, MARK_MD):
                    modified += 1

    print(f"Añadir automáticamente cabeceras... (modificados: {modified})")


if __name__ == "__main__":
    main()
