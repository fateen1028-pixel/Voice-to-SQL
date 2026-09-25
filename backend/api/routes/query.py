import asyncio
from fastapi import APIRouter, Request
from model.requests import QueryRequest
from model.responses import ApiResponse
from services.conversation_service import PendingClarification

router = APIRouter()


@router.post("/query", response_model=ApiResponse)
async def query(payload: QueryRequest, request: Request) -> dict:
    session_id = request.headers.get("X-Session-ID") or request.headers.get("x-session-id")
    conversations = request.app.state.conversations
    query_service = request.app.state.query_service
    prior_sql = conversations.get_last_sql(payload.conversation_id)
    active_table = conversations.get_active_table(payload.conversation_id)

    pending_intent = conversations.get_and_pop_pending_intent_for_conversation(payload.conversation_id)
    if pending_intent:
        schema_dict = query_service.schema.get()
        field = pending_intent.intent.missing_slots[0] if pending_intent.intent.missing_slots else "general"
        updated_intent = query_service.intent.update_intent_with_selection(
            pending_intent.intent, payload.message, field, schema_dict
        )

        result = await asyncio.to_thread(
            query_service.process,
            message=pending_intent.original_message,
            conversation_id=payload.conversation_id,
            session_id=session_id,
            prior_sql=prior_sql,
            active_context_table=active_table,
            user_role=payload.user_role or pending_intent.user_role or "user",
            input_type="text",
            intent=updated_intent,
        )
    else:
        result = await asyncio.to_thread(
            query_service.process,
            message=payload.message,
            conversation_id=payload.conversation_id,
            session_id=session_id,
            prior_sql=prior_sql,
            active_context_table=active_table,
            user_role=payload.user_role or "user",
            input_type="text",
        )

    if result.get("status") == "CLARIFICATION_REQUIRED":
        req_id = result.get("request_id")
        intent = result.pop("intent", None)
        if req_id:
            conversations.clarifications[req_id] = PendingClarification(
                message=payload.message,
                conversation_id=payload.conversation_id,
                user_role=payload.user_role,
            )
            if intent:
                from services.conversation_service import PendingClarificationIntent
                conversations.pending_intents[req_id] = PendingClarificationIntent(
                    request_id=req_id,
                    conversation_id=payload.conversation_id,
                    original_message=pending_intent.original_message if pending_intent else payload.message,
                    intent=intent,
                    user_role=payload.user_role,
                )
    else:
        table = result.get("table")
        conversations.remember(
            payload.conversation_id,
            pending_intent.original_message if pending_intent else payload.message,
            result.get("sql"),
            table=table,
        )

    return result


@router.get("/query/{request_id}")
async def get_query_status(request_id: str, request: Request) -> dict:
    from fastapi import HTTPException
    details = request.app.state.query_service.get_request_by_id(request_id)
    if not details:
        raise HTTPException(404, f"Query request with ID '{request_id}' was not found.")
    return details

