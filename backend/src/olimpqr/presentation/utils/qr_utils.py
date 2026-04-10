"""Shared QR token parsing utilities."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from uuid import UUID

ATTEMPT_TOKEN_PATTERN = re.compile(
    r"attempt[:/](?P<attempt_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
    re.IGNORECASE,
)
ATTEMPT_TOKEN_LEGACY_PATTERN = re.compile(
    r"^(?P<attempt_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?=[:/]|$)",
    re.IGNORECASE,
)
# Matches A3-cover QR: attempt:<UUID>:tour:<N>:cover
A3_COVER_PATTERN = re.compile(
    r"attempt[:/](?P<attempt_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"[:/]tour[:/](?P<tour_number>\d+)[:/]cover",
    re.IGNORECASE,
)


def normalize_sheet_token(raw_token: str) -> str:
    """Normalize scanned token from laser/camera scanners."""
    token = (raw_token or "").strip().strip('"').strip("'")
    token = token.replace("\ufeff", "").replace("\u200b", "").strip()
    if not token:
        return ""

    parsed = urlparse(token)
    if parsed.scheme in {"http", "https"}:
        query = parse_qs(parsed.query)
        for key in ("sheet_token", "token", "qr", "data"):
            values = query.get(key)
            if values and values[0].strip():
                return unquote(values[0]).strip()

        path_value = unquote(parsed.path).strip()
        if "attempt:" in path_value.lower() or "attempt/" in path_value.lower():
            return path_value.strip("/")

        tail = unquote(parsed.path.rsplit("/", 1)[-1]).strip()
        if tail:
            return tail

    return unquote(token).strip()


def extract_attempt_id(token: str) -> UUID | None:
    """Extract attempt UUID from QR token payload."""
    match = ATTEMPT_TOKEN_PATTERN.search(token)
    if not match:
        match = ATTEMPT_TOKEN_LEGACY_PATTERN.search(token)
    if not match:
        return None
    try:
        return UUID(match.group("attempt_id"))
    except ValueError:
        return None


def extract_a3_cover_info(token: str) -> tuple[UUID, int] | None:
    """Extract (attempt_id, tour_number) from an A3-cover QR payload.

    Returns None if the token is not in A3-cover format.
    """
    match = A3_COVER_PATTERN.search(token)
    if not match:
        return None
    try:
        attempt_id = UUID(match.group("attempt_id"))
        tour_number = int(match.group("tour_number"))
        return attempt_id, tour_number
    except (ValueError, IndexError):
        return None


def extract_special_tours(competition: Any) -> list[dict[str, Any]]:
    """Extract normalized special tours config from a competition object/model."""
    if not competition or not getattr(competition, "is_special", False):
        return []

    allowed_modes = {"individual", "individual_captains", "team"}
    settings_payload = (getattr(competition, "special_settings", None) or {})
    raw_tours = settings_payload.get("tours")

    normalized: list[dict[str, Any]] = []
    if isinstance(raw_tours, list):
        for idx, item in enumerate(raw_tours, start=1):
            if not isinstance(item, dict):
                continue
            tour_number = int(item.get("tour_number") or idx)
            mode = str(item.get("mode") or "individual").strip()
            if mode not in allowed_modes:
                mode = "individual"
            task_numbers = item.get("task_numbers") or item.get("tasks") or [1]
            tasks: list[int] = []
            for task in task_numbers:
                try:
                    val = int(task)
                    if val > 0:
                        tasks.append(val)
                except Exception:  # noqa: BLE001
                    continue
            if not tasks:
                tasks = [1]
            normalized.append(
                {
                    "tour_number": tour_number,
                    "mode": mode,
                    "task_numbers": sorted(set(tasks)),
                }
            )

    if normalized:
        return normalized

    tours_count = int(getattr(competition, "special_tours_count", 0) or 1)
    modes = getattr(competition, "special_tour_modes", None) or []
    fallback: list[dict[str, Any]] = []
    for idx in range(tours_count):
        mode = str(modes[idx]) if idx < len(modes) else "individual"
        if mode not in allowed_modes:
            mode = "individual"
        fallback.append(
            {
                "tour_number": idx + 1,
                "mode": mode,
                "task_numbers": [1],
            }
        )
    return fallback
