import io
from pathlib import Path

from app.storage.files import save_plan_result_json, save_result_json, save_upload


def test_save_upload_writes_file_under_job_dir(tmp_path):
    content = b"hello world"
    path = save_upload(str(tmp_path), "job-1", "doc.txt", io.BytesIO(content))
    assert Path(path).read_bytes() == content
    assert Path(path).parent.name == "job-1"


def test_save_result_json_writes_named_file(tmp_path):
    path = save_result_json(str(tmp_path), "job-1", '{"a": 1}')
    assert Path(path).name == "DocumentKnowledgeExtract.json"
    assert Path(path).read_text() == '{"a": 1}'


def test_save_upload_rejects_relative_traversal_filename(tmp_path):
    path = save_upload(str(tmp_path), "job-1", "../evil.txt", io.BytesIO(b"x"))
    assert Path(path).parent == tmp_path / "job-1"
    assert Path(path).name == "evil.txt"


def test_save_upload_rejects_absolute_path_filename(tmp_path):
    path = save_upload(str(tmp_path), "job-1", "/etc/passwd", io.BytesIO(b"x"))
    assert Path(path).parent == tmp_path / "job-1"
    assert Path(path).name == "passwd"


def test_save_plan_result_json_writes_teaching_plan_file(tmp_path):
    path = save_plan_result_json(str(tmp_path), "job-1", '{"job_id": "job-1"}')
    assert Path(path).name == "TeachingPlan.json"
    assert Path(path).read_text() == '{"job_id": "job-1"}'
