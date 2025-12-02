import re
from typing import Any

from fastapi import HTTPException, status
from starlette.datastructures import FormData

# validate form keys like `front-pickup` or `front-return`
KEY_REGEX = re.compile(r"^(?P<side>front|rear|left|right)-(?P<phase>pickup|return)$")

def parse_and_validate_form(form: FormData) -> dict[str, dict[str, Any]]:
    """Group files by side and validate form constraints."""
    # groups[side] = {"pickup": file, "return": file}
    groups: dict[str, dict[str, Any]] = {}

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
            detail=(
                "No images found in request. "
                "Provide at least one complete side with 'pickup' and 'return' images."
            ),
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

    # At most four sides: front, rear, left, right
    if len(groups) > 4:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Too many sides provided. A maximum of 4 sides is allowed: "
                "front, rear, left, right."
            ),
        )

    return groups
