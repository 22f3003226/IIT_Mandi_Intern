from typing import Optional

from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    id: str
    status: str
    stage: Optional[str] = None
    progress: int
    error: Optional[str] = None
    result_path: Optional[str] = None
