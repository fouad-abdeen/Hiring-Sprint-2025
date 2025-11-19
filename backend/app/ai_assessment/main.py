from typing import Any, Optional
import requests
from inference_sdk import InferenceHTTPClient
import supervision as sv
import cv2
import numpy as np

from ..config import Settings
from ..models import UploadedFileInfo
from .helpers import DamagePrediction, _normalize_predictions, _bbox_iou

settings = Settings() # loads from environment
roboflow_client = InferenceHTTPClient(settings.ROBOFLOW_API_URL, settings.ROBOFLOW_API_KEY)
# confidence_threshold defaults to 0.4 and IoU threshold defaults to 0.5
car_damage_model_1 = "car-damage-detection-5ioys/1"
car_damage_model_2 = "car-damage-c1f0i/1"
damage_severity_model = "car-damage-severity-detection-cardd/1"

def assess_car_on_return(uploaded_images: list[UploadedFileInfo]):
    assessment_results: list[tuple[dict, UploadedFileInfo]] = []

    if len(uploaded_images) % 2 != 0:
        raise ValueError("Uploaded images must be in pairs (pickup, return)")

    for i in range(0, len(uploaded_images), 2):
        pickup_image = uploaded_images[i]
        return_image = uploaded_images[i + 1]

        result_on_pickup = detect_car_damage(pickup_image.url)
        result_on_return = detect_car_damage(return_image.url)
        image_side = pickup_image.key.split("_")[0].split("/")[0]

        damage_comparison = compare_damage(result_on_pickup, result_on_return)
        final_result = {"predictions": damage_comparison.get("new_damages", []), "image_side": image_side}
        assessment_results.append((final_result, return_image))

    return assessment_results

def detect_car_damage(image_url: str, iou_threshold: Optional[float] = 0.5) -> list[DamagePrediction]:
    """
    Run multiple car-damage detection models and return the final result.

    Strategy:
    Using multiple models to cover all possible damage scenarios while avoiding false positives.
    - Car Damage Model 1 has a high precision (90%) and covers a wide range of damage scenarios.
    - Car Damage Model 2 has a richer classification output and might cover more damage scenarios.
    - Damage Severity Model detects the severity of damage if any to avoid false positives.


    Decision logic:
    - If at least one model detects predictions: check for damage severity if damage exists.
    - If the damage severity model didn't detect any damage: return an empty predictions list.
    - Otherwise: If only one model detects predictions, return predictions that overlap with the severity predictions.
    - If both car damage models detect predictions and both overlap, return predictions with the highest confidence.

    Returns:
        A dict with a "predictions" key (list), or an empty predictions list if no damage.
    """
    model_1_result: dict[str, Any] = roboflow_client.infer(image_url, car_damage_model_1)
    model_2_result: dict[str, Any] = roboflow_client.infer(image_url, car_damage_model_2)
    severity_result: dict[str, Any] = roboflow_client.infer(image_url, damage_severity_model)

    final_result: list[DamagePrediction] = []

    m1_predictions = _normalize_predictions(model_1_result)
    m2_predictions = _normalize_predictions(model_2_result)
    severity_predictions = severity_result.get("predictions", []) or []

    # If no car damage at all, or no severity predictions, treat as no damage.
    if (not m1_predictions and not m2_predictions) or not severity_predictions:
        return final_result

    # To-Do:
    # 1. Filter out overlapping predictions from both models choosing the highest confidence.
    # 2. Aggregate predictions from both models and check for overlap with severity predictions.

    all_damage_predictions = m1_predictions + m2_predictions
    seen_detection_ids: set[str] = set()  # deduplication by detection_id

    for prediction_a in all_damage_predictions:
        overlapping_predictions = [prediction_a]

        for prediction_b in all_damage_predictions:
            if prediction_a is prediction_b:
                continue
            iou = _bbox_iou(prediction_a, prediction_b)
            if iou > iou_threshold:
                overlapping_predictions.append(prediction_b)

        # Choose the highest confidence prediction if overlapping.
        highest_confidence_prediction = max(
            overlapping_predictions,
            key=lambda x: x.get("confidence", 0.0),
        )

        detection_id = str(highest_confidence_prediction.get("detection_id", ""))
        if detection_id and detection_id in seen_detection_ids:
            continue
        if detection_id:
            for severity_prediction in severity_predictions:
                iou = _bbox_iou(highest_confidence_prediction, severity_prediction)
                if iou > 0.5:
                    seen_detection_ids.add(detection_id)
                    # To-Do: Prompt OpenAI to verify the severity classification.
                    # highest_confidence_prediction["severity"] = severity_prediction["class"]
                    final_result.append(highest_confidence_prediction)
                    break

    return final_result

