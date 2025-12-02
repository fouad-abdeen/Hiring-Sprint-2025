from typing import TypedDict, Optional

from fastapi import UploadFile
from pydantic import BaseModel, Field

class UploadedFileInfo(BaseModel):
    key: str = Field(..., description="S3 key of the uploaded file")
    url: str = Field(..., description="url to access the file")


class UploadResponse(BaseModel):
    upload_id: str = Field(..., description="UUID for this upload set")
    files: list[UploadedFileInfo] = Field(..., description="List of uploaded files with their URLs")

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
