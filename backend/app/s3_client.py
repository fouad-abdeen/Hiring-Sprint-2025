from typing import List, Optional
import boto3


class S3Client:
    def __init__(self, bucket: str, region: str, endpoint_url: str, access_key_id: str, secret_access_key: str):
        session = boto3.session.Session()
        self._client = session.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key
        )
        self.bucket = bucket
        self.configure_lifecycle_policy()

    def configure_lifecycle_policy(self):
        """Configure S3 lifecycle policy to auto-delete objects after 3 days"""
        lifecycle_policy = {
            'Rules': [
                {
                    'ID': 'DeleteAfter3Days',
                    'Status': 'Enabled',
                    'Filter': {'Prefix': ''},  # Apply to all objects
                    'Expiration': {
                        'Days': 3
                    }
                }
            ]
        }

        self._client.put_bucket_lifecycle_configuration(
            Bucket=self.bucket,
            LifecycleConfiguration=lifecycle_policy
        )

    def upload_file_object(self, file_object, key: str, content_type: Optional[str] = None) -> None:
        extra_args = { "ContentType": content_type } if content_type else {}
        # boto3 is synchronous; callers should run this in a threadpool if used from async code
        self._client.upload_fileobj(Fileobj=file_object, Bucket=self.bucket, Key=key, ExtraArgs=extra_args)

    def list_keys(self, prefix: str) -> List[str]:
        paginator = self._client.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys
