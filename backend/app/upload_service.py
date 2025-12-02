import os
import re
import uuid
import mimetypes
from typing import Dict, Any, Tuple

from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import FormData

from .config import Settings
from .models import UploadResponse, UploadedFileInfo
from .s3_client import S3Client


# validate form keys like `1-pickup` or `1-return`
KEY_REGEX = re.compile(r"^(?P<id>\d+)-(?P<side>pickup|return)$")


class UploadService:
    def __init__(self, s3_client: S3Client, settings: Settings) -> None:
        self._s3 = s3_client
        self._settings = settings

    async def handle_upload_form(self, form: FormData) -> UploadResponse:
        """Process the multipart form, upload files to S3, and return metadata."""
        groups: Dict[str, Dict[str, Any]] = {}

        # Collect upload files grouped by numeric id
        for key, value in form.items():
            # Only handle file uploads; skip non-file fields
            if not hasattr(value, "filename") or value.filename == "":
                continue

            match = KEY_REGEX.match(key)
            if not match:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid form field name: '{key}'. Expected pattern '<N>-pickup' or '<N>-return'",
                )

            group_id = match.group("id")
            side = match.group("side")

            groups.setdefault(group_id, {})[side] = value

        # Ensure each group has both pickup and return
        incomplete = [gid for gid, pair in groups.items() if not ("pickup" in pair and "return" in pair)]
        if incomplete:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"The following groups are incomplete (both pickup & return required): {incomplete}",
            )

        upload_id = str(uuid.uuid4())
        uploaded_files_info: list[UploadedFileInfo] = []

        for gid, pair in groups.items():
            side_upload: dict[str, UploadedFileInfo] = {}

            for side_name in ("pickup", "return"):
                upload_file = pair[side_name]

                # Determine file extension
                _, ext = os.path.splitext(upload_file.filename)
                if not ext:
                    ct = getattr(upload_file, "content_type", None)
                    if ct:
                        guessed = mimetypes.guess_extension(ct.split(";")[0].strip())
                        ext = guessed or ""

                object_key = f"{upload_id}/{gid}-{side_name}{ext}"

                await run_in_threadpool(
                    self._s3.upload_file_object,
                    upload_file.file,
                    object_key,
                    getattr(upload_file, "content_type", None),
                )

                url = f"{self._settings.AWS_S3_ENDPOINT}/{self._settings.AWS_S3_BUCKET}/{object_key}"
                side_upload[side_name] = UploadedFileInfo(key=object_key, url=url)

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
