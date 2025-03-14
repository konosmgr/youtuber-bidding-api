"""
Storage backends for S3 media storage.
This file is needed for backward compatibility as some code references core.storage_backends
"""

from auctions.storage import DebugS3Storage

# Re-export the storage class from auctions.storage for backward compatibility
class S3MediaStorage(DebugS3Storage):
    """S3 storage class for media files"""
    location = ""
