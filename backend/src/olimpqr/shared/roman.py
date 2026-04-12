"""Arabic → Roman numeral conversion for tour labels."""

from __future__ import annotations

_ROMAN_PAIRS: tuple[tuple[int, str], ...] = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


def arabic_to_roman(value: int) -> str:
    """Render an integer in the range 1..3999 as a Roman numeral.

    Used for tour labels (1 → I, 2 → II, …) on blanks, badges and exports.
    """
    if not isinstance(value, int) or value < 1 or value > 3999:
        raise ValueError(f"Невозможно преобразовать {value!r} в римское число")
    parts: list[str] = []
    remaining = value
    for arabic, roman in _ROMAN_PAIRS:
        while remaining >= arabic:
            parts.append(roman)
            remaining -= arabic
    return "".join(parts)
