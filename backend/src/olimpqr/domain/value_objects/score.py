"""Score value object."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Score:
    """Represents a competition score.

    Attributes:
        value: The numeric score value
        max_value: Maximum possible score for the competition
        confidence: OCR confidence level (0.0-1.0), None if manually entered
    """
    value: float
    max_value: float
    confidence: float | None = None

    def __post_init__(self):
        if self.value < 0:
            raise ValueError("Балл не может быть отрицательным")
        if self.max_value <= 0:
            raise ValueError("Максимальное значение должно быть положительным")
        if self.value > self.max_value:
            raise ValueError(f"Балл {self.value} превышает максимум {self.max_value}")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError("Уверенность должна быть от 0.0 до 1.0")

    @property
    def percentage(self) -> float:
        """Calculate score as percentage of maximum."""
        return (self.value / self.max_value) * 100

    @property
    def is_high_confidence(self) -> bool:
        """Check if OCR confidence is high enough for auto-approval."""
        from ...config import settings
        return self.confidence is not None and self.confidence >= settings.ocr_confidence_threshold
