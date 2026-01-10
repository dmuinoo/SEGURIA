#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import shutil
import subprocess
import sys

import boe_downloader_eli as boe


def test_extract_boe_ids_from_sumario_schema_preserves_order() -> None:
    data = {
        "sumario": {
            "diario": {
                "seccion": [
                    {
                        "departamento": [
                            {
                                "epigrafe": [
                                    {
                                        "item": [
                                            {"id": "BOE-A-2024-2"},
                                            {"id": "BOE-A-2024-1"},
                                            {"identificador": "BOE-A-2024-3"},
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        }
    }
    ids = boe.extract_boe_ids_from_sumario_schema(data)
    assert ids == ["BOE-A-2024-2", "BOE-A-2024-1", "BOE-A-2024-3"]


def test_extract_boe_ids_from_sumario_bytes_stream_order() -> None:
    payload = {
        "sumario": {
            "diario": {
                "seccion": [
                    {
                        "departamento": [
                            {
                                "epigrafe": [
                                    {
                                        "item": [
                                            {"id": "BOE-A-2024-1"},
                                            {"id": "BOE-A-2024-2"},
                                            {"id": "BOE-A-2024-1"},
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        }
    }
    raw = json.dumps(payload).encode("utf-8")
    ids, source = boe.extract_boe_ids_from_sumario_bytes(raw)
    if source == "no-ijson":
        return
    assert ids == ["BOE-A-2024-1", "BOE-A-2024-2"]
    assert source in ("schema-stream", "regex-stream")


def test_extract_boe_ids_from_sumario_regex_order() -> None:
    data = {"text": "Refs BOE-A-2024-2 then BOE-A-2024-1 and BOE-A-2024-2 again"}
    ids, source = boe.extract_boe_ids_from_sumario_with_source(data)
    assert ids == ["BOE-A-2024-2", "BOE-A-2024-1"]
    assert source == "regex"


def test_extract_urls_from_act_html_prefers_boe_id_and_pdfs() -> None:
    html = """
    <html><body>
      <a href="/eli/id/BOE-A-2024-1/con">eli1</a>
      <a href="/eli/id/BOE-A-2024-2/con">eli2</a>
      <a href="/pdfs/2024/BOE-A-2024-2.pdf">pdf2</a>
      <a href="/pdfs/2024/BOE-A-2024-1.pdf">pdf1</a>
    </body></html>
    """
    url_eli, url_pdf = boe.extract_urls_from_act_html(html, boe_id="BOE-A-2024-1")
    assert url_eli.endswith("/eli/id/BOE-A-2024-1/con")
    assert url_pdf.endswith("/pdfs/2024/BOE-A-2024-1.pdf")


def test_parse_boe_xml_with_namespace() -> None:
    xml = """
    <root xmlns="urn:test">
      <data>
        <metadatos>
          <fecha_actualizacion>20240101T000000Z</fecha_actualizacion>
          <ambito codigo="EST">Estado</ambito>
          <departamento codigo="D1">Dept</departamento>
          <rango codigo="R1">Rango</rango>
          <fecha_disposicion>20240102</fecha_disposicion>
          <numero_oficial>1</numero_oficial>
          <titulo>Titulo</titulo>
          <diario>BOE</diario>
          <fecha_publicacion>20240103</fecha_publicacion>
          <diario_numero>10</diario_numero>
          <fecha_vigencia>20240104</fecha_vigencia>
          <estatus_derogacion>NO</estatus_derogacion>
          <estatus_anulacion>NO</estatus_anulacion>
          <vigencia_agotada>NO</vigencia_agotada>
          <estado_consolidacion codigo="V">Vigente</estado_consolidacion>
        </metadatos>
        <analisis>
          <materias><materia codigo="M1">Materia</materia></materias>
          <notas><nota>Nota 1</nota></notas>
          <referencias>
            <anteriores>
              <relacion>
                <id_norma>BOE-A-2023-1</id_norma>
                <relacion codigo="R">Relacion</relacion>
                <texto>Texto</texto>
              </relacion>
            </anteriores>
          </referencias>
        </analisis>
        <texto>
          <bloque id="b1" tipo="encabezado" titulo="TITULO I">
            <version id_norma="BOE-A-2024-1" fecha_publicacion="20240103" fecha_vigencia="20240104">
              <p class="p">Hola</p>
            </version>
          </bloque>
        </texto>
      </data>
    </root>
    """
    parsed = boe.parse_boe_xml_to_model(xml.encode("utf-8"))
    md = parsed["metadatos_fields"]
    assert md["ambito_codigo"] == "EST"
    assert md["diario"] == "BOE"
    assert parsed["materias"][0]["codigo"] == "M1"
    assert parsed["notas"][0] == "Nota 1"
    assert parsed["texto_blocks"][0]["block_key"] == "b1"


# Network tests (disabled by default):
# - test_run_consolidada_fetch_real_urls
# - test_run_sumario_fetch_real


def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(cmd: list[str], desc: str) -> int:
    print(f"\n==> {desc}")
    print(" ".join(cmd))
    return subprocess.call(cmd)


def main() -> int:
    python = sys.executable
    exit_code = 0
    missing = []
    for mod in ("pytest", "black", "mypy", "pylint", "bandit", "coverage"):
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    if missing:
        print("Faltan dependencias de test: " + ", ".join(missing))
        print("Ejecuta: uv run --extra test python3 test_boe_downloader_eli.py")

    if _which("pytest"):
        exit_code |= _run([python, "-m", "pytest", "-q", __file__], "pytest")
        if _which("coverage"):
            exit_code |= _run(
                ["coverage", "run", "-m", "pytest", "-q", __file__], "coverage run"
            )
            exit_code |= _run(["coverage", "report"], "coverage report")
        if _which("pytest") and _which("pytest-cov"):
            exit_code |= _run(
                [
                    python,
                    "-m",
                    "pytest",
                    "-q",
                    "--cov=.",
                    "--cov-report=term-missing",
                    __file__,
                ],
                "pytest-cov",
            )
        if _which("pytest"):
            exit_code |= _run(
                [python, "-m", "pytest", "-q", "--doctest-glob=*.py"],
                "pytest doctest",
            )
    else:
        print("pytest no esta disponible; saltando tests.")

    if _which("ruff"):
        exit_code |= _run(["ruff", "check", "boe_downloader_eli.py"], "ruff")
    if _which("mypy"):
        exit_code |= _run(["mypy", "boe_downloader_eli.py"], "mypy")
    if _which("pylint"):
        exit_code |= _run(["pylint", "boe_downloader_eli.py"], "pylint")
    if _which("bandit"):
        exit_code |= _run(["bandit", "-r", "boe_downloader_eli.py"], "bandit")
    if _which("black"):
        exit_code |= _run(["black", "--check", "."], "black")

    if os.getenv("RUN_HEAVY", "0") == "1":
        if _which("mutmut"):
            exit_code |= _run(["mutmut", "run"], "mutmut")
        if _which("locust"):
            exit_code |= _run(["locust", "--version"], "locust")
    else:
        print("RUN_HEAVY=1 para ejecutar mutmut/locust.")

    for mod in (
        "pytest_asyncio",
        "pytest_mock",
        "hypothesis",
        "testcontainers",
        "httpx",
        "requests",
        "fastapi",
        "pydantic",
    ):
        try:
            __import__(mod)
        except Exception:
            print(f"Modulo no disponible: {mod}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
