"""SafeBuild visual layer. All actions use native Streamlit controls."""

from pathlib import Path
from functools import lru_cache
from base64 import b64encode
from html import escape
from urllib.parse import quote
from datetime import timezone, timedelta
import sqlite3
from .icons import icon, CRANE
from .home_metrics import context_metrics

ROOT = Path(__file__).resolve().parents[2]
NAV_LABELS = {
    "Inicio": "SafeBuild",
    "Imágenes": "Imagen",
    "Videos": "Video",
    "Resumen": "Resumen de sesión",
}
NAV_ICONS = [
    "home",
    "chart",
    "image",
    "video",
    "clock",
    "people",
    "book",
    "upload",
    "settings",
    "help",
    "layers",
]


@lru_cache(maxsize=1)
def _assets(css_version, photo_version):
    css = (ROOT / "assets/safebuild/theme.css").read_text(encoding="utf-8-sig")
    photo = b64encode(
        (ROOT / "assets/safebuild/hero-conceptual.png").read_bytes()
    ).decode("ascii")
    css += (
        '\n.st-key-sb_hero{background-image:linear-gradient(90deg,#092B2D 0%,#092B2Dee 28%,#07141A08 68%),url("data:image/png;base64,'
        + photo
        + '");}'
    )
    for index, name in enumerate(NAV_ICONS, 1):
        svg = icon(name, 20).replace("currentColor", "#A9CCD1")
        css += f'\n.st-key-navigation [role=radiogroup]>div:nth-child({index}) label::before{{background-image:url("data:image/svg+xml,{quote(svg)}");}}'
    return css


def apply_theme(st):
    st.markdown(
        "<style>"
        + _assets(
            (ROOT / "assets/safebuild/theme.css").stat().st_mtime_ns,
            (ROOT / "assets/safebuild/hero-conceptual.png").stat().st_mtime_ns,
        )
        + "</style>",
        unsafe_allow_html=True,
    )


def brand(st):
    st.markdown(
        '<div class="sb-brand">'
        + icon("helmet", 52)
        + '<div><div class="sb-brand-title">SafeBuild <span>AI</span></div><small>Sistema Inteligente de Detección de EPP</small></div></div>',
        unsafe_allow_html=True,
    )


@lru_cache(maxsize=1)
def _reference_crane(version):
    image = b64encode(
        (ROOT / "assets/safebuild/dashboard-reference.png").read_bytes()
    ).decode("ascii")
    # Native SVG viewport crops only the illustration from the user reference.
    # None of the mock dashboard values or controls are rendered.
    return (
        '<svg class="sb-crane" viewBox="0 797 299 144" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><image width="1672" height="941" href="data:image/png;base64,'
        + image
        + '"/></svg>'
    )


def crane(st):
    path = ROOT / "assets/safebuild/dashboard-reference.png"
    st.markdown(
        _reference_crane(path.stat().st_mtime_ns) if path.exists() else CRANE,
        unsafe_allow_html=True,
    )


def side_heading(title, name, st):
    st.markdown(
        '<div class="sb-side-heading">' + icon(name, 21) + escape(title) + "</div>",
        unsafe_allow_html=True,
    )


def topbar(st):
    st.markdown(
        '<div class="sb-topbar"><span class="sb-local">MVP ACADÉMICO</span><span class="sb-avatar" aria-hidden="true">SB</span><div><b>SafeBuild AI</b><small>Demostración académica · sin autenticación</small></div></div>',
        unsafe_allow_html=True,
    )


def page_heading(page, st):
    st.markdown(
        '<div class="sb-page-heading">SAFEBUILD AI / '
        + escape(NAV_LABELS.get(page, page).upper())
        + "</div>",
        unsafe_allow_html=True,
    )


def go(page, st):
    st.session_state["pending_navigation"] = page
    st.rerun()


def heading(title, subtitle, name, st):
    st.markdown(
        '<div class="sb-section-title">'
        + icon(name, 31)
        + "<div><h2>"
        + escape(title)
        + "</h2><p>"
        + escape(subtitle)
        + "</p></div></div>",
        unsafe_allow_html=True,
    )


