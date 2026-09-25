from typing import Any
from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    status: str = Field(..., description="Response status indicator.")
    request_id: str | None = Field(default=None, description="Unique request identifier.")
    message: str | None = Field(default=None, description="Human readable status message.")
    sql: str | None = Field(default=None, description="Generated or executed SQL statement.")
    operation: str | None = Field(default=None, description="SQL operation category (SELECT, INSERT, UPDATE, DELETE).")
    table: str | None = Field(default=None, description="Target database table identifier.")
    columns: list[str] | None = Field(default=None, description="Column names returned by SELECT query.")

    rows: list[dict[str, Any]] | None = Field(default=None, description="Data rows returned by query.")
    row_count: int | None = Field(default=None, description="Count of returned or affected rows.")
    question: str | None = Field(default=None, description="Clarification question when status is CLARIFICATION_REQUIRED.")
    field: str | None = Field(default=None, description="Target field requiring clarification.")
    options: list[Any] | None = Field(default=None, description="Clarification choices.")
    confirmation_token: str | None = Field(default=None, description="Token required to confirm mutation queries.")
    estimated_affected_rows: int | None = Field(default=None, description="Estimated affected row count for UPDATE/DELETE operations.")
    validation: dict[str, Any] | None = Field(default=None, description="Validation summary details.")
    visualization: dict[str, Any] | None = Field(default=None, description="Recommended visualization configuration.")
    explanation: str | None = Field(default=None, description="Natural language interpretation of query results.")
    transcript: str | None = Field(default=None, description="Transcribed speech-to-text string for voice requests.")
    audit_id: str | None = Field(default=None, description="Audit log entry identifier.")


