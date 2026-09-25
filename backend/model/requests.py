from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="Natural language query string.")
    conversation_id: str | None = Field(default=None, max_length=128, description="Optional conversation identifier.")
    user_role: str | None = Field(default="user", max_length=64, description="Optional user role for permission evaluation.")


class ClarifyRequest(BaseModel):
    request_id: str = Field(..., min_length=1, description="Original request ID that triggered clarification.")
    selection: str = Field(..., min_length=1, max_length=500, description="User selected option/meaning.")


class ConfirmRequest(BaseModel):
    confirmation_token: str = Field(..., min_length=1, description="One-time server issued execution confirmation token.")
