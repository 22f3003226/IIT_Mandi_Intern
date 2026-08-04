from app.config import settings
from app.jobs.manager import JobManager

job_manager = JobManager(settings.db_path)
