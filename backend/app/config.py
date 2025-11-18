from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

class Settings(BaseSettings):
    AWS_S3_BUCKET: str = Field(..., description="Target S3 bucket name")
    AWS_S3_REGION: str = Field(..., description="Target S3 region")
    AWS_S3_ENDPOINT: str = Field(..., description="Target S3 endpoint URL")
    AWS_ACCESS_KEY_ID: str = Field(..., description="AWS access key ID")
    AWS_SECRET_ACCESS_KEY: str = Field(..., description="AWS secret access key")

    ROBOFLOW_API_URL: str = Field(..., description="Roboflow API URL")
    ROBOFLOW_API_KEY: str = Field(..., description="Roboflow API key")

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
    )
