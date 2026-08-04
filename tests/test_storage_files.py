import io
from pathlib import Path

from app.storage.files import save_result_json, save_upload


def test_save_upload_writes_file_under_job_dir(tmp_path):
    content = b"hello world"
    path = save_upload(str(tmp_path), "job-1", "doc.txt", io.BytesIO(content))
    assert Path(path).read_bytes() == content
    assert Path(path).parent.name == "job-1"


def test_save_result_json_writes_named_file(tmp_path):
    path = save_result_json(str(tmp_path), "job-1", '{"a": 1}')
    assert Path(path).name == "DocumentKnowledgeExtract.json"
    assert Path(path).read_text() == '{"a": 1}'
