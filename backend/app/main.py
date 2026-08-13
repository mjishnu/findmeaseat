import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.redis import close_redis
from app.exceptions import AppError
from app.routers import api_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_redis()


app = FastAPI(
    title="FindMeASeat API",
    version="0.1.0",
    description="Finds the booking combination most likely to confirm by "
    "checking every station pair that covers the user's journey.",
    lifespan=lifespan,
)

# The Vite dev proxy makes CORS unnecessary in dev, but explicit origins keep
# the API usable when the frontend is pointed straight at :8000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(api_router)
