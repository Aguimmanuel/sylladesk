"""Storage seam: feature apps never touch disks or blobs directly.

Two backends behind one interface:
- DBStorage   - Postgres bytea via core.FileBlob (default).
- DiskStorage - local disk files/{course}/{kind}/{uuid}.{ext}.
Switching is a FILES_BACKEND setting; no feature code changes.
"""
import hashlib
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from .models import File, FileBlob


@dataclass(frozen=True)
class SavedFile:
    file: File


def _sha256_of(chunks) -> str:
    h = hashlib.sha256()
    for chunk in chunks:
        h.update(chunk)
    return h.hexdigest()


def build_key(course_id: int | None, kind: str, original_name: str) -> str:
    ext = ""
    if "." in original_name:
        ext = "." + original_name.rsplit(".", 1)[1].lower()[:16]
    return f"{course_id or 'x'}/{kind}/{uuid.uuid4().hex}{ext}"


class StorageBackend(ABC):
    @abstractmethod
    def save(self, uploaded, *, course_id, kind, uploaded_by) -> File: ...

    @abstractmethod
    def open(self, file: File):
        """Return a file-like object of raw bytes."""

    @abstractmethod
    def delete(self, file: File) -> None: ...


class DBStorage(StorageBackend):
    @transaction.atomic
    def save(self, uploaded, *, course_id, kind, uploaded_by):
        key = build_key(course_id, kind, uploaded.name)
        data = uploaded.read()
        blob = FileBlob.objects.create(key=key, data=data)
        f = File.objects.create(
            storage_key=key,
            original_name=uploaded.name[:255],
            mime=getattr(uploaded, "content_type", "") or "",
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            uploaded_by=uploaded_by,
        )
        return f

    def open(self, file: File):
        import io

        blob = FileBlob.objects.get(key=file.storage_key)
        return io.BytesIO(bytes(blob.data))

    def delete(self, file: File):
        FileBlob.objects.filter(key=file.storage_key).delete()
        file.delete()


class DiskStorage(StorageBackend):
    def _path(self, file: File):
        root = settings.FILES_DISK_ROOT
        return root / file.storage_key

    def save(self, uploaded, *, course_id, kind, uploaded_by):
        key = build_key(course_id, kind, uploaded.name)
        path = settings.FILES_DISK_ROOT / key
        path.parent.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        size = 0
        with path.open("wb") as out:
            for chunk in uploaded.chunks():
                out.write(chunk)
                h.update(chunk)
                size += len(chunk)
        return File.objects.create(
            storage_key=key,
            original_name=uploaded.name[:255],
            mime=getattr(uploaded, "content_type", "") or "",
            size_bytes=size,
            sha256=h.hexdigest(),
            uploaded_by=uploaded_by,
        )

    def open(self, file: File):
        return self._path(file).open("rb")

    def delete(self, file: File):
        path = self._path(file)
        if path.exists():
            path.unlink()
        file.delete()


_BACKENDS = {"db": DBStorage, "disk": DiskStorage}


def get_storage() -> StorageBackend:
    return _BACKENDS[settings.FILES_BACKEND]()
