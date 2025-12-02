import os
import uuid
import mimetypes
from io import BytesIO

from PIL import Image
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import FormData

from .config import Settings
from .helpers import parse_and_validate_form
from .models import UploadedFileInfo
from .s3_client import S3Client


class UploadService:
    # Allowed file extensions
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}

    # Maximum file size in bytes (3 MB)
    MAX_FILE_SIZE = 3 * 1024 * 1024  # 3 MB

    def __init__(self, s3_client: S3Client, settings: Settings) -> None:
        self._s3 = s3_client
        self._settings = settings

    async def handle_upload_form(self, form: FormData) -> str:
        """Process the multipart form, upload files to S3, and return metadata.

        Expected form field names:
            `<side>-pickup` and `<side>-return`

        Where:
            side ∈ {front, rear, left, right}

        Requirements:
            - At least one side must have both pickup and return images.
            - At most four sides can be provided (front, rear, left, right).
        """
        groups = parse_and_validate_form(form)

        upload_id = str(uuid.uuid4())

        async def _upload_single_phase(side: str, phase: str) -> None:
            """Upload a single pickup/return file for one side."""
            upload_file = groups[side][phase]

            # Validate that the file is actually an image
            await self._validate_image_file(upload_file.file, upload_file.filename)

            ext = self._determine_file_extension(
                filename=upload_file.filename,
                content_type=getattr(upload_file, "content_type", None),
            )

            # Object key format: "<upload_id>/<side>-<phase>.<ext>"
            object_key = f"{upload_id}/{side}-{phase}{ext}"

            await self.upload_file_object(
                upload_file.file,
                object_key,
                getattr(upload_file, "content_type", None),
            )

        for car_side in groups.keys():
            await _upload_single_phase(car_side, "pickup")
            await _upload_single_phase(car_side, "return")

        return upload_id

    async def upload_file_object(self, file_object, key: str, content_type: str | None = None) -> UploadedFileInfo:
        """Upload a file object to S3 asynchronously."""
        await run_in_threadpool(
            self._s3.upload_file_object,
            file_object,
            key,
            content_type,
        )
        return UploadedFileInfo(key=key, url=self._get_file_url(key))

    def get_uploaded_files(self, upload_id: str) -> list[UploadedFileInfo]:
        uploaded_files = []
        keys_list = self._s3.list_keys(upload_id)

        for key in keys_list:
            if key == f"{upload_id}/":
                continue
            uploaded_files.append(UploadedFileInfo(key=key, url=self._get_file_url(key)))

        return uploaded_files

    def _get_file_url(self, key: str) -> str:
        return f"{self._settings.AWS_S3_ENDPOINT}/{self._settings.AWS_S3_BUCKET}/{key}"

    async def _validate_image_file(self, file_object, filename: str) -> None:
        """Validate that the uploaded file is actually an image.

        Performs multiple security checks:
        1. Extension validation
        2. Image library validation (attempts to open with Pillow)
        3. Basic image property verification

        Args:
            file_object: The file object to validate
            filename: The original filename

        Raises:
            ValueError: If the file is not a valid image
        """
        try:
            # Check file extension
            _, ext = os.path.splitext(filename or "")
            if ext.lower() not in self.ALLOWED_EXTENSIONS:
                raise ValueError(f"File extension '{ext}' is not allowed. Only image files are permitted.")

            # Read file content
            file_content = await run_in_threadpool(file_object.read)

            file_size = len(file_content)
            if file_size > self.MAX_FILE_SIZE:
                raise ValueError(
                    f"File size ({file_size / (1024 * 1024):.2f} MB) exceeds the maximum allowed size of 3 MB.")

            # Reset file pointer for later use
            await run_in_threadpool(file_object.seek, 0)

            # Validate with Pillow
            img = Image.open(BytesIO(file_content))
            img.verify()  # Verify it's a valid image

            # Re-open for additional checks (verify() closes the image)
            img = Image.open(BytesIO(file_content))

            if img.format not in ['JPEG', 'PNG', 'GIF', 'WEBP', 'BMP', 'TIFF']:
                raise ValueError(f"Unsupported image format: {img.format}")

        except Exception as e:
            raise ValueError(f"Invalid image file: {str(e)}")

    @staticmethod
    def _determine_file_extension(
        filename: str,
        content_type: str | None,
    ) -> str:
        """Determine file extension from the filename or content type."""
        _, ext = os.path.splitext(filename or "")
        if ext:
            return ext

        if content_type:
            guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
            if guessed:
                return guessed

        return ""
