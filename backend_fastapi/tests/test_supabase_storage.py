from io import BytesIO

import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody

from scripts.supabase_storage import StorageMigrationError, copy_object


class MemoryBucket:
    def __init__(self, contents: dict[str, bytes]) -> None:
        self.contents = contents
        self.writes = 0

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        if Key not in self.contents:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        data = self.contents[Key]
        return {"Body": StreamingBody(BytesIO(data), len(data)), "ContentType": "application/pdf"}

    def put_object(self, *, Bucket: str, Key: str, Body, IfNoneMatch: str, ContentType: str) -> None:
        assert ContentType == "application/pdf"
        assert IfNoneMatch == "*" and Key not in self.contents
        self.contents[Key] = Body.read()
        self.writes += 1


def test_verified_object_copy_is_idempotent():
    key = "documentos/prueba.pdf"
    origin = MemoryBucket({key: b"fixture"})
    destination = MemoryBucket({})
    copy_object(origin, destination, "origen", "destino", key)
    copy_object(origin, destination, "origen", "destino", key)
    assert destination.contents == origin.contents
    assert destination.writes == 1


def test_existing_different_object_is_preserved():
    key = "documentos/prueba.pdf"
    origin = MemoryBucket({key: b"origen"})
    destination = MemoryBucket({key: b"destino"})
    with pytest.raises(StorageMigrationError, match="contenido distinto"):
        copy_object(origin, destination, "origen", "destino", key)
    assert destination.contents[key] == b"destino" and destination.writes == 0

