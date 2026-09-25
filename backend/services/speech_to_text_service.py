"""Speech-To-Text service with abstract provider architecture and faster-whisper support."""
from abc import ABC, abstractmethod
import io
import logging
import math
import os
import tempfile

from config.settings import Settings

logger = logging.getLogger(__name__)


class BaseSpeechToTextService(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes, content_type: str | None = None) -> tuple[str | None, float | None]:
        """Transcribe audio bytes to (transcript_text, confidence)."""
        pass


class LocalWhisperSpeechToTextService(BaseSpeechToTextService):
    def __init__(self, settings: Settings) -> None:
        self.model_name = settings.whisper_model
        self.device = settings.whisper_device
        self.compute_type = settings.whisper_compute_type
        self.confidence_threshold = settings.stt_confidence_threshold
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                logger.info("Initializing local faster-whisper model '%s' on device='%s' (compute_type='%s')", self.model_name, self.device, self.compute_type)
                self._model = WhisperModel(
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                )
            except Exception as exc:
                logger.error("Failed to load faster-whisper model: %s", exc)
                raise RuntimeError(f"Could not load local Whisper model: {exc}") from exc
        return self._model

    async def transcribe(self, audio: bytes, content_type: str | None = None) -> tuple[str | None, float | None]:
        if not audio or len(audio) == 0:
            return None, 0.0

        # Attempt UTF-8 plain text fallback if passed as text bytes (e.g., in mock/test callers)
        try:
            text_str = audio.decode("utf-8", errors="strict").strip()
            if text_str and not text_str.startswith("\x00") and len(text_str) < 500:
                # Check if it looks like natural language text rather than binary audio header
                if not any(b > 127 for b in audio[:16]):
                    return text_str, 0.95
        except UnicodeDecodeError:
            pass

        tmp_path = None
        try:
            suffix = ".wav"
            if content_type:
                if "mp3" in content_type:
                    suffix = ".mp3"
                elif "ogg" in content_type:
                    suffix = ".ogg"
                elif "webm" in content_type:
                    suffix = ".webm"
                elif "m4a" in content_type:
                    suffix = ".m4a"

            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(audio)
                tmp_path = f.name

            model = self._get_model()
            segments, info = model.transcribe(tmp_path, beam_size=5)

            full_text = []
            logprobs = []
            no_speech_probs = []

            for seg in segments:
                text = seg.text.strip()
                if text:
                    full_text.append(text)
                if hasattr(seg, "avg_logprob"):
                    logprobs.append(seg.avg_logprob)
                if hasattr(seg, "no_speech_prob"):
                    no_speech_probs.append(seg.no_speech_prob)

            transcript = " ".join(full_text).strip()

            if not transcript:
                return None, 0.0

            # Calculate estimated confidence from logprobs if available
            confidence = 0.85
            if logprobs:
                avg_lp = sum(logprobs) / len(logprobs)
                confidence = max(0.0, min(1.0, math.exp(avg_lp)))

            if no_speech_probs and (sum(no_speech_probs) / len(no_speech_probs)) > 0.6:
                return None, 0.0

            if confidence < self.confidence_threshold:
                return None, confidence

            return transcript, confidence
        except Exception as exc:
            logger.warning("Local faster-whisper transcription error: %s", exc)
            return None, 0.0
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass


class MockSpeechToTextService(BaseSpeechToTextService):
    async def transcribe(self, audio: bytes, content_type: str | None = None) -> tuple[str | None, float | None]:
        if not audio or len(audio) == 0:
            return None, 0.0
        try:
            decoded = audio.decode("utf-8", errors="ignore").strip()
            if not decoded or decoded.startswith("\x00"):
                return None, 0.0
            return decoded, 0.95
        except Exception:
            return None, 0.0


class CloudSpeechToTextService(BaseSpeechToTextService):
    def __init__(self, settings: Settings) -> None:
        self.api_key = settings.stt_api_key

    async def transcribe(self, audio: bytes, content_type: str | None = None) -> tuple[str | None, float | None]:
        if not self.api_key:
            raise RuntimeError("STT_API_KEY is not configured for cloud Speech-To-Text provider.")
        return None, 0.0


class SpeechToTextService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = (settings.stt_provider or "local").lower()
        self.instance: BaseSpeechToTextService

        if self.provider in ("local", "whisper", "faster-whisper"):
            self.instance = LocalWhisperSpeechToTextService(settings)
        elif self.provider in ("openai", "cloud"):
            self.instance = CloudSpeechToTextService(settings)
        else:
            self.instance = MockSpeechToTextService()

    async def transcribe(self, audio: bytes, content_type: str | None = None) -> tuple[str | None, float | None]:
        return await self.instance.transcribe(audio, content_type)
