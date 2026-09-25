from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/schema")
async def schema(request: Request) -> dict:
    return {"tables": request.app.state.query_service.schema.get()}
