import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.auth import router as auth_router
from app.api.routes.consultations import router as consultations_router
from app.api.routes.health import router as health_router
from app.api.routes.patients import router as patients_router
from app.api.routes.reports import router as reports_router
from app.api.routes.transcriptions import router as transcriptions_router
from app.core.cleanup import run_purge
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.transcription_worker import transcription_loop

configure_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async def cleanup_loop():
        while True:
            try:
                await asyncio.to_thread(run_purge)
            except Exception:
                logger.exception("audio cleanup failed")
            await asyncio.sleep(settings.audio_cleanup_interval_seconds)

    async def transcription_loop_task():
        await transcription_loop()

    tasks = [
        asyncio.create_task(cleanup_loop()),
        asyncio.create_task(transcription_loop_task()),
    ]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(patients_router, prefix="/patients", tags=["patients"])
app.include_router(consultations_router, prefix="/consultations", tags=["consultations"])
app.include_router(transcriptions_router, prefix="/consultations", tags=["transcriptions"])
app.include_router(reports_router, prefix="/consultations", tags=["reports"])
