import hashlib

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def s3_upload(key: str, content: bytes) -> str:
    path = default_storage.save(key, ContentFile(content))
    return path


def s3_exists(key: str) -> bool:
    return default_storage.exists(key)


def s3_delete(key: str) -> None:
    default_storage.delete(key)


def s3_read(key: str) -> bytes:
    return default_storage.open(key).read()


def s3_read_text(key: str) -> str:
    return default_storage.open(key).read().decode("utf-8")


def upload_with_hash(prefix: str, ext: str, content: bytes) -> tuple[str, str]:
    sha256 = hashlib.sha256(content).hexdigest()
    key = f"{prefix}/{sha256}{ext}"
    if not s3_exists(key):
        s3_upload(key, content)
    return sha256, key