def compare_damage(
    pickup_result: list[DamagePrediction],
    return_result: list[DamagePrediction],
    iou_threshold: float = 0.3,
    require_same_class: bool = True,
) -> dict[str, list[DamagePrediction]]:
    """
    Compare pickup vs. return detections and classify them into:
      - new_damages: on return only (or increased confidence on return)
      - existing_damages: present in both, confidence higher on pickup
      - resolved_damages: present on pickup only

    Matching rules:
    - Two boxes are a potential match if IoU >= iou_threshold.
    - If `require_same_class` is True, classes must also match.
    - For each pickup box we select at most one best matching return box (greedy on IoU).

    Confidence rules for overlapping matches:
    - If a damage prediction is overlapping on both stages:
        * If confidence(return) > confidence(pickup):
            Treat as *new damage* on return, with confidence reduced to
            confidence(return) - confidence(pickup).
        * Otherwise:
            Treat as *existing damage* from pickup, with confidence reduced to
            confidence(pickup) - confidence(return).
    - Any unmatched pickup box is considered resolved.
    - Any unmatched return box is considered new.
    """
    new_damages: list[DamagePrediction] = []
    existing_damages: list[DamagePrediction] = []
    resolved_damages: list[DamagePrediction] = []

    if not pickup_result and not return_result:
        return {
            "new_damages": new_damages,
            "existing_damages": existing_damages,
            "resolved_damages": resolved_damages,
        }

    # Track which return indices are already matched
    matched_return_indices: set[int] = set()

    # 1. For each pickup prediction, find the best matching return prediction (if any)
    for p_idx, p_pred in enumerate(pickup_result):
        best_iou = 0.0
        best_r_idx: Optional[int] = None

        for r_idx, r_pred in enumerate(return_result):
            if r_idx in matched_return_indices:
                continue

            if require_same_class and p_pred.get("class_name") != r_pred.get("class_name"):
                continue

            iou = _bbox_iou(p_pred, r_pred)
            if iou >= iou_threshold and iou > best_iou:
                best_iou = iou
                best_r_idx = r_idx

        if best_r_idx is None:
            # No overlapping return damage: this damage seems resolved
            resolved_damages.append(p_pred)
            continue

        # We have a damage overlapping on pickup and return
        matched_return_indices.add(best_r_idx)
        r_pred = return_result[best_r_idx]

        p_conf = float(p_pred.get("confidence", 0.0))
        r_conf = float(r_pred.get("confidence", 0.0))

        if r_conf - p_conf > 0.3:
            # Consider "new" damage on return, with reduced confidence
            new_pred = DamagePrediction(**p_pred)
            new_pred["confidence"] = r_conf - p_conf
            new_damages.append(new_pred)
        else:
            # Consider "existing" damage from pickup
            existing_damages.append(p_pred)

    # 2. Any return prediction was not matched at all is treated as new damage
    for r_idx, r_pred in enumerate(return_result):
        if r_idx in matched_return_indices:
            continue
        new_damages.append(r_pred)

    return {
        "new_damages": new_damages,
        "existing_damages": existing_damages,
        "resolved_damages": resolved_damages,
    }

async def draw_bounding_box(
    image_url: str,
    result: dict[str, list[DamagePrediction]],
) -> np.ndarray:
    # Download image bytes from URL
    response = requests.get(image_url)
    response.raise_for_status()
    content = response.content

    # Convert the byte content to a NumPy array and decode into an OpenCV image (BGR)
    nparr = np.frombuffer(content, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to decode image from URL: {image_url}")

    # Build supervision.Detections manually from our normalized predictions
    predictions: list[DamagePrediction] = result.get("predictions", []) or []

    if not predictions:
        # Nothing to draw, just return the original image
        return image

    xyxy_list: list[list[float]] = []
    confidence_list: list[float] = []
    class_id_list: list[int] = []

    for idx, p in enumerate(predictions):
        # Roboflow-style boxes: center x/y, width, height
        # Adjust this if your DamagePrediction uses different keys.
        x = float(p.get("x", 0.0))
        y = float(p.get("y", 0.0))
        w = float(p.get("width", 0.0))
        h = float(p.get("height", 0.0))

        x_min = x - w / 2
        y_min = y - h / 2
        x_max = x + w / 2
        y_max = y + h / 2

        xyxy_list.append([x_min, y_min, x_max, y_max])
        confidence_list.append(float(p.get("confidence", 0.0)))
        # Fall back to index if class_id is not present
        class_id_list.append(int(p.get("class_id", idx)))

    detections = sv.Detections(
        xyxy=np.array(xyxy_list, dtype=float),
        confidence=np.array(confidence_list, dtype=float),
        class_id=np.array(class_id_list, dtype=int),
    )

    labels = []
    for p in predictions:
        cls = p.get("class_name") or "damage"
        cls = cls.replace("-", " ").title()
        conf = float(p.get("confidence", 0.0)) * 100.0
        conf = round(conf)
        labels.append(f"{conf}% {cls}")

    bounding_box_annotator = sv.BoxAnnotator()
    annotated_frame = bounding_box_annotator.annotate(
        scene=image.copy(),
        detections=detections,
    )

    label_annotator = sv.LabelAnnotator()
    annotated_frame = label_annotator.annotate(
        scene=annotated_frame,
        detections=detections,
        labels=labels,
    )

    return annotated_frame
