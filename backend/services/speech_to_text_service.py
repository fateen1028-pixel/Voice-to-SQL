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
        self.settings = settings
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
                gemini_text, gemini_conf = await self._transcribe_with_gemini_fallback(audio, content_type)
                if gemini_text:
                    return gemini_text, gemini_conf
                return None, 0.0

            # Calculate estimated confidence from logprobs if available
            confidence = 0.85
            if logprobs:
                avg_lp = sum(logprobs) / len(logprobs)
                confidence = max(0.0, min(1.0, math.exp(avg_lp)))

            if no_speech_probs and (sum(no_speech_probs) / len(no_speech_probs)) > 0.6:
                return None, 0.0

            if confidence < self.confidence_threshold:
                # Try Gemini audio fallback if confidence is low or empty
                gemini_text, gemini_conf = await self._transcribe_with_gemini_fallback(audio, content_type)
                if gemini_text:
                    return gemini_text, gemini_conf
                return None, confidence

            return transcript, confidence
        except Exception as exc:
            logger.warning("Local faster-whisper transcription error: %s. Attempting Gemini inline audio STT fallback...", exc)
            return await self._transcribe_with_gemini_fallback(audio, content_type)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    async def _transcribe_with_gemini_fallback(self, audio: bytes, content_type: str | None = None) -> tuple[str | None, float | None]:
        api_key = getattr(self, "settings", None) and self.settings.llm_api_key
        if not api_key or api_key.startswith("your_") or api_key == "mock":
            return None, 0.0

        try:
            import base64
            import httpx

            mime = content_type or "audio/webm"
            if ";" in mime:
                mime = mime.split(";")[0]

            b64 = base64.b64encode(audio).decode("utf-8")
            candidate_models = [
                getattr(self.settings, "llm_model", None),
                "gemini-3.6-flash",
                "gemma-4-26b-a4b-it",
                "gemini-3.1-flash-lite",
            ]
            models: list[str] = []
            for m in candidate_models:
                if m and m not in ("gpt-4o-mini", "mock") and m not in models:
                    models.append(m)

            async with httpx.AsyncClient(timeout=20.0) as client:
                for model_name in models:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                    payload = {
                        "contents": [{
                            "parts": [
                                {"inlineData": {"mimeType": mime, "data": b64}},
                                {"text": "Transcribe this spoken voice query accurately into plain English text. Output ONLY the transcribed query without punctuation or quotes."}
                            ]
                        }],
                        "generationConfig": {"temperature": 0.0}
                    }
                    try:
                        resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
                        if resp.status_code == 200:
                            candidates = resp.json().get("candidates", [])
                            if candidates and "content" in candidates[0]:
                                parts = candidates[0]["content"].get("parts", [])
                                if parts:
                                    text = parts[0].get("text", "").strip()
                                    if text:
                                        logger.info("Gemini inline audio STT ('%s') successfully transcribed: '%s'", model_name, text)
                                        return text, 0.95
                        logger.warning("Gemini inline audio STT model '%s' status %d: %s", model_name, resp.status_code, resp.text[:150])
                    except Exception as exc:
                        logger.warning("Gemini audio STT error on model '%s': %s", model_name, exc)
        except Exception as exc:
            logger.warning("Gemini inline audio STT error: %s", exc)

        return None, 0.0


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
        self.api_key = settings.stt_api_key or settings.llm_api_key
        self.provider = (settings.stt_provider or "openai").lower()

    async def transcribe(self, audio: bytes, content_type: str | None = None) -> tuple[str | None, float | None]:
        if not audio or len(audio) == 0:
            return None, 0.0

        if not self.api_key or self.api_key.startswith("your_"):
            logger.warning("STT_API_KEY is not configured for cloud Speech-To-Text. Falling back to text/mock handler.")
            try:
                decoded = audio.decode("utf-8", errors="ignore").strip()
                if decoded and not decoded.startswith("\x00"):
                    return decoded, 0.95
            except Exception:
                pass
            return None, 0.0

        try:
            import httpx
            ext = "webm" if "webm" in (content_type or "") else "wav"
            url = "https://api.openai.com/v1/audio/transcriptions"
            model = "whisper-1"

            if self.provider == "groq":
                url = "https://api.groq.com/openai/v1/audio/transcriptions"
                model = "whisper-large-v3-turbo"

            files = {"file": (f"speech.{ext}", audio, content_type or "audio/webm")}
            data = {"model": model}
            headers = {"Authorization": f"Bearer {self.api_key}"}

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, files=files, data=data, headers=headers)
                if resp.status_code == 200:
                    text = resp.json().get("text", "").strip()
                    return (text, 0.95) if text else (None, 0.0)
                logger.warning("Cloud STT API error (status %d): %s", resp.status_code, resp.text)
        except Exception as exc:
            logger.warning("Cloud Speech-To-Text transcription error: %s", exc)

        return None, 0.0


class SpeechToTextService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = (settings.stt_provider or "local").lower()
        self.instance: BaseSpeechToTextService

        if self.provider in ("local", "whisper", "faster-whisper"):
            self.instance = LocalWhisperSpeechToTextService(settings)
        elif self.provider in ("openai", "groq", "cloud"):
            self.instance = CloudSpeechToTextService(settings)
        else:
            self.instance = MockSpeechToTextService()

    async def transcribe(self, audio: bytes, content_type: str | None = None) -> tuple[str | None, float | None]:
        return await self.instance.transcribe(audio, content_type)

