from typing import TypedDict, Optional


class DamagePrediction(TypedDict, total=False):
    x: float
    y: float
    width: float
    height: float
    confidence: float
    class_id: int
    class_name: str
    detection_id: str
    severity: Optional[str]
