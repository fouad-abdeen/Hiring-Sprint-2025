from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request, HTTPException, status, Depends, BackgroundTasks
from starlette.middleware.cors import CORSMiddleware

from .assessment_repository import set_assessment, get_assessment
from .config import Settings
from .s3_client import S3Client
from .models import AssessmentResponse, UploadResponse
from .assessment_service import run_assessment
from .upload_service import UploadService

app = FastAPI(title="Car Damage Assessment API")

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
async def upload_images(
    request: Request,
    background_tasks: BackgroundTasks,
    service: UploadService = Depends(get_upload_service),
):
    """Upload matched pickup/return images.

    The client should send multipart/form-data with files whose form-field names
    follow the pattern `<N>-pickup` and `<N>-return` (N is an integer).

    Returns:
        UploadResponse containing the generated upload_id (UUID) and uploaded files' URLs.
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
    Return assessment info for a given upload_id
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
        cutoff_time = current_time - timedelta(minutes=10)
        if created_at < cutoff_time:
            # Reattempt to execute the assessment if it's still pending for more than 10 minutes.
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

