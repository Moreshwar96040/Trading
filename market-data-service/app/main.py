"""FastAPI entrypoint.

Run: uvicorn app.main:app --port 8000
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.scheduler import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level,
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    scheduler = start_scheduler()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Market Data Service", version="0.1.0", lifespan=lifespan)
app.include_router(router)
