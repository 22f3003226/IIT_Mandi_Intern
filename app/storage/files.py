import shutil
from pathlib import Path
from typing import BinaryIO


def save_upload(storage_dir: str, job_id: str, filename: str, file_obj: BinaryIO) -> str:
    safe_name = Path(filename).name
    if not safe_name or safe_name in (".", ".."):
        raise ValueError(f"Invalid upload filename: {filename!r}")
    dest_dir = Path(storage_dir) / job_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / safe_name
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file_obj, f)
    return str(dest_path)


def save_result_json(storage_dir: str, job_id: str, content: str) -> str:
    dest_dir = Path(storage_dir) / job_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "DocumentKnowledgeExtract.json"
    dest_path.write_text(content, encoding="utf-8")
    return str(dest_path)


def save_plan_result_json(storage_dir: str, job_id: str, content: str) -> str:
    dest_dir = Path(storage_dir) / job_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "TeachingPlan.json"
    dest_path.write_text(content, encoding="utf-8")
    return str(dest_path)


def save_publish_result_json(storage_dir: str, job_id: str, content: str) -> str:
    dest_dir = Path(storage_dir) / job_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "TeacherKnowledgePackage.json"
    dest_path.write_text(content, encoding="utf-8")
    return str(dest_path)


def save_publish_pdf(storage_dir: str, job_id: str, kind: str, content: bytes) -> str:
    dest_dir = Path(storage_dir) / job_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{kind}.pdf"
    dest_path.write_bytes(content)
    return str(dest_path)
