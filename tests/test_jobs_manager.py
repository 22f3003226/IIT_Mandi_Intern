from app.jobs.manager import JobManager


def test_create_and_get_job(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = manager.create_job(file_path="/tmp/doc.pdf")
    job = manager.get_job(job_id)
    assert job["status"] == "queued"
    assert job["progress"] == 0
    assert job["file_path"] == "/tmp/doc.pdf"


def test_update_job_progress_and_status(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = manager.create_job(file_path="/tmp/doc.pdf")
    manager.update_job(job_id, status="running", stage="parsing", progress=10)
    job = manager.get_job(job_id)
    assert job["status"] == "running"
    assert job["stage"] == "parsing"
    assert job["progress"] == 10


def test_get_job_returns_none_for_unknown_id(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.db"))
    assert manager.get_job("does-not-exist") is None


def test_create_job_with_explicit_id(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = manager.create_job(file_path="/tmp/doc.pdf", job_id="fixed-id")
    assert job_id == "fixed-id"
    assert manager.get_job("fixed-id") is not None