def home(settings, st):
    @st.dialog("Presentación de SafeBuild AI", width="large")
    def presentation_video():
        st.video("https://www.youtube.com/watch?v=T4TzRgYSeVY", autoplay=False)

    with st.container(key="sb_hero"):
        st.markdown(
            """<div class="sb-hero-copy"><div class="sb-eyebrow">PLATAFORMA DE SEGURIDAD EN OBRA</div><h1>Bienvenido a <span class="sb-accent">SafeBuild AI</span></h1><p>Plataforma integral de visión por computadora y conocimiento especializado para la seguridad en construcción. Detecta EPP en imágenes y videos, permite revisar evidencias, consultar procedimientos mediante una base de conocimiento RAG y generar reportes operativos.</p></div><div class="sb-bracket" aria-hidden="true"></div><div class="sb-detection" aria-hidden="true"><strong>EPP · ejemplo visual</strong><span>✓</span> Casco<br><span>✓</span> Lentes de seguridad<br><span>✓</span> Chaleco reflectivo</div>""",
            unsafe_allow_html=True,
        )
        buttons = st.columns([1.05, 1.25, 1.45, 2.05])
        with buttons[0]:
            if st.button(
                "Analizar evidencias",
                key="home_analyze",
                icon=":material/play_arrow:",
                type="primary",
                width="stretch",
            ):
                go("Imágenes", st)
        with buttons[1]:
            if st.button(
                "Consultar procedimientos",
                key="home_knowledge",
                icon=":material/menu_book:",
                width="stretch",
            ):
                go("Copilot · Conocimiento", st)
        with buttons[2]:
            if st.button(
                "Ver video de presentación",
                key="home_presentation_video",
                icon=":material/play_circle:",
                width="stretch",
            ):
                presentation_video()
        st.markdown(
            '<span class="sb-concept">Imagen sintética conceptual · sin inferencia YOLO</span>',
            unsafe_allow_html=True,
        )
    cards = [
        (
            "scan",
            "Detección de EPP",
            "Identifica automáticamente elementos de protección personal en imágenes y videos mediante modelos de visión artificial.",
            "Imágenes",
        ),
        (
            "people",
            "Revisión humana",
            "Permite examinar las detecciones, revisar observaciones y consultar las evidencias antes de tomar decisiones.",
            "Historial",
        ),
        (
            "layers",
            "Base de conocimiento (RAG)",
            "Recupera información de normas, procedimientos y documentación mediante BM25, ChromaDB y búsqueda híbrida.",
            "Copilot · Conocimiento",
        ),
        (
            "chart",
            "Consultas y reportes",
            "Permite consultar registros operativos, explorar estadísticas y exportar resultados para su revisión.",
            "Resumen",
        ),
    ]
    with st.container(key="sb_features"):
        for i, (col, card) in enumerate(zip(st.columns(4), cards)):
            name, title, description, destination = card
            with col:
                with st.container(key=f"sb_feature_{i}", height="stretch"):
                    st.markdown(icon(name, 30), unsafe_allow_html=True)
                    if st.button(title, key=f"home_card_{i}", width="stretch"):
                        go(destination, st)
                    st.markdown(
                        "<p>" + escape(description) + "</p>", unsafe_allow_html=True
                    )
    with st.container(key="sb_indicators"):
        try:
            data = context_metrics(
                settings.get("db_path"),
                settings.get("company_id"),
                settings.get("site_id"),
                settings.get("origin"),
            )
        except (sqlite3.Error, OSError, ValueError, TypeError):
            data = None
        title, meta, refresh = st.columns([7, 3.5, 1.3])
        with title:
            heading(
                "Indicadores del contexto seleccionado",
                "Resumen de análisis y gestión de evidencias en la obra actual.",
                "chart",
                st,
            )
        with meta:
            if data is not None:
                queried = data["queried_at"].astimezone(timezone(timedelta(hours=-3)))
                st.caption(
                    "Consulta: "
                    + queried.strftime("%d/%m/%Y %H:%M:%S")
                    + " · Buenos Aires"
                )
        with refresh:
            if st.button(
                "Actualizar",
                key="home_refresh",
                icon=":material/refresh:",
                help="Volver a consultar SQLite para esta empresa, obra y procedencia.",
            ):
                st.rerun()
        if data is None:
            st.info(
                "No se pudieron consultar los indicadores. Revise el contexto y SQLite en Sistema. Los valores no se estiman."
            )
        items = [
            ("image", "Análisis realizados", "total"),
            ("shield", "Observaciones registradas", "observations"),
            ("alert", "Observaciones pendientes", "pending"),
            ("video", "Videos analizados", "videos"),
        ]
        body = ""
        for name, label, key in items:
            value = str(data[key]) if data is not None else "Sin datos"
            body += (
                '<div class="sb-kpi"><span class="sb-kpi-icon">'
                + icon(name, 28)
                + "</span><div><small>"
                + label
                + "</small><b>"
                + value
                + "</b></div></div>"
            )
        st.markdown('<div class="sb-kpis">' + body + "</div>", unsafe_allow_html=True)
    with st.container(key="sb_steps"):
        heading(
            "Cómo usar la app",
            "Sigue estos pasos para analizar, revisar, consultar y generar reportes de forma ágil.",
            "rocket",
            st,
        )
        steps = [
            ("upload", "Selecciona el contexto", "Elige empresa, obra y procedencia."),
            (
                "image",
                "Analiza evidencias",
                "Carga imágenes o videos y ejecuta la detección de EPP.",
            ),
            (
                "shield",
                "Revisa los resultados",
                "Examina las detecciones, consulta las observaciones y revisa sus limitaciones.",
            ),
            (
                "chart",
                "Consulta y reporta",
                "Explora los procedimientos mediante RAG y descarga los resultados disponibles.",
            ),
        ]
        body = "".join(
            '<div class="sb-step"><div class="sb-step-title"><span class="sb-number">'
            + str(i)
            + "</span>"
            + icon(name, 21)
            + escape(title)
            + "</div><p>"
            + escape(description)
            + "</p></div>"
            for i, (name, title, description) in enumerate(steps, 1)
        )
        st.markdown(
            '<div class="sb-steps-grid">' + body + "</div>", unsafe_allow_html=True
        )
