import time
from datetime import datetime, timezone
from io import BytesIO

import cv2
from starlette.concurrency import run_in_threadpool

from .ai_assessment.helpers import DamagePrediction
from .assessment_repository import get_assessment, set_assessment
from .ai_assessment.main import assess_car_condition, draw_bounding_box, get_prediction_label
from .models import AssessmentResponse
from .upload_service import UploadService

import logging
logger = logging.getLogger(__name__)

async def run_assessment(
    upload_id: str,
    service: UploadService,
) -> None:
    """
    Background job:
      - Run `assess_car_condition` in a threadpool (CPU / blocking work).
      - Draw bounding boxes.
      - Encode and upload annotated images.
    """
    start_time = time.time()
    logger.info(f"Starting assessment for upload_id: {upload_id}")

    try:
        current = get_assessment(upload_id)
        if not current:
            raise Exception(f"Assessment not found for upload ID: {upload_id}")
        
        if current.status in ["complete", "in_progress"]:
            return

        set_assessment(upload_id, AssessmentResponse(
            status="in_progress",
            updated_at=datetime.now(timezone.utc).isoformat(),
            started_at = datetime.now(timezone.utc).isoformat(),
        ))

        # Run the heavy, synchronous assessment in a thread pool
        assessment_results = await run_in_threadpool(assess_car_condition, upload_id, service)

        all_predictions: list[DamagePrediction] = []

        for side, side_assessment in assessment_results.items():
            predictions = side_assessment.get("predictions", [])
            all_predictions.extend(predictions)

            return_image_url = side_assessment.get("return_image")
            if not return_image_url:
                # Skip if there's no return image URL for some reason
                continue

            # Draw bounding boxes on the return image
            annotated_image = draw_bounding_box(return_image_url, predictions)

            # Encode the annotated image (NumPy array) as JPEG in a thread pool
            success, buffer = await run_in_threadpool(cv2.imencode, ".jpg", annotated_image)
            if not success:
                # In a background task we can't surface this directly to the client;
                # for now just stop processing this image.
                continue

            bytes_io = BytesIO(buffer.tobytes())
            bytes_io.seek(0)

            # Derive a key name for the annotated image
            # Use the existing return image URL or side name to construct something stable
            annotated_key = f"{upload_id}/{side}-return-annotated.jpg"

            # Upload annotated image; this method already offloads to threadpool internally
            uploaded_file = await service.upload_file_object(
                bytes_io,
                annotated_key,
                content_type="image/jpeg",
            )

            side_assessment["annotated_return_image"] = uploaded_file.url
            assessment_results[side] = side_assessment

        summary = "The car is in good condition." if len(all_predictions) == 0 else ""

        if len(all_predictions) == 1:
            summary = f"The car has one damage: {get_prediction_label(all_predictions[0])}"
        elif len(all_predictions) > 1:
            summary = f"The car has {len(all_predictions)} damages:"
            for index, pred in enumerate(all_predictions):
                summary += f"\n{index + 1}. {get_prediction_label(pred)}"

        duration = time.time() - start_time
        logger.info(f"Assessment completed in {duration:.2f}s for {upload_id}")
        set_assessment(
            upload_id, AssessmentResponse(
                status="complete",
                updated_at=datetime.now(timezone.utc).isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
                results=assessment_results,
                summary=summary)
        )

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Assessment failed after {duration:.2f}s for {upload_id}")
        logger.exception(e)

        error_message = f"{type(e).__name__}: {str(e)}"
        set_assessment(upload_id, AssessmentResponse(
            status="failed",
            updated_at=datetime.now(timezone.utc).isoformat(),
            error=error_message
        ))
