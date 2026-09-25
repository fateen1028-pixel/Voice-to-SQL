import asyncio
from fastapi import APIRouter, Request
from model.requests import ConfirmRequest
from model.responses import ApiResponse

router = APIRouter()


@router.post("/query/confirm", response_model=ApiResponse)
async def confirm(payload: ConfirmRequest, request: Request) -> dict:
    session_id = request.headers.get("X-Session-ID") or request.headers.get("x-session-id")
    return await asyncio.to_thread(
        request.app.state.query_service.confirm,
        payload.confirmation_token,
        session_id=session_id,
    )
