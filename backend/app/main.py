from fastapi import FastAPI

app = FastAPI(
    title="CORNET API",
    description="Universal web monitoring and change detection platform",
    version="0.1.0",
)


@app.get("/")
async def root():
    return {
        "project": "CORNET",
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
    }
