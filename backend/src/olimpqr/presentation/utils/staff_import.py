"""Parser for Руководители.xlsx (staff/leaders import for badge generation)."""

from __future__ import annotations

import io
import re
from typing import Any

_CITY_PAREN_RE = re.compile(r"\(\s*г\.?\s*([^)]+?)\s*\)", re.IGNORECASE | re.UNICODE)

_ABBREVIATION_MAP: dict[str, str] | None = None


def _abbreviate(institution_name: str) -> str:
    """Build abbreviation from institution name.

    Takes first uppercase Cyrillic letter of each word, or if none found,
    uses first 4 letters uppercase.
    """
    words = institution_name.split()
    caps = [w[0] for w in words if w and w[0].isupper()]
    if len(caps) >= 2:
        return "".join(caps)
    return institution_name[:4].upper().strip()


def split_institution_and_city(raw: str) -> tuple[str, str | None]:
    """Split 'БВВМУ (г. Калининград)' → ('БВВМУ', 'Калининград')."""
    m = _CITY_PAREN_RE.search(raw)
    if m:
        city = m.group(1).strip()
        name = raw[: m.start()].strip()
        return name, city
    return raw.strip(), None


def looks_like_rukovoditeli_sheet(rows: list[list[Any]]) -> bool:
    """Detect Руководители.xlsx template by header signature."""
    if len(rows) < 2:
        return False
    for row in rows[:5]:
        cells = [str(c).lower().strip() if c else "" for c in row]
        joined = " ".join(cells)
        if "вуз" in joined and ("фио" in joined or "ф.и.о" in joined):
            return True
    return False


def parse_rukovoditeli_xlsx(file_bytes: bytes) -> list[dict[str, Any]] | None:
    """Parse Руководители.xlsx template.

    Expected layout (positional):
      Column A (0): institution name with optional city in parens
      Column E (4): ФИО (full name)

    Role is auto-derived as 'ПРЕДСТАВИТЕЛЬ {abbreviation}'.

    Returns list of dicts with keys: full_name, role, institution, city.
    Returns None if the file doesn't match the template signature.
    """
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    result: list[dict[str, Any]] = []

    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not looks_like_rukovoditeli_sheet(rows):
            continue

        header_row_idx = None
        for idx, row in enumerate(rows[:5]):
            cells = [str(c).lower().strip() if c else "" for c in row]
            joined = " ".join(cells)
            if "фио" in joined or "ф.и.о" in joined:
                header_row_idx = idx
                break

        if header_row_idx is None:
            continue

        current_institution: str | None = None
        current_city: str | None = None

        for row in rows[header_row_idx + 1 :]:
            padded = list(row) + [None] * max(0, 6 - len(row))
            cell_a = str(padded[0]).strip() if padded[0] else ""
            cell_e = str(padded[4]).strip() if padded[4] else ""

            if cell_a and cell_a.lower() not in ("none", ""):
                inst, city = split_institution_and_city(cell_a)
                if inst:
                    current_institution = inst
                    current_city = city

            if not cell_e or cell_e.lower() in ("none", ""):
                continue

            full_name = cell_e.strip()
            if current_institution and current_city:
                role = f"РУКОВОДИТЕЛЬ КОМАНДЫ\n({current_institution} г.{current_city})"
            elif current_institution:
                role = f"РУКОВОДИТЕЛЬ КОМАНДЫ\n({current_institution})"
            else:
                role = "РУКОВОДИТЕЛЬ КОМАНДЫ"

            result.append({
                "full_name": full_name,
                "role": role,
                "institution": current_institution,
                "city": current_city,
            })

    wb.close()
    return result if result else None
