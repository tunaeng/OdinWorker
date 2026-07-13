import uuid
from unittest.mock import patch

from django.test import TestCase
from moto import mock_aws
from storages.backends.s3boto3 import S3Boto3Storage

from parser import storage as storage_module

_bucket_created = False


def _ensure_bucket():
    global _bucket_created
    if not _bucket_created:
        import boto3
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="test-bucket")
        _bucket_created = True


def _make_storage():
    _ensure_bucket()
    return S3Boto3Storage(
        access_key="testing",
        secret_key="testing",
        bucket_name="test-bucket",
        endpoint_url=None,
        region_name="us-east-1",
    )


class StorageUtilsTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._mock = mock_aws()
        cls._mock.start()
        _ensure_bucket()

    @classmethod
    def tearDownClass(cls):
        cls._mock.stop()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self._storage = _make_storage()
        self._patchers = [
            patch.object(storage_module, "default_storage", self._storage),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        super().tearDown()

    def test_s3_upload_and_read(self):
        key = f"utils/{uuid.uuid4()}.bin"
        content = b"\x00\x01\x02\x03"
        storage_module.s3_upload(key, content)
        self.assertTrue(storage_module.s3_exists(key))
        self.assertEqual(storage_module.s3_read(key), content)

    def test_s3_read_text(self):
        key = f"utils/{uuid.uuid4()}.txt"
        storage_module.s3_upload(key, b"line1\nline2\n")
        self.assertEqual(storage_module.s3_read_text(key), "line1\nline2\n")

    def test_upload_with_hash_deduplication(self):
        content = b"dedup content"
        sha1, key1 = storage_module.upload_with_hash("dedup", ".txt", content)
        sha2, key2 = storage_module.upload_with_hash("dedup", ".txt", content)
        self.assertEqual(key1, key2)
        self.assertEqual(sha1, sha2)

    def test_upload_with_hash_different_content(self):
        sha1, key1 = storage_module.upload_with_hash("diff", ".txt", b"content a")
        sha2, key2 = storage_module.upload_with_hash("diff", ".txt", b"content b")
        self.assertNotEqual(key1, key2)

    def test_s3_exists_missing(self):
        self.assertFalse(storage_module.s3_exists(f"nonexistent/{uuid.uuid4()}"))

    def test_s3_delete(self):
        key = f"utils/{uuid.uuid4()}.txt"
        storage_module.s3_upload(key, b"delete me")
        self.assertTrue(storage_module.s3_exists(key))
        storage_module.s3_delete(key)
        self.assertFalse(storage_module.s3_exists(key))

    def test_direct_storage_upload(self):
        from django.core.files.base import ContentFile

        key = f"direct/{uuid.uuid4()}.txt"
        path = self._storage.save(key, ContentFile(b"hello"))
        self.assertTrue(self._storage.exists(path))
        self.assertEqual(self._storage.open(path).read(), b"hello")
