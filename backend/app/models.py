from typing import Any, Optional
from pydantic import BaseModel, Field


class UploadedFileInfo(BaseModel):
    key: str = Field(..., description="S3 key of the uploaded file")
    url: str = Field(..., description="url to access the file")


class UploadResponse(BaseModel):
    upload_id: str = Field(..., description="UUID for this upload set")


class AssessmentResponse(BaseModel):
    status: str = Field(..., description="Status of the assessment")
    created_at: Optional[str] = Field(default=None, description="Timestamp of the assessment creation")
    started_at: Optional[str] = Field(default=None, description="Timestamp of the assessment start")
    updated_at: Optional[str] = Field(default=None, description="Timestamp of the last assessment update")
    completed_at: Optional[str] = Field(default=None, description="Timestamp of the assessment completion")
    results: Optional[dict[str, dict[str, Any]]] = Field(default=None, description="Assessment results")
    summary: Optional[str] = Field(default=None, description="Assessment summary")
    error: Optional[str] = Field(default=None, description="Error message if any")

    # class Config:
    #     # Allow creating instances from dictionaries with extra fields ignored
    #     extra = "ignore"
