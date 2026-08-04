from fastapi import FastAPI

from app.api import documents, jobs, plans

app = FastAPI(title="Teacher AI Platform")
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(plans.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
