import asyncio
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from model.responses import ApiResponse
from services.conversation_service import PendingClarification, PendingClarificationIntent

router = APIRouter()


@router.post("/voice/query", response_model=ApiResponse)
async def voice_query(
    request: Request,
    audio: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
    user_role: str | None = Form(default="user"),
) -> dict:
    session_id = request.headers.get("X-Session-ID") or request.headers.get("x-session-id")
    conversations = request.app.state.conversations
    settings = request.app.state.query_service.settings
    try:
        content = await audio.read()
        transcript, confidence = await request.app.state.stt_service.transcribe(content, audio.content_type)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))

    if not transcript or (confidence is not None and confidence < settings.stt_confidence_threshold):
        return {
            "status": "RETRY_REQUIRED",
            "message": "Can't understand, please say again.",
        }

    prior_sql = conversations.get_last_sql(conversation_id)
    active_table = conversations.get_active_table(conversation_id)
    query_service = request.app.state.query_service

    pending_intent = conversations.get_and_pop_pending_intent_for_conversation(conversation_id)
    if pending_intent:
        schema_dict = query_service.schema.get()
        field = pending_intent.intent.missing_slots[0] if pending_intent.intent.missing_slots else "general"
        updated_intent = query_service.intent.update_intent_with_selection(
            pending_intent.intent, transcript, field, schema_dict
        )

        res = await asyncio.to_thread(
            query_service.process,
            message=pending_intent.original_message,
            conversation_id=conversation_id,
            session_id=session_id,
            prior_sql=prior_sql,
            active_context_table=active_table,
            user_role=user_role or pending_intent.user_role or "user",
            input_type="voice",
            intent=updated_intent,
        )
    else:
        res = await asyncio.to_thread(
            query_service.process,
            message=transcript,
            conversation_id=conversation_id,
            session_id=session_id,
            prior_sql=prior_sql,
            active_context_table=active_table,
            user_role=user_role or "user",
            input_type="voice",
        )

    if isinstance(res, dict):
        res["transcript"] = transcript

        if res.get("status") == "CLARIFICATION_REQUIRED":
            req_id = res.get("request_id")
            intent = res.pop("intent", None)
            if req_id:
                conversations.clarifications[req_id] = PendingClarification(
                    message=transcript,
                    conversation_id=conversation_id,
                    user_role=user_role,
                )
                if intent:
                    conversations.pending_intents[req_id] = PendingClarificationIntent(
                        request_id=req_id,
                        conversation_id=conversation_id,
                        original_message=pending_intent.original_message if pending_intent else transcript,
                        intent=intent,
                        user_role=user_role,
                    )
        else:
            table = res.get("table")
            conversations.remember(
                conversation_id,
                pending_intent.original_message if pending_intent else transcript,
                res.get("sql"),
                table=table,
            )

    return res


