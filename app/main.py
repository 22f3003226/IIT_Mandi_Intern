from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import documents, jobs, plans, publish

app = FastAPI(title="Teacher AI Platform")
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(plans.router)
app.include_router(publish.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
