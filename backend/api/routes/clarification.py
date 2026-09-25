from fastapi import APIRouter, HTTPException, Request
from model.requests import ClarifyRequest
from model.responses import ApiResponse

router = APIRouter()


@router.post("/query/clarify", response_model=ApiResponse)
async def clarify(payload: ClarifyRequest, request: Request) -> dict:
    conversations = request.app.state.conversations
    pending = conversations.clarifications.pop(payload.request_id, None)
    if not pending:
        raise HTTPException(404, "Clarification request was not found or has expired.")

    combined_message = f"{pending.message}. Meaning: {payload.selection}"
    result = request.app.state.query_service.process(
        message=combined_message,
        conversation_id=pending.conversation_id,
        user_role=pending.user_role or "user",
        input_type="text",
    )
    conversations.remember(pending.conversation_id, pending.message, result.get("sql"))
    return result
