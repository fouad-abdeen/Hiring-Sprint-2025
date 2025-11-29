import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, status, Depends, BackgroundTasks, UploadFile, File
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .assessment_repository import set_assessment, get_assessment
from .config import Settings
from .s3_client import S3Client
from .models import AssessmentResponse, UploadResponse
from .assessment_service import run_assessment
from .upload_service import UploadService

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Car Condition Assessment API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Error handler middleware
@app.middleware("http")
async def error_handler_middleware(request: Request, call_next):
    """
    Global error handler middleware to catch and handle all exceptions.
    """
    try:
        response = await call_next(request)
        return response
    except HTTPException as exc:
        # HTTPException is already handled by FastAPI, but we can log it
        logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail}")
        raise
    except ValueError as exc:
        logger.error(f"Validation error on {request.url.path}: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": str(exc),
                "error_type": "validation_error"
            }
        )
    except PermissionError as exc:
        logger.error(f"Permission error on {request.url.path}: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "detail": "Permission denied",
                "error_type": "permission_error"
            }
        )
    except FileNotFoundError as exc:
        logger.error(f"File not found on {request.url.path}: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "detail": "Resource not found",
                "error_type": "not_found"
            }
        )
    except Exception as exc:
        # Catch all other exceptions
        logger.exception(f"Unhandled exception on {request.url.path}: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An internal server error occurred",
                "error_type": "internal_server_error"
            }
        )


origins = [
    "http://localhost:5173",
    "http://localhost:8000",
    ### Production Domain ###
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "Authorization"],
)

settings = Settings()  # loads from environment
s3 = S3Client(settings.AWS_S3_BUCKET, settings.AWS_S3_REGION, settings.AWS_S3_ENDPOINT, settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_ACCESS_KEY)
upload_service = UploadService(s3_client=s3, settings=settings)

def get_upload_service() -> UploadService:
    # It's better to use dependency injection than global variables in large applications.
    return upload_service


@app.get("/health")
async def health():
    """Simple health endpoint."""
    return {"status": "ok"}


@app.post("/upload", response_model=UploadResponse)
@limiter.limit("5/minute")
async def upload_images(
    request: Request,
    background_tasks: BackgroundTasks,
    service: UploadService = Depends(get_upload_service),
    left_pickup: Optional[UploadFile] = File(None, description="Left side pickup image"),
    left_return: Optional[UploadFile] = File(None, description="Left side return image"),
    right_pickup: Optional[UploadFile] = File(None, description="Right side pickup image"),
    right_return: Optional[UploadFile] = File(None, description="Right side return image"),
    front_pickup: Optional[UploadFile] = File(None, description="Front side pickup image"),
    front_return: Optional[UploadFile] = File(None, description="Front side return image"),
    rear_pickup: Optional[UploadFile] = File(None, description="Rear side pickup image"),
    rear_return: Optional[UploadFile] = File(None, description="Rear side return image"),
):
    """Upload car images to start a car condition assessment.

    The client should send multipart/form-data with files whose form-field names
    follow the pattern `<side>-<phase>` where:
    - side: left, right, front, or rear
    - phase: pickup or return

    Example field names:
    - left-pickup, left-return
    - right-pickup, right-return
    - front-pickup, front-return
    - rear-pickup, rear-return

    Requirements:
    - At least one side must have both pickup and return images
    - At most four sides can be provided (left, right, front, rear)
    - Each image must be a valid image file (JPEG, PNG, GIF, WEBP, BMP, TIFF)
    - Maximum file size: 3 MB per image

    Returns:
        UploadResponse containing the generated upload_id (UUID) for tracking the assessment.

    P.S. Note: Disable 'Send empty value' for each field on Swagger UI to avoid validation errors
    """
    form = await request.form()
    upload_id = await service.handle_upload_form(form)

    # Immediately mark as pending and schedule background assessment.
    assessment = AssessmentResponse(
        status="pending",
        created_at = datetime.now(timezone.utc).isoformat()
    )
    set_assessment(upload_id, assessment)
    background_tasks.add_task(run_assessment, upload_id, service)

    return {"upload_id": upload_id}

@app.get("/assessment/{upload_id}", response_model=AssessmentResponse)
async def get_assessment_info(
        upload_id: str,
        background_tasks: BackgroundTasks,
        service: UploadService = Depends(get_upload_service),
):
    """
    Retrieve the current status and results of a car condition assessment.

    This endpoint tracks the progress of an assessment job and returns its current state.
    The assessment progresses through several stages: pending → in_progress → completed/failed.

    **Assessment Status Flow: **
    - `pending`: Assessment is queued for processing
    - `in_progress`: The AI models are actively analyzing the images
    - `completed`: Assessment finished successfully with results
    - `failed`: Assessment encountered an error or timed out

    **Automatic Recovery: **
    - If an assessment stays in `pending` for >5 minutes, it will be automatically retried
    - If an assessment stays in `in_progress` for >30 minutes, it will be marked as `failed` (timeout)

    **Usage Pattern: **
    1. Upload images via `/upload` endpoint and receive an `upload_id`
    2. Poll this endpoint periodically (recommended: every 5-10 seconds) to check status
    3. When status is `completed`, the response includes detailed damage assessment results

    Args:
        upload_id: The unique UUID returned from the /upload endpoint

    Returns:
        AssessmentResponse:
        ```
        - status: Current processing state
        - created_at: ISO timestamp when assessment was created
        - started_at: ISO timestamp when processing began (if started)
        - updated_at: ISO timestamp of last update (if any)
        - completed_at: ISO timestamp when assessment finished (if completed)
        - results: Detailed damage analysis per vehicle side (if completed)
        - summary: Human-readable assessment summary (if completed)
        - error: Error message if assessment failed
        ```

    Raises:
        404: Assessment not found for the provided upload_id
        500: Internal server error during processing

    Example Response (completed):
        ```json
        {
            "status": "completed",
            "created_at": "2025-11-27T10:00:00Z",
            "started_at": "2025-11-27T10:00:05Z",
            "completed_at": "2025-11-27T10:01:30Z",
            "results": {
                "left": {
                    "new_damages": ["scratch", "dent"],
                    "severity": "moderate",
                    "estimated_cost": 450.00
                }
            },
            "summary": "New damage detected on left side: moderate scratch and dent. Estimated repair cost: $450."
        }
        ```

    Example Response (in progress):
        ```json
        {
            "status": "in_progress",
            "created_at": "2025-11-27T10:00:00Z",
            "started_at": "2025-11-27T10:00:05Z"
        }
        ```
    """
    assessment = get_assessment(upload_id)

    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found for this upload_id",
        )

    created_at = datetime.fromisoformat(assessment.created_at)
    current_time = datetime.now(timezone.utc)

    if assessment.status == "pending":
        cutoff_time = current_time - timedelta(minutes=5)
        if created_at < cutoff_time:
            # Reattempt to execute the assessment if it's still pending for more than 5 minutes.
            # `run_assessment` handles updating the status to "in_progress".
            background_tasks.add_task(run_assessment, upload_id, service)

    if assessment.status == "in_progress":
        cutoff_time = current_time - timedelta(minutes=30)
        if created_at < cutoff_time:
            # Cancel the assessment if it's been running for too long (more than 30 minutes).
            assessment = AssessmentResponse(
                status="failed",
                updated_at=datetime.now(timezone.utc).isoformat(),
                error="Assessment timed out")
            set_assessment(upload_id, assessment)

    return assessment

