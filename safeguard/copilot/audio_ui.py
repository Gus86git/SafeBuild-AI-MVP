"""Small public Components v2 wrappers. Never pass API credentials to JS."""

from pathlib import Path
from hashlib import sha256
import streamlit as st

ROOT = Path(__file__).parent
_js = (ROOT / "audio_component.mjs").read_text(encoding="utf-8")
_css = (ROOT / "audio_component.css").read_text(encoding="utf-8")
_version = sha256((_js + _css).encode()).hexdigest()[:12]
component = st.components.v2.component(
    "safebuild_audio_" + _version, js=_js, css=_css, html="<div></div>"
)


def render_composer(
    scope, *, consent=False, has_key=False, phase=None, draft="", error=""
):
    result = component(
        key="copilot_composer",
        data=dict(
            kind="composer",
            scope=scope,
            consent=consent,
            hasKey=has_key,
            phase=phase,
            draft=draft,
            error=error,
        ),
        on_submission_change=lambda: None,
    )
    return result.submission


def render_player(text, message_id, mode, scope):
    component(
        key="copilot_player_" + message_id,
        data=dict(kind="player", text=text, id=scope + ":" + message_id, mode=mode),
        on_status_change=lambda: None,
    )
