from fastapi import FastAPI

from app.api.routers.resume_scoring import router as resume_scoring_router

app = FastAPI(title="AI Interview Bot — Backend Services")
app.include_router(resume_scoring_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
