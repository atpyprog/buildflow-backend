# Copyright (c) 2025 Alexandre Tavares
# Licensed under the Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# See the LICENSE file in the project root for more information. __future__ import annotations
from typing import Any, List, Optional
from uuid import UUID
from datetime import datetime
from pathlib import Path as FsPath
import secrets
import time
from fastapi import (
    APIRouter,
    Depends,
    Path as PathParam,
    HTTPException,
    Query,
    UploadFile,
    File,
)
from pydantic import BaseModel, HttpUrl
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.core.config import settings

"""
Gerenciamento de fotos vinculadas ao progresso diário.


- `POST /{progress_id}/photos` anexa via URL (simulado).
- `POST /{progress_id}/photos/upload` upload real (JPEG/PNG/WebP) em `/uploads`.
- `GET /{progress_id}/photos` lista fotos.
- `DELETE /photos/{photo_id}` remove registro e arquivo físico (se existir).
"""

router = APIRouter()


class PhotoIn(BaseModel):
    url: HttpUrl
    caption: Optional[str] = None

class PhotoOut(BaseModel):
    id: UUID
    progress_id: UUID
    url: str
    caption: Optional[str] = None
    created_at: Optional[datetime] = None


def _safe_filename(content_type: str) -> str:
    ext_map = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    ext = ext_map.get(content_type, "bin")
    ts = int(time.time() * 1000)
    rand = secrets.token_hex(6)
    return f"{ts}_{rand}.{ext}"

async def _progress_exists(db: AsyncSession, pid: str) -> bool:
    res = await db.execute(text("SELECT 1 FROM daily_progress WHERE id = CAST(:pid AS uuid)"), {"pid": pid})
    return bool(res.scalar())

async def _photo_row(db: AsyncSession, photo_id: str) -> dict[str, Any] | None:
    res = await db.execute(text("SELECT * FROM progress_photo WHERE id = CAST(:id AS uuid)"), {"id": photo_id})
    row = res.mappings().first()
    return dict(row) if row else None

#Simulação de inserção de foto.
@router.post("/{progress_id}/photos", response_model=PhotoOut, summary="Anexar foto (por URL) a um progresso")
async def add_photo(
    payload: PhotoIn,
    progress_id: str = PathParam(..., description="UUID do daily_progress"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not await _progress_exists(db, progress_id):
        raise HTTPException(status_code=404, detail="Progress not found")

    sql = text("""
        INSERT INTO progress_photo (progress_id, url, caption)
        VALUES (CAST(:pid AS uuid), :url, :caption)
        RETURNING *;
    """)
    res = await db.execute(sql, {"pid": progress_id, "url": str(payload.url), "caption": payload.caption})
    row = res.mappings().first()
    if not row:
        raise HTTPException(status_code=500, detail="Falha ao anexar foto.")
    await db.commit()
    return dict(row)


@router.get("/{progress_id}/photos", response_model=List[PhotoOut], summary="Listar fotos de um progresso")
async def list_photos(
    progress_id: str = PathParam(..., description="UUID do daily_progress"),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> List[dict[str, Any]]:
    if not await _progress_exists(db, progress_id):
        raise HTTPException(status_code=404, detail="Progress not found")

    sql = text("""
        SELECT * FROM progress_photo
        WHERE progress_id = CAST(:pid AS uuid)
        ORDER BY created_at
        LIMIT :limit OFFSET :offset;
    """)
    res = await db.execute(sql, {"pid": progress_id, "limit": limit, "offset": offset})
    return [dict(row) for row in res.mappings().all()]

#Inserção real da foto!
@router.post("/{progress_id}/photos/upload", response_model=PhotoOut, summary="Upload de foto real (arquivo)")
async def upload_photo(
    progress_id: str = PathParam(..., description="UUID do daily_progress"),
    file: UploadFile = File(..., description="Imagem (image/jpeg, image/png, image/webp)"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not await _progress_exists(db, progress_id):
        raise HTTPException(status_code=404, detail="Progress not found")

    if file.content_type not in settings.ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported media type: {file.content_type}")

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    progress_dir = FsPath(settings.UPLOAD_DIR) / progress_id
    progress_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(file.content_type)
    disk_path = progress_dir / filename
    size = 0

    with disk_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)  # 1MB
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                try:
                    disk_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise HTTPException(status_code=413, detail=f"File too large (>{settings.MAX_UPLOAD_MB}MB)")
            out.write(chunk)

    # URL pública servida pelo StaticFiles montado em /uploads
    public_url = f"/uploads/{progress_id}/{filename}"

    sql = text("""
        INSERT INTO progress_photo (progress_id, url, file_path, caption)
        VALUES (CAST(:pid AS uuid), :url, :file_path, :caption)
        RETURNING *;
    """)
    params = {"pid": progress_id, "url": public_url, "file_path": str(disk_path), "caption": None}
    res = await db.execute(sql, params)
    row = res.mappings().first()
    if not row:
        try:
            disk_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Falha ao registrar foto no banco.")
    await db.commit()
    return dict(row)


@router.delete("/photos/{photo_id}", status_code=204, summary="Excluir foto (remove arquivo e registro)")
async def delete_photo(
    photo_id: str = PathParam(..., description="UUID da foto"),
    db: AsyncSession = Depends(get_db),
) -> None:
    row = await _photo_row(db, photo_id)
    if not row:
        return

    file_path = row.get("file_path")
    if file_path:
        try:
            FsPath(file_path).unlink(missing_ok=True)
        except Exception:
            pass

    await db.execute(text("DELETE FROM progress_photo WHERE id = CAST(:id AS uuid)"), {"id": photo_id})
    await db.commit()
    return
