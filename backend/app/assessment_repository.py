import json
from typing import Optional

import redis

from .config import Settings
from .models import AssessmentResponse


settings = Settings()
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD or None,
    db=0,
)


def set_assessment(upload_id: str, assessment: AssessmentResponse) -> None:
    existing_assessment = redis_client.hget(upload_id, "status")
    assessment_dict = assessment.model_dump(exclude_none=True)

    if existing_assessment:
        for key, value in assessment_dict.items():
            if isinstance(value, dict):
                value = json.dumps(value)
            redis_client.hset(upload_id, key, value)
    else:
        redis_client.hset(upload_id, mapping=assessment_dict)
        # Set assessment to expire after three days
        redis_client.expire(upload_id, 60 * 60 * 24 * 3)

def get_assessment(upload_id: str) -> Optional[AssessmentResponse]:
    data = redis_client.hgetall(upload_id)
    if not data:
        return None

    decoded_data = {
        key.decode('utf-8'): value.decode('utf-8') if isinstance(value, bytes) else value
        for key, value in data.items()
    }
    if 'results' in decoded_data and isinstance(decoded_data['results'], str):
        decoded_data['results'] = json.loads(decoded_data['results'])

    return AssessmentResponse(**decoded_data)
