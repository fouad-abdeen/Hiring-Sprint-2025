from typing import Any, Optional
from pydantic import BaseModel, Field


class UploadedFileInfo(BaseModel):
    key: str = Field(..., description="S3 key of the uploaded file")
    url: str = Field(..., description="url to access the file")


class UploadResponse(BaseModel):
    upload_id: str = Field(..., description="UUID for this upload set")


class AssessmentResponse(BaseModel):
    status: str = Field(..., description="Current assessment status: 'pending', 'in_progress', 'completed', or 'failed'")
    created_at: Optional[str] = Field(default=None, description="ISO 8601 timestamp when the assessment was created")
    started_at: Optional[str] = Field(default=None, description="ISO 8601 timestamp when the assessment was started")
    updated_at: Optional[str] = Field(default=None, description="ISO 8601 timestamp when the assessment was updated")
    completed_at: Optional[str] = Field(default=None, description="ISO 8601 timestamp when the assessment was completed")
    results: Optional[dict[str, dict[str, Any]]] = Field(
        default=None,
        description="Detailed damage assessment results per vehicle side (left, right, front, rear)." +
                    "Each side contains type and severity for each detected damage (if any)."
                    "Each side contains type and severity for each detected damage (if any)."
    )
    summary: Optional[str] = Field(default=None, description="Human-readable summary of the assessment findings")
    error: Optional[str] = Field(default=None, description="Error message if the assessment failed or timed out")


