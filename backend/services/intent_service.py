"""Intent understanding and ambiguity detection service."""
import re
from services.clarification_service import ClarificationService


class IntentService:
    def __init__(self, clarification_service: ClarificationService) -> None:
        self.clarification_service = clarification_service

    def detect_clarification(self, message: str, schema: dict[str, dict] | None = None) -> tuple[str, list[str]] | None:
        normalized = message.lower().strip()

        # If user has already selected a clarification meaning, do not trigger clarification again
        if "meaning:" in normalized or "clarification:" in normalized:
            return None

        # Check for ambiguous concepts
        if re.search(r"\bbest\s+customers?\b", normalized):
            return self.clarification_service.generate_options("best customers", schema)

        if re.fullmatch(r"\s*(show|get|view|list)?\s*(me\s+)?(the\s+)?sales\s*[?.!]*\s*", normalized):
            return self.clarification_service.generate_options("sales", schema)

        if re.search(r"\b(top|best)\s+employees?\b", normalized):
            return "What metric defines the 'top employees'?", [
                "Highest sales volume",
                "Highest salary",
                "Longest tenure",
            ]

        return None

    def is_prompt_injection(self, message: str) -> bool:
        normalized = message.lower()
        suspicious_patterns = [
            r"ignore\s+(all\s+)?previous\s+instructions",
            r"system\s+prompt",
            r"bypass\s+security",
        ]
        return any(re.search(pattern, normalized) for pattern in suspicious_patterns)
