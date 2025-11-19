from io import BytesIO
import cv2
from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.concurrency import run_in_threadpool

from .ai_assessment.main import assess_car_on_return, draw_bounding_box
from .config import Settings
from .s3_client import S3Client
from .models import UploadResponse, UploadedFileInfo
from .upload_service import UploadService

app = FastAPI(title="Car Damage Assessment API")

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
    service: UploadService = Depends(get_upload_service),
):
    """Upload matched pickup/return images.

    The client should send multipart/form-data with files whose form-field names
    follow the pattern `<N>-pickup` and `<N>-return` (N is an integer).

    Returns:
        UploadResponse containing the generated upload_id (UUID) and uploaded files' URLs.
    """
    form = await request.form()
    response = await service.handle_upload_form(form)

    assessment = assess_car_on_return(response.files)

    for result, image in assessment:
        annotated_image = await draw_bounding_box(image.url, result)

        # Encode annotated image (NumPy array) as JPEG and wrap in BytesIO
        success, buffer = cv2.imencode(".jpg", annotated_image)
        if not success:
            raise RuntimeError("Failed to encode annotated image as JPEG")

        bytes_io = BytesIO(buffer.tobytes())
        bytes_io.seek(0)

        uploaded_file = await service.upload_file_object(
            bytes_io,
            f"{image.key.split('.')[0]}-annotated.jpg",
            content_type="image/jpeg",
        )
        response.files.append(uploaded_file)

    return response


@app.get("/images/{upload_id}")
async def list_images(upload_id: str):
    """List images uploaded under the given upload_id and return their URLs."""
    prefix = f"{upload_id}/"

    # list_keys is blocking; run in the threadpool
    keys = await run_in_threadpool(s3.list_keys, prefix)
    if not keys or len(keys) == 1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No images found for this upload_id")

    files = [
        UploadedFileInfo(key=k, url=f"{settings.AWS_S3_ENDPOINT}/{settings.AWS_S3_BUCKET}/{k}") for k in keys
    ]
    return {"upload_id": upload_id, "files": files[1::]}
