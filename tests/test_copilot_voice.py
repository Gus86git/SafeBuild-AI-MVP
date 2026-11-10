import base64
import io
import struct
import wave
from uuid import uuid4
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch
from safeguard.copilot.voice import (
    accept_event,
    validate_audio,
    SpeechTranscriber,
    readable_answer,
)
from ui_isolation import IsolatedUITest, submit_copilot


def wav_audio(seconds=1, rate=16000, silent=False):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        out.writeframes(
            b"".join(
                struct.pack("<h", 0 if silent else (1000 if i % 2 else -1000))
                for i in range(int(rate * seconds))
            )
        )
    return buffer.getvalue()


def event(mode="voice", **kw):
    return dict(
        id=str(uuid4()),
        scope="scope",
        mode=mode,
        audio=base64.b64encode(wav_audio()).decode(),
        text="Cuántas observaciones registradas",
        **kw,
    )


class VoiceTests(TestCase):
    def test_audio_validated_from_actual_bytes(self):
        raw, duration = validate_audio(event()["audio"])
        self.assertEqual(duration, 1)
        self.assertEqual(raw, wav_audio())

    def test_invalid_empty_silent_long_short_or_wrong_rate(self):
        for raw in (
            b"",
            b"not audio",
            wav_audio(0.1),
            wav_audio(31),
            wav_audio(rate=8000),
            wav_audio(silent=True),
            wav_audio()[:-20],
        ):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                validate_audio(base64.b64encode(raw).decode())
        with self.assertRaises(ValueError):
            validate_audio("!" * 100)
        with self.assertRaises(ValueError):
            validate_audio("A" * 1_500_000)

    def test_consent_scope_duplicate_and_busy(self):
        session = {}
        ev = event()
        with self.assertRaises(ValueError):
            accept_event(session, ev, "scope")
        with self.assertRaises(ValueError):
            accept_event(session, ev, "other", consent=True)
        accepted = accept_event(session, ev, "scope", consent=True)
        self.assertEqual(accepted["mode"], "voice")
        self.assertIsNone(accept_event(session, ev, "scope", consent=True))
        session["voice_pending"] = accepted
        with self.assertRaises(ValueError):
            accept_event(session, event(), "scope", consent=True)

    def test_rate_and_text_normalization(self):
        session = {}
        for _ in range(6):
            accept_event(session, event(), "scope", consent=True, now=10)
        with self.assertRaisesRegex(ValueError, "rate_limit"):
            accept_event(session, event(), "scope", consent=True, now=12)
        self.assertIsNotNone(
            accept_event(session, event(), "scope", consent=True, now=71)
        )
        ev = event("text")
        ev["text"] = "  Una   pregunta  "
        self.assertEqual(accept_event({}, ev, "scope")["question"], "Una pregunta")
        ev["id"] = str(uuid4())
        ev["text"] = " "
        with self.assertRaises(ValueError):
            accept_event({}, ev, "scope")

    def test_stt_valid_spanish_single_call_no_retry(self):
        client = Mock()
        client.audio.transcriptions.create.return_value.text = (
            "  Cuántas   observaciones hay  "
        )
        factory = Mock(return_value=client)
        result = SpeechTranscriber("test-only", factory).transcribe(
            wav_audio(), authorized=True
        )
        self.assertEqual(result["text"], "Cuántas observaciones hay")
        self.assertEqual(result["state"], "transcribed")
        factory.assert_called_once_with(
            api_key="test-only", timeout=20.0, max_retries=0
        )
        call = client.audio.transcriptions.create.call_args.kwargs
        self.assertEqual(
            (call["language"], call["model"]), ("es", "whisper-large-v3-turbo")
        )
        client.audio.transcriptions.create.assert_called_once()
        client.close.assert_called_once()

    def test_stt_missing_key_or_permission_never_sends(self):
        factory = Mock()
        self.assertEqual(
            SpeechTranscriber(None, factory).transcribe(wav_audio(), authorized=True)[
                "state"
            ],
            "missing_key",
        )
        self.assertEqual(
            SpeechTranscriber("test", factory).transcribe(wav_audio())["state"],
            "voice_consent_required",
        )
        self.assertEqual(
            SpeechTranscriber("test", factory).transcribe(b"bad", authorized=True)[
                "state"
            ],
            "invalid_audio",
        )
        factory.assert_not_called()

    def test_stt_empty_provider_error_and_timeout_redacted(self):
        for name, state in [
            ("AuthenticationError", "authentication_error"),
            ("RateLimitError", "rate_limit"),
            ("TimeoutError", "timeout"),
            ("OtherError", "provider_error"),
        ]:
            client = Mock()
            client.audio.transcriptions.create.side_effect = type(
                name, (Exception,), {}
            )("sensitive provider details")
            result = SpeechTranscriber("test", Mock(return_value=client)).transcribe(
                wav_audio(), authorized=True
            )
            self.assertEqual(result["state"], state)
            self.assertNotIn("sensitive", str(result))
            client.close.assert_called_once()
        client = Mock()
        client.audio.transcriptions.create.return_value.text = "  "
        self.assertEqual(
            SpeechTranscriber("test", Mock(return_value=client)).transcribe(
                wav_audio(), authorized=True
            )["state"],
            "empty_or_long_transcript",
        )

    def test_only_visible_validated_answer_is_narrated(self):
        package = dict(
            status="grounded",
            warnings=[],
            documents=[{"is_synthetic": True, "text": "SECRET hidden path"}],
            sql={
                "facts": {"analyses": 3, "observations": 15},
                "observation_states": [{"review_status": "pending", "count": 12}],
            },
            generation={
                "state": "unvalidated_response",
                "answer": {"text": "REJECTED"},
            },
        )
        text = readable_answer(package)
        for term in ("3 análisis", "15 observaciones", "12 observaciones", "ficticios"):
            self.assertIn(term, text)
        for term in ("SECRET", "REJECTED"):
            self.assertNotIn(term, text)
        package["generation"] = {
            "state": "validated_format",
            "answer": {
                "text": "Evidencia disponible.",
                "warnings": ["Requiere revisión."],
            },
        }
        self.assertIn("Evidencia disponible.", readable_answer(package))
        self.assertIn("Requiere revisión.", readable_answer(package))
        package["warnings"] = ["C:\\private\\secret"]
        self.assertNotIn("C:", readable_answer(package))


