"""Keep UI tests out of the user's local database and approved model."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from itertools import chain, repeat
from uuid import uuid4
import hashlib


def submit_copilot(app, question, *, mode="text", audio=None):
    """Inject the real component event contract; JS behavior is tested separately."""
    token = hashlib.sha256(
        repr(
            (
                app.session_state["copilot_scope"],
                app.session_state["voice_conversation"],
            )
        ).encode()
    ).hexdigest()
    event = dict(id=str(uuid4()), scope=token, mode=mode, text=question, audio=audio)
    with patch(
        "safeguard.copilot.ui.render_composer", side_effect=chain([event], repeat(None))
    ):
        app.run(timeout=60)
    return event


class IsolatedUITest(TestCase):
    def setUp(self):
        self.sandbox = TemporaryDirectory()
        self.addCleanup(self.sandbox.cleanup)
        scope = patch.dict(
            os.environ,
            {
                "SAFEGUARD_DB_PATH": str(Path(self.sandbox.name) / "ui.sqlite3"),
                "SAFEGUARD_MODEL_PATH": str(Path(self.sandbox.name) / "absent.pt"),
                "SAFEGUARD_RAG_PATH": str(Path(self.sandbox.name) / "rag"),
                "SAFEGUARD_EMBEDDING_PATH": str(Path(self.sandbox.name) / "embeddings"),
                "GROQ_API_KEY": "",
            },
        )
        scope.start()
        self.addCleanup(scope.stop)
