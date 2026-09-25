from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/history")
async def history(request: Request, conversation_id: str) -> dict:
    items = request.app.state.conversations.history.get(conversation_id, [])
    return {"conversation_id": conversation_id, "items": items}
