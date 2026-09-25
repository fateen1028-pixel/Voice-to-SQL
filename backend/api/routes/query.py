from fastapi import APIRouter, Request
from model.requests import QueryRequest
from model.responses import ApiResponse
from services.conversation_service import PendingClarification

router = APIRouter()


@router.post("/query", response_model=ApiResponse)
async def query(payload: QueryRequest, request: Request) -> dict:
    conversations = request.app.state.conversations
    prior_sql = conversations.get_last_sql(payload.conversation_id)

    result = request.app.state.query_service.process(
        message=payload.message,
        conversation_id=payload.conversation_id,
        prior_sql=prior_sql,
        user_role=payload.user_role or "user",
        input_type="text",
    )

    if result.get("status") == "CLARIFICATION_REQUIRED":
        req_id = result.get("request_id")
        if req_id:
            conversations.clarifications[req_id] = PendingClarification(
                message=payload.message,
                conversation_id=payload.conversation_id,
                user_role=payload.user_role,
            )
    else:
        conversations.remember(payload.conversation_id, payload.message, result.get("sql"))

    return result


@router.get("/query/{request_id}")
async def get_query_status(request_id: str, request: Request) -> dict:
    from fastapi import HTTPException
    details = request.app.state.query_service.get_request_by_id(request_id)
    if not details:
        raise HTTPException(404, f"Query request with ID '{request_id}' was not found.")
    return details