class VoiceUITests(IsolatedUITest):
    def app(self):
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(
            str(Path(__file__).resolve().parents[1] / "app.py")
        ).run(timeout=45)
        app.radio(key="navigation").set_value("Copilot · Asistente").run(timeout=45)
        return app

    def test_voice_auto_query_once_context_and_rerun(self):
        with (
            patch("safeguard.copilot.ui.groq_key", return_value="test"),
            patch("safeguard.copilot.ui.SpeechTranscriber") as transcriber,
        ):
            transcriber.return_value.transcribe.return_value = {
                "state": "transcribed",
                "text": "Cuántas observaciones registradas",
                "latency_seconds": 0.1,
            }
            app = self.app()
            app.checkbox(key="voice_consent").check().run(timeout=45)
            submit_copilot(app, "", mode="voice", audio=event()["audio"])
            self.assertFalse(app.exception)
            history = app.session_state["copilot_history"]
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["input_mode"], "voice")
            self.assertEqual(history[0]["sql"]["context"]["site_id"], "OBRA-NORTE-001")
            transcriber.return_value.transcribe.assert_called_once()
            app.run(timeout=45)
            self.assertEqual(len(app.session_state["copilot_history"]), 1)
            self.assertNotIn("voice_pending", app.session_state)
            app.selectbox(key="site").set_value("OBRA-SUR-002").run(timeout=45)
            self.assertFalse(app.checkbox(key="voice_consent").value)
            self.assertEqual(app.session_state["copilot_history"], [])

    def test_text_mode_and_conversation_reset(self):
        with patch("safeguard.copilot.ui.SpeechTranscriber") as transcriber:
            app = self.app()
            submit_copilot(app, "Cuántas observaciones registradas")
            self.assertEqual(
                app.session_state["copilot_history"][-1]["input_mode"], "text"
            )
            token = app.session_state["voice_conversation"]
            app.button(key="copilot_clear").click().run(timeout=45)
            self.assertNotEqual(token, app.session_state["voice_conversation"])
            self.assertEqual(app.session_state["copilot_history"], [])
            transcriber.assert_not_called()
