import asyncio
from fastapi import APIRouter, HTTPException, Request
from model.requests import ClarifyRequest
from model.responses import ApiResponse

router = APIRouter()


@router.post("/query/clarify", response_model=ApiResponse)
async def clarify(payload: ClarifyRequest, request: Request) -> dict:
    session_id = request.headers.get("X-Session-ID") or request.headers.get("x-session-id")
    conversations = request.app.state.conversations
    query_service = request.app.state.query_service
    schema_dict = query_service.schema.get()

    pending_intent = conversations.pending_intents.pop(payload.request_id, None)
    if pending_intent:
        field = pending_intent.intent.missing_slots[0] if pending_intent.intent.missing_slots else "general"
        updated_intent = query_service.intent.update_intent_with_selection(
            pending_intent.intent, payload.selection, field, schema_dict
        )

        result = await asyncio.to_thread(
            query_service.process,
            message=pending_intent.original_message,
            conversation_id=pending_intent.conversation_id,
            session_id=session_id,
            user_role=pending_intent.user_role or "user",
            input_type="text",
            intent=updated_intent,
        )

        if result.get("status") == "CLARIFICATION_REQUIRED":
            req_id = result.get("request_id")
            next_intent = result.pop("intent", None)
            if req_id and next_intent:
                from services.conversation_service import PendingClarificationIntent
                conversations.pending_intents[req_id] = PendingClarificationIntent(
                    request_id=req_id,
                    conversation_id=pending_intent.conversation_id,
                    original_message=pending_intent.original_message,
                    intent=next_intent,
                    user_role=pending_intent.user_role,
                )
        else:
            table = result.get("table")
            conversations.remember(pending_intent.conversation_id, pending_intent.original_message, result.get("sql"), table=table)

        return result

    pending_legacy = conversations.clarifications.pop(payload.request_id, None)
    if not pending_legacy:
        raise HTTPException(404, "Clarification request was not found or has expired.")

    combined_message = f"{pending_legacy.message}. Meaning: {payload.selection}"
    result = await asyncio.to_thread(
        query_service.process,
        message=combined_message,
        conversation_id=pending_legacy.conversation_id,
        session_id=session_id,
        user_role=pending_legacy.user_role or "user",
        input_type="text",
    )
    table = result.get("table")
    conversations.remember(pending_legacy.conversation_id, pending_legacy.message, result.get("sql"), table=table)
    return result
