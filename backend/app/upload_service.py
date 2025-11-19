import os
import re
import uuid
import mimetypes
from typing import Dict, Any

from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import FormData

from .config import Settings
from .models import UploadResponse, UploadedFileInfo
from .s3_client import S3Client


# validate form keys like `front-pickup` or `front-return`
KEY_REGEX = re.compile(r"^(?P<side>front|rear|left|right)-(?P<phase>pickup|return)$")


class UploadService:
    def __init__(self, s3_client: S3Client, settings: Settings) -> None:
        self._s3 = s3_client
        self._settings = settings

    async def handle_upload_form(self, form: FormData) -> UploadResponse:
        """Process the multipart form, upload files to S3, and return metadata.

        Expected form field names:
            `<side>-pickup` and `<side>-return`

        Where:
            side ∈ {front, rear, left, right}

        Requirements:
            - At least one side must have both pickup & return images.
            - At most four sides can be provided (front, rear, left, right).
        """
        # groups[side] = {"pickup": file, "return": file}
        groups: Dict[str, Dict[str, Any]] = {}

        # Collect upload files grouped by side name
        for key, value in form.items():
            # Only handle file uploads; skip non-file fields
            if not hasattr(value, "filename") or value.filename == "":
                continue

            match = KEY_REGEX.match(key)
            if not match:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"Invalid form field name: '{key}'. "
                        "Expected pattern '<side>-pickup' or '<side>-return' "
                        "where side is one of: front, rear, left, right."
                    ),
                )

            side = match.group("side")
            phase = match.group("phase")  # "pickup" | "return"

            groups.setdefault(side, {})[phase] = value

        if not groups:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No images found in request. "
                       "Provide at least one complete side with 'pickup' and 'return' images.",
            )

        # Ensure each side that appears has both pickup and return
        incomplete_sides = [
            side for side, phases in groups.items()
            if not ("pickup" in phases and "return" in phases)
        ]
        if incomplete_sides:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "The following sides are incomplete (both pickup & return required): "
                    f"{incomplete_sides}"
                ),
            )

        # At least one complete side must be present
        if len(groups) == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "At least one complete side is required. "
                    "Each complete side must include both '<side>-pickup' and '<side>-return'."
                ),
            )

        # At most four sides: front, rear, left, right
        if len(groups) > 4:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Too many sides provided. A maximum of 4 sides is allowed: front, rear, left, right.",
            )

        upload_id = str(uuid.uuid4())
        uploaded_files_info: list[UploadedFileInfo] = []

        # For each side, upload pickup then return image
        for side, phases in groups.items():
            side_upload: dict[str, UploadedFileInfo] = {}

            for phase in ("pickup", "return"):
                upload_file = phases[phase]

                # Determine file extension
                _, ext = os.path.splitext(upload_file.filename)
                if not ext:
                    ct = getattr(upload_file, "content_type", None)
                    if ct:
                        guessed = mimetypes.guess_extension(ct.split(";")[0].strip())
                        ext = guessed or ""

                # Object key format: "<upload_id>/<side>-<phase>.<ext>"
                object_key = f"{upload_id}/{side}-{phase}{ext}"

                await run_in_threadpool(
                    self._s3.upload_file_object,
                    upload_file.file,
                    object_key,
                    getattr(upload_file, "content_type", None),
                )

                url = f"{self._settings.AWS_S3_ENDPOINT}/{self._settings.AWS_S3_BUCKET}/{object_key}"
                side_upload[phase] = UploadedFileInfo(key=object_key, url=url)

            uploaded_files_info.append(side_upload["pickup"])
            uploaded_files_info.append(side_upload["return"])

        return UploadResponse(upload_id=upload_id, files=uploaded_files_info)

    async def upload_file_object(self, file_object, key: str, content_type: str | None = None) -> UploadedFileInfo:
        """Upload a file object to S3 asynchronously."""
        await run_in_threadpool(
            self._s3.upload_file_object,
            file_object,
            key,
            content_type,
        )
        return UploadedFileInfo(key=key, url=f"{self._settings.AWS_S3_ENDPOINT}/{self._settings.AWS_S3_BUCKET}/{key}")
