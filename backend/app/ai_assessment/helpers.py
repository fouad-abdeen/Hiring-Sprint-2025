from typing import Any, TypedDict, Optional


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


def _bbox_iou(a: DamagePrediction, b: DamagePrediction) -> float:
    """
    Compute IoU between two boxes in center-x, center-y, width, height format.
    """
    ax_min = a["x"] - a["width"] / 2.0
    ay_min = a["y"] - a["height"] / 2.0
    ax_max = a["x"] + a["width"] / 2.0
    ay_max = a["y"] + a["height"] / 2.0

    bx_min = b["x"] - b["width"] / 2.0
    by_min = b["y"] - b["height"] / 2.0
    bx_max = b["x"] + b["width"] / 2.0
    by_max = b["y"] + b["height"] / 2.0

    inter_x_min = max(ax_min, bx_min)
    inter_y_min = max(ay_min, by_min)
    inter_x_max = min(ax_max, bx_max)
    inter_y_max = min(ay_max, by_max)

    inter_w = max(0.0, inter_x_max - inter_x_min)
    inter_h = max(0.0, inter_y_max - inter_y_min)
    inter_area = inter_w * inter_h

    if inter_area <= 0:
        return 0.0

    area_a = a["width"] * a["height"]
    area_b = b["width"] * b["height"]
    union = area_a + area_b - inter_area
    if union <= 0:
        return 0.0

    return inter_area / union


def _normalize_predictions(
    result: dict[str, Any],
    min_confidence: float = 0.5,
) -> list[DamagePrediction]:
    """
    Take a raw model result and return a filtered, normalized list of predictions.
    """
    raw_predictions = result.get("predictions", []) or []

    normalized: list[DamagePrediction] = []
    for prediction in raw_predictions:
        confidence = float(prediction.get("confidence", 0.0))
        if confidence < min_confidence:
            continue

        normalized.append(
            DamagePrediction(
                x=float(prediction["x"]),
                y=float(prediction["y"]),
                width=float(prediction["width"]),
                height=float(prediction["height"]),
                confidence=confidence,
                class_id=int(prediction.get("class_id", -1)),
                class_name=str(prediction.get("class", "")),
                detection_id=str(prediction.get("detection_id", "")),
            )
        )
    return normalized
