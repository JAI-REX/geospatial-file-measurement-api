from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.services.geospatial import GeospatialError, process_file
from app.store import FILES, LOCK, UPLOAD_DIR

router = APIRouter(prefix="/api/files", tags=["files"])

ALLOWED = {".kml", ".zip"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def summary(record: dict) -> dict:
    return {
        key: record.get(key)
        for key in (
            "id",
            "filename",
            "feature_count",
            "crs",
            "measurement_crs",
            "status",
            "error",
        )
        if key in record
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload_file(file: UploadFile = File(...)):
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED:
        raise HTTPException(
            status_code=400,
            detail="Only .kml or .zip Shapefile archives are supported.",
        )

    file_id = uuid.uuid4().hex
    work_dir = UPLOAD_DIR / file_id
    work_dir.mkdir(parents=True, exist_ok=True)
    saved_path = work_dir / filename

    try:
        total = 0
        with saved_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 50 MB upload limit.",
                    )
                output.write(chunk)

        result = process_file(saved_path, work_dir / "work")
        record = {
            "id": file_id,
            "filename": filename,
            "feature_count": result["feature_count"],
            "crs": result["crs"],
            "measurement_crs": result["measurement_crs"],
            "status": "COMPLETED",
            "features": result["features"],
            "measurements": result["measurements"],
        }
        with LOCK:
            FILES[file_id] = record
        return summary(record)

    except HTTPException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    except GeospatialError as exc:
        record = {
            "id": file_id,
            "filename": filename,
            "status": "FAILED",
            "error": str(exc),
        }
        with LOCK:
            FILES[file_id] = record
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="Unexpected processing error.") from exc
    finally:
        await file.close()


@router.get("/{file_id}/")
def file_information(file_id: str):
    record = FILES.get(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found.")
    return summary(record)


@router.get("/{file_id}/measurements/")
def measurements(file_id: str):
    record = FILES.get(file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found.")
    if record.get("status") != "COMPLETED":
        raise HTTPException(status_code=409, detail="File processing did not complete successfully.")

    return {
        "file_id": file_id,
        "source_crs": record.get("crs"),
        "measurement_crs": record.get("measurement_crs"),
        "features": record["features"],
        "measurements": record["measurements"],
    }
