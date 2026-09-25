from fastapi import APIRouter, Request
from model.requests import ConfirmRequest
from model.responses import ApiResponse

router = APIRouter()


@router.post("/query/confirm", response_model=ApiResponse)
async def confirm(payload: ConfirmRequest, request: Request) -> dict:
    return request.app.state.query_service.confirm(payload.confirmation_token)
