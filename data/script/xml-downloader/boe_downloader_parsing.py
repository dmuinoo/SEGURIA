"""Funciones de parsing usadas por boe_downloader_eli."""

from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Tuple

from defusedxml import ElementTree as ET  # type: ignore[import-untyped]

try:
    import ijson  # type: ignore
except Exception:  # pragma: no cover
    ijson = None  # type: ignore

BASE = "https://www.boe.es"


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def extract_boe_ids_from_sumario_schema(data: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    diario = data.get("sumario", {}).get("diario", {})
    for seccion in diario.get("seccion", []) or []:
        for dept in seccion.get("departamento", []) or []:
            for epigrafe in dept.get("epigrafe", []) or []:
                for item in epigrafe.get("item", []) or []:
                    val = item.get("id") or item.get("identificador")
                    if isinstance(val, str) and val.startswith("BOE-"):
                        ids.append(val)
    return ids


def extract_boe_ids_from_sumario_with_source(
    data: Dict[str, Any],
) -> Tuple[List[str], str]:
    text = data.get("text", "") if isinstance(data, dict) else ""
    matches = re.findall(r"BOE-[A-Z]-\d{4}-\d+", text)
    return _unique_preserve_order(matches), "regex"


def extract_boe_ids_from_sumario_bytes(raw: bytes) -> Tuple[List[str], str]:
    if ijson is None:
        return [], "no-ijson"

    ids: List[str] = []
    for prefix, event, value in ijson.parse(io.BytesIO(raw)):
        if event != "string":
            continue
        if not (prefix.endswith(".id") or prefix.endswith(".identificador")):
            continue
        if isinstance(value, str) and value.startswith("BOE-"):
            ids.append(value)

    ids = _unique_preserve_order(ids)
    return ids, "schema-stream"


def extract_sumario_item_urls(xml_bytes: bytes) -> List[str]:
    """Extract <url_xml> entries from a BOE sumario XML payload.

    Uses ElementTree for the primary path and a regex fallback if parsing fails.
    """
    try:
        root = ET.fromstring(xml_bytes)
        urls: List[str] = []
        for el in root.iter():
            if el.tag.split("}")[-1] == "url_xml":
                text = (el.text or "").strip()
                if text:
                    urls.append(text)
        return _unique_preserve_order(urls)
    except Exception:
        text = xml_bytes.decode("utf-8", errors="ignore")
        matches = re.findall(r"<url_xml>(.*?)</url_xml>", text, flags=re.DOTALL)
        return _unique_preserve_order([m.strip() for m in matches if m.strip()])


def extract_urls_from_act_html(
    html: str, boe_id: str | None = None
) -> Tuple[Optional[str], Optional[str]]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    url_eli: Optional[str] = None
    url_pdf: Optional[str] = None

    for href in hrefs:
        if boe_id and boe_id in href and "/eli/" in href:
            url_eli = href
        if boe_id and boe_id in href and "/pdfs/" in href:
            url_pdf = href

    if url_eli is None:
        for href in hrefs:
            if "/eli/" in href:
                url_eli = href
                break
    if url_pdf is None:
        for href in hrefs:
            if "/pdfs/" in href:
                url_pdf = href
                break

    if url_eli and url_eli.startswith("/"):
        url_eli = f"{BASE}{url_eli}"
    if url_pdf and url_pdf.startswith("/"):
        url_pdf = f"{BASE}{url_pdf}"

    return url_eli, url_pdf


def _first_text(parent: ET.Element, name: str) -> Optional[str]:
    for el in parent.iter():
        if el.tag.split("}")[-1] == name:
            text = (el.text or "").strip()
            return text or None
    return None


def parse_boe_xml_to_model(xml_bytes: bytes) -> Dict[str, Any]:
    root = ET.fromstring(xml_bytes)

    def find_child(name: str) -> Optional[ET.Element]:
        for el in root.iter():
            if el.tag.split("}")[-1] == name:
                return el
        return None

    metadatos = find_child("metadatos")
    metadatos_fields: Dict[str, Any] = {}
    if metadatos is not None:

        def set_attr_text(tag: str, code_key: str, text_key: str) -> None:
            for el in metadatos.iter():
                if el.tag.split("}")[-1] == tag:
                    metadatos_fields[code_key] = el.attrib.get("codigo")
                    metadatos_fields[text_key] = (el.text or "").strip() or None
                    return

        set_attr_text("ambito", "ambito_codigo", "ambito_texto")
        set_attr_text("departamento", "departamento_codigo", "departamento_texto")
        set_attr_text("rango", "rango_codigo", "rango_texto")
        metadatos_fields["fecha_actualizacion_utc"] = _first_text(
            metadatos, "fecha_actualizacion"
        )
        metadatos_fields["fecha_disposicion"] = _first_text(
            metadatos, "fecha_disposicion"
        )
        metadatos_fields["numero_oficial"] = _first_text(metadatos, "numero_oficial")
        metadatos_fields["titulo"] = _first_text(metadatos, "titulo")
        metadatos_fields["diario"] = _first_text(metadatos, "diario")
        metadatos_fields["fecha_publicacion"] = _first_text(
            metadatos, "fecha_publicacion"
        )
        metadatos_fields["diario_numero"] = _first_text(metadatos, "diario_numero")
        metadatos_fields["fecha_vigencia"] = _first_text(metadatos, "fecha_vigencia")
        metadatos_fields["estatus_derogacion"] = _first_text(
            metadatos, "estatus_derogacion"
        )
        metadatos_fields["estatus_anulacion"] = _first_text(
            metadatos, "estatus_anulacion"
        )
        metadatos_fields["vigencia_agotada"] = _first_text(
            metadatos, "vigencia_agotada"
        )
        for el in metadatos.iter():
            if el.tag.split("}")[-1] == "estado_consolidacion":
                metadatos_fields["estado_consolidacion_codigo"] = el.attrib.get(
                    "codigo"
                )
                metadatos_fields["estado_consolidacion_texto"] = (
                    el.text or ""
                ).strip() or None
                break

    materias: List[Dict[str, Optional[str]]] = []
    for el in root.iter():
        if el.tag.split("}")[-1] == "materia":
            materias.append(
                {
                    "codigo": el.attrib.get("codigo"),
                    "texto": (el.text or "").strip() or None,
                }
            )

    notas: List[str] = []
    for el in root.iter():
        if el.tag.split("}")[-1] == "nota":
            txt = (el.text or "").strip()
            if txt:
                notas.append(txt)

    texto_blocks: List[Dict[str, Any]] = []
    for el in root.iter():
        if el.tag.split("}")[-1] == "bloque":
            texto_blocks.append(
                {
                    "block_key": el.attrib.get("id"),
                    "block_tipo": el.attrib.get("tipo"),
                    "block_titulo": el.attrib.get("titulo"),
                }
            )

    return {
        "metadatos_fields": metadatos_fields,
        "metadatos_raw": {},
        "analisis_raw": {},
        "materias": materias,
        "notas": notas,
        "referencias": [],
        "metadata_eli_raw": None,
        "texto_raw": None,
        "xml_raw": xml_bytes.decode("utf-8", errors="replace"),
        "texto_blocks": texto_blocks,
    }
