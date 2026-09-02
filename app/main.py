from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers.candidate_form import router as candidate_form_router
from app.api.routers.resume_scoring import router as resume_scoring_router
from app.core.config import settings
from app.core.database import close_db_pool, init_db_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db_pool(settings.DATABASE_URL)
    yield
    await close_db_pool()


app = FastAPI(title="AI Interview Bot — Backend Services", lifespan=lifespan)
app.include_router(resume_scoring_router)
app.include_router(candidate_form_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
