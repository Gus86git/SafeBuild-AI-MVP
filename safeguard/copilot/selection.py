"""Small session context: stable ID and authorized scope, never media or models."""

from pathlib import Path
from .operational import OperationalQueryService


def scope(context):
    return (
        str(Path(context["db_path"]).resolve()) if context.get("db_path") else "",
        context.get("company_id"),
        context.get("site_id"),
        context.get("origin"),
    )


def invalidate_changed_scope(session, context):
    selected = session.get("copilot_selection")
    if selected and tuple(selected["scope"]) != scope(context):
        clear_selection(session)
        return True
    return False


def clear_selection(session):
    session.pop("copilot_selection", None)
    session["copilot_history"] = []
    session.pop("copilot_conversation_analysis", None)


def select_analysis(session, context, analysis_id):
    data = OperationalQueryService(context["db_path"]).analysis(
        analysis_id, context["company_id"], context["site_id"], context["origin"]
    )
    if data["selected_analysis"]["kind"] != "imagen":
        raise ValueError("La selección contextual admite imágenes.")
    clear_selection(session)
    session["copilot_selection"] = {"analysis_id": analysis_id, "scope": scope(context)}
    return data


def selected_id(session, context):
    invalidate_changed_scope(session, context)
    return session.get("copilot_selection", {}).get("analysis_id")
