from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from model.responses import ApiResponse

router = APIRouter()


@router.post("/voice/query", response_model=ApiResponse)
async def voice_query(request: Request, audio: UploadFile = File(...)) -> dict:
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

    return request.app.state.query_service.process(transcript, input_type="voice")
