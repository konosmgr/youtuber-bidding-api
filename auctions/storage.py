from storages.backends.s3boto3 import S3Boto3Storage
import boto3
import logging

logger = logging.getLogger(__name__)


class DebugS3Storage(S3Boto3Storage):
    """Storage class that uses direct boto3 upload to ensure files are saved"""

    location = ""

    def _save(self, name, content):
        """Override _save to use direct boto3 upload"""
        try:
            # Get content
            content.seek(0)
            file_content = content.read()

            # Create boto3 client
            s3 = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )

            # Upload directly using boto3
            s3.put_object(
                Bucket=self.bucket_name,
                Key=name,
                Body=file_content,
                ContentType=getattr(
                    content, "content_type", "application/octet-stream"
                ),
            )

            # Return the name for the database record
            return name

        except Exception as e:
            logger.error(f"Error in _save: {str(e)}")
            raise
