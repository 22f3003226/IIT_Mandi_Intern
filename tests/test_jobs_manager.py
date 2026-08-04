import sqlite3

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


def test_create_job_defaults_job_type_document(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.db"))
    job_id = manager.create_job(file_path="/tmp/x.pdf")
    job = manager.get_job(job_id)
    assert job["job_type"] == "document"
    assert job["parent_job_id"] is None


def test_create_job_accepts_plan_type_and_parent(tmp_path):
    manager = JobManager(str(tmp_path / "jobs.db"))
    parent_id = manager.create_job(file_path="/tmp/x.pdf")
    plan_id = manager.create_job(file_path="/tmp/x.pdf", job_type="plan", parent_job_id=parent_id)
    job = manager.get_job(plan_id)
    assert job["job_type"] == "plan"
    assert job["parent_job_id"] == parent_id


def test_job_manager_migrates_old_schema_without_job_type_columns(tmp_path):
    db_path = str(tmp_path / "old.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            stage TEXT,
            progress INTEGER NOT NULL DEFAULT 0,
            file_path TEXT NOT NULL,
            result_path TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    manager = JobManager(db_path)
    job_id = manager.create_job(file_path="/tmp/old.pdf")
    job = manager.get_job(job_id)
    assert job["job_type"] == "document"
    assert job["parent_job_id"] is None
