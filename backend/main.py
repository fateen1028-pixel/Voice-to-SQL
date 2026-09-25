"""FastAPI entry point for the safe natural-language database assistant."""
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import router
from config.settings import Settings
from db.connection import Database
from services.conversation_service import ConversationStore
from services.query_service import QueryService
from services.speech_to_text_service import SpeechToTextService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    database = Database(settings.database_url)
    database.connect()
    app.state.query_service = QueryService(database, settings)
    app.state.stt_service = SpeechToTextService(settings)
    app.state.conversations = ConversationStore()
    yield
    database.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Voice to SQL Assistant", version="0.1.0", lifespan=lifespan)
    settings = Settings()
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"status": "INVALID_REQUEST", "message": "Request validation failed.", "details": exc.errors()})

    @app.exception_handler(Exception)
    async def internal_error(_: Request, exc: Exception) -> JSONResponse:
        logging.exception("Unhandled application error")
        return JSONResponse(status_code=500, content={"status": "ERROR", "message": "An unexpected server error occurred."})

    app.include_router(router, prefix="/api")

    @app.get("/")
    async def health_checker() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
