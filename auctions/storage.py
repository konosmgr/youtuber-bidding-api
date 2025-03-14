from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage
import boto3
import logging
from PIL import Image
from io import BytesIO

logger = logging.getLogger(__name__)

class DebugS3Storage(S3Boto3Storage):
    """Storage class with image optimization before upload"""
    location = ""

    def _save(self, name, content):
        """Optimize images before saving to S3"""
        try:
            # Check if this is an image file
            if self._is_image_file(name):
                # Optimize the image
                optimized_content = self._optimize_image(content)
                if optimized_content:
                    content = optimized_content
            
            # Continue with the standard saving process
            content.seek(0)
            file_content = content.read()

            # Create boto3 client
            s3 = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )

            # Upload with appropriate content type
            s3.put_object(
                Bucket=self.bucket_name,
                Key=name,
                Body=file_content,
                ContentType=getattr(
                    content, "content_type", "application/octet-stream"
                ),
                CacheControl="max-age=604800",  # 1 week cache
            )

            # Return the name for the database record
            return name

        except Exception as e:
            logger.error(f"Error in _save: {str(e)}")
            raise

    def _is_image_file(self, name):
        """Check if the file is an image based on extension"""
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        return any(name.lower().endswith(ext) for ext in image_extensions)

    def _optimize_image(self, content):
        """Optimize image content while maintaining quality"""
        try:
            # Open image with PIL
            img = Image.open(content)
            
            # If image is very large, resize it
            max_dimension = 1600  # Max width or height
            if img.width > max_dimension or img.height > max_dimension:
                # Calculate new dimensions maintaining aspect ratio
                if img.width > img.height:
                    new_width = max_dimension
                    new_height = int(img.height * (max_dimension / img.width))
                else:
                    new_height = max_dimension
                    new_width = int(img.width * (max_dimension / img.height))
                
                # Resize the image
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Determine format
            format = img.format
            
            # Create new BytesIO object for the optimized image
            optimized_content = BytesIO()
            
            # Save the image with optimized settings
            if format == 'JPEG':
                img.save(optimized_content, format='JPEG', quality=85, optimize=True)
            elif format == 'PNG':
                img.save(optimized_content, format='PNG', optimize=True)
            else:
                # For other formats, maintain original
                img.save(optimized_content, format=format)
            
            # Reset position to start
            optimized_content.seek(0)
            
            # Copy content_type from original
            if hasattr(content, 'content_type'):
                optimized_content.content_type = content.content_type
            
            return optimized_content
            
        except Exception as e:
            logger.warning(f"Image optimization failed: {str(e)}. Using original image.")
            return None