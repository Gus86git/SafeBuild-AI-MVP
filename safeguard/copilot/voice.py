"""Ephemeral voice requests: validate PCM WAV before any optional Groq call."""

import base64
import binascii
import io
import re
import struct
import wave
from time import monotonic, perf_counter
from uuid import UUID

STT_MODEL = "whisper-large-v3-turbo"
MAX_SECONDS = 30
MAX_BYTES = 1_000_000
MAX_REQUESTS_PER_MINUTE = 6


def normalize_question(value):
    if not isinstance(value, str):
        raise ValueError("invalid_question")
    value = " ".join(value.split())
    if not 3 <= len(value) <= 1000:
        raise ValueError("empty_or_long_transcript")
    return value


def validate_audio(encoded):
    if not isinstance(encoded, str) or len(encoded) > ((MAX_BYTES + 2) // 3) * 4:
        raise ValueError("audio_too_large")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("invalid_audio") from None
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("invalid_audio")
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE" or len(raw) < 44:
        raise ValueError("invalid_audio")
    if int.from_bytes(raw[4:8], "little") + 8 != len(raw):
        raise ValueError("invalid_audio")
    try:
        with wave.open(io.BytesIO(raw), "rb") as wav:
            channels, width, rate, frames, compression, _ = wav.getparams()
            if (channels, width, rate, compression) != (1, 2, 16000, "NONE"):
                raise ValueError("unsupported_audio")
            duration = frames / rate
            if not 0.6 <= duration <= MAX_SECONDS:
                raise ValueError("audio_duration")
            pcm = wav.readframes(frames)
            if len(pcm) != frames * 2:
                raise ValueError("invalid_audio")
            if not any(abs(v[0]) > 8 for v in struct.iter_unpack("<h", pcm)):
                raise ValueError("silent_audio")
    except (wave.Error, EOFError, struct.error):
        raise ValueError("invalid_audio") from None
    return raw, duration


def accept_event(session, event, token, *, consent=False, now=None):
    """Reserve a unique event before STT or local querying. Never trust UI scope."""
    if not isinstance(event, dict) or event.get("scope") != token:
        raise ValueError("stale_context")
    try:
        identifier = str(UUID(event.get("id", "")))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("invalid_event") from None
    handled = session.setdefault("voice_handled", [])
    if identifier in handled:
        return None
    if session.get("voice_pending"):
        raise ValueError("busy")
    if len(handled) >= 128:
        raise ValueError("session_limit")
    mode = event.get("mode")
    if mode not in ("text", "voice"):
        raise ValueError("invalid_event")
    if mode == "voice" and not consent:
        raise ValueError("voice_consent_required")
    handled.append(identifier)
    if mode == "text":
        return dict(
            id=identifier,
            mode=mode,
            question=normalize_question(event.get("text")),
            phase="PROCESSING",
            scope=token,
        )
    raw, duration = validate_audio(event.get("audio"))
    now = monotonic() if now is None else now
    attempts = [t for t in session.get("voice_attempts", []) if now - t < 60]
    session["voice_attempts"] = attempts
    if len(attempts) >= MAX_REQUESTS_PER_MINUTE:
        raise ValueError("rate_limit")
    attempts.append(now)
    return dict(
        id=identifier,
        mode=mode,
        audio=raw,
        duration=duration,
        phase="TRANSCRIBING",
        scope=token,
    )


class SpeechTranscriber:
    def __init__(self, key=None, client_factory=None):
        self.key, self.client_factory = key, client_factory

    def transcribe(self, raw, *, authorized=False):
        began = perf_counter()
        if not authorized:
            return {"state": "voice_consent_required"}
        if not self.key:
            return {"state": "missing_key"}
        # Defense in depth for direct calls, not just the component path.
        try:
            validate_audio(base64.b64encode(raw).decode("ascii"))
        except (ValueError, TypeError):
            return {"state": "invalid_audio"}
        client = None
        try:
            if self.client_factory is None:
                from groq import Groq

                factory = Groq
            else:
                factory = self.client_factory
            client = factory(api_key=self.key, timeout=20.0, max_retries=0)
            response = client.audio.transcriptions.create(
                file=("question.wav", raw, "audio/wav"),
                model=STT_MODEL,
                language="es",
                response_format="json",
                temperature=0,
            )
            question = normalize_question(response.text)
            return {
                "state": "transcribed",
                "text": question,
                "latency_seconds": perf_counter() - began,
            }
        except (ValueError, AttributeError):
            return {"state": "empty_or_long_transcript"}
        except ImportError:
            return {"state": "sdk_unavailable"}
        except Exception as exc:
            state = {
                "AuthenticationError": "authentication_error",
                "PermissionDeniedError": "authentication_error",
                "RateLimitError": "rate_limit",
                "APITimeoutError": "timeout",
                "TimeoutError": "timeout",
                "APIConnectionError": "connection_error",
            }.get(type(exc).__name__, "provider_error")
            return {"state": state, "latency_seconds": perf_counter() - began}
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass


def readable_answer(package):
    """Exact visible narration, built from trusted fields, never raw hidden evidence."""
    lines = []
    sql = package.get("sql")
    if sql:
        facts = sql["facts"]
        lines.append(
            f"En el contexto seleccionado hay {facts['analyses']} análisis y {facts['observations']} observaciones registradas."
        )
        pending = sum(
            r["count"]
            for r in sql["observation_states"]
            if r["review_status"] == "pending"
        )
        lines.append(f"{pending} observaciones están pendientes de revisión humana.")
        lines.append(
            "Estos conteos no representan trabajadores únicos ni infracciones confirmadas."
        )
    generated = package.get("generation") or {}
    if generated.get("state") == "validated_format":
        answer = generated["answer"]
        lines.append(answer["text"])
        lines.extend(answer["warnings"])
        lines.append(
            "Formato y referencias comprobados; la interpretación requiere revisión humana."
        )
    elif package.get("documents"):
        lines.append(
            "Hay fragmentos documentales recuperados para esta consulta. Revisá las citas y el texto de las fuentes que se muestran debajo."
        )
    if any(c.get("is_synthetic") for c in package.get("documents", [])):
        lines.append(
            "Los procedimientos TechCorp utilizados son ficticios y pertenecen a una simulación académica."
        )
    if package.get("status") == "insufficient":
        lines.append(
            "No hay evidencia suficiente para responder esta consulta. Revisá el contexto o reformulá la pregunta."
        )
    elif package.get("status") == "partial":
        lines.append(
            "La evidencia disponible es parcial; no permite completar toda la respuesta."
        )
    lines.extend(package.get("warnings", []))
    # Fixed local messages plus validated generation only. Reject rather than
    # narrate path/secret/technical payload accidentally introduced upstream.
    text = "\n\n".join(dict.fromkeys(lines))
    if re.search(r"gsk_|[A-Za-z]:[\\/]|\b[a-fA-F0-9]{32,}\b|\bDOC:|[{}]", text):
        return "La respuesta contiene información técnica que no se reproduce por voz. Revisá las evidencias visibles."
    return text or "No hay una respuesta legible disponible. Revisá las evidencias."


ERRORS = {
    "missing_key": "La transcripción requiere una clave Groq configurada en el servidor. Podés escribir tu pregunta.",
    "voice_consent_required": "Autorizá el uso de voz para este contexto antes de grabar.",
    "stale_context": "Cambió el contexto. La grabación anterior se descartó.",
    "invalid_event": "No se pudo reconocer el envío. Intentá nuevamente.",
    "invalid_question": "La pregunta no es válida.",
    "empty_or_long_transcript": "No se obtuvo una pregunta válida de entre 3 y 1000 caracteres. Intentá hablar más claramente o escribí.",
    "invalid_audio": "El audio está vacío, incompleto o no tiene un formato válido.",
    "unsupported_audio": "No se pudo preparar el audio en el formato admitido.",
    "audio_duration": "La grabación debe durar entre 0,6 y 30 segundos.",
    "audio_too_large": "El audio supera el límite de un megabyte.",
    "silent_audio": "No se detectó señal de audio suficiente.",
    "rate_limit": "Se alcanzó el límite de solicitudes. Esperá un minuto antes de volver a intentar.",
    "busy": "Ya hay una consulta en curso.",
    "session_limit": "Esta conversación alcanzó el límite de envíos. Iniciá una nueva conversación.",
    "authentication_error": "Groq no aceptó la configuración de acceso. Revisá la clave en el servidor.",
    "timeout": "La transcripción tardó demasiado. No se reintentó automáticamente.",
    "connection_error": "No se pudo conectar con Groq. Podés escribir tu pregunta.",
    "provider_error": "El proveedor no pudo transcribir el audio. Podés escribir tu pregunta.",
    "sdk_unavailable": "El adaptador Groq no está instalado. La consulta escrita sigue disponible.",
}
