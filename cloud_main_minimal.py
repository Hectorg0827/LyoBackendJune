from fastapi import FastAPI
import os

app = FastAPI(title="LyoBackend Minimal")

@app.get("/")
def read_root():
    return {"message": "LyoBackend Minimal Deployment Test", "status": "success"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "lyo-backend-minimal"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
