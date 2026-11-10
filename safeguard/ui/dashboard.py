"""SafeBuild analytics: native controls, scoped SQL and dark Plotly figures."""

from datetime import datetime, timedelta, timezone
from html import escape
import sqlite3
import plotly.graph_objects as go
from .analytics import dashboard_data, LOCAL
from .icons import icon
from .presentation import heading, go as navigate
from safeguard.copilot.operational import OperationalQueryService
from safeguard.copilot.selection import select_analysis, scope

COLORS = ["#00DEB5", "#44F5D1", "#24B4F5", "#AF7DE4", "#FFC345"]
LABELS = {
    "helmet": "Casco",
    "vest": "Chaleco reflectivo",
    "gloves": "Guantes",
    "boots": "Botas",
    "goggles": "Gafas",
}


def styled(fig, height=176):
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Segoe UI, Arial, sans-serif", size=12, color="#E5F1F2"),
        margin=dict(l=8, r=8, t=12, b=12),
        colorway=COLORS,
        legend=dict(orientation="h", y=1.22, x=0, font=dict(size=10)),
        hoverlabel=dict(bgcolor="#12343C", font_color="#F2F7F8", bordercolor="#29E6CF"),
    )
    fig.update_xaxes(
        gridcolor="#24454C", zeroline=False, showgrid=False, automargin=True
    )
    fig.update_yaxes(
        gridcolor="#24454C", zeroline=False, automargin=True, rangemode="tozero"
    )
    return fig


def chart(st, fig, key):
    st.plotly_chart(
        fig,
        width="stretch",
        theme=None,
        key=key,
        config={"displayModeBar": False, "scrollZoom": False, "responsive": True},
    )


def empty(st, message="Sin registros en este período"):
    st.markdown(
        '<div class="sb-dash-empty">'
        + icon("chart", 30)
        + "<b>"
        + escape(message)
        + "</b><span>Cambie el período o analice y guarde una evidencia.</span></div>",
        unsafe_allow_html=True,
    )


def render(settings, st):
    with st.container(key="sb_dashboard"):
        title_col, controls_col = st.columns([4.6, 1.2], vertical_alignment="center")
        with controls_col:
            with st.popover(
                "Filtrar dashboard", icon=":material/filter_alt:", width="stretch"
            ):
                period = st.selectbox(
                    "Período",
                    [
                        "Todo el historial",
                        "Últimos 7 días",
                        "Últimos 30 días",
                        "Personalizado",
                    ],
                    key="dash_period",
                    help="Período aplicado a todos los paneles.",
                )
                kind = st.selectbox(
                    "Medio",
                    ["Todos", "imagen", "video"],
                    format_func=lambda v: {
                        "Todos": "Todos los medios",
                        "imagen": "Imágenes",
                        "video": "Videos",
                    }[v],
                    key="dash_kind",
                    help="Filtrar análisis de imágenes o videos.",
                )
                start = end = None
                today = datetime.now(LOCAL).date()
                if period == "Personalizado":
                    interval = st.date_input(
                        "Fechas · Buenos Aires",
                        value=(today - timedelta(days=6), today),
                        key="dash_dates",
                    )
                    if len(interval) != 2:
                        st.info("Seleccione el inicio y el final del período.")
                        return
                    start, end = interval
                elif period != "Todo el historial":
                    end = today
                    start = today - timedelta(
                        days=6 if period == "Últimos 7 días" else 29
                    )
                    st.caption(f"{start:%d/%m/%Y} — {end:%d/%m/%Y} · Buenos Aires")
                else:
                    st.caption(
                        "Todo el historial de la obra · sin recorte de agregados"
                    )
            if st.button(
                "Actualizar datos",
                key="dash_refresh",
                icon=":material/refresh:",
                width="stretch",
            ):
                st.rerun()
        with title_col:
            filter_label = (
                period
                + " · "
                + {
                    "Todos": "Todos los medios",
                    "imagen": "Imágenes",
                    "video": "Videos",
                }[kind]
            )
            if start:
                filter_label += f" · {start:%d/%m/%Y} — {end:%d/%m/%Y}"
            st.markdown(
                '<div class="sb-dash-title"><div class="sb-eyebrow">DASHBOARD DE SEGURIDAD EN OBRA</div><h1>Indicadores de EPP y gestión de evidencias</h1><p>'
                + escape(filter_label)
                + " · Datos de la obra seleccionada.</p></div>",
                unsafe_allow_html=True,
            )
        try:
            data = dashboard_data(
                settings.get("db_path"),
                settings.get("company_id"),
                settings.get("site_id"),
                settings.get("origin"),
                start,
                end,
                kind,
            )
        except (sqlite3.Error, OSError, ValueError, TypeError):
            st.warning(
                "No se pudo consultar el dashboard. Revise empresa, obra y SQLite en Sistema; no se estiman valores."
            )
            return
        totals = data["totals"]
        with st.container(key="dash_kpis"):
            metrics = [
                ("image", "Análisis realizados", "total"),
                ("shield", "Observaciones registradas", "observations"),
                ("alert", "Pendientes de revisión", "pending"),
                ("video", "Videos analizados", "videos"),
            ]
            st.markdown(
                '<div class="sb-kpis">'
                + "".join(
                    '<div class="sb-kpi"><span class="sb-kpi-icon">'
                    + icon(ic, 36)
                    + "</span><div><small>"
                    + name
                    + "</small><b>"
                    + str(totals[key])
                    + "</b></div></div>"
                    for ic, name, key in metrics
                )
                + "</div>",
                unsafe_allow_html=True,
            )
        with st.container(key="dash_row_one"):
            cols = st.columns([3, 2.55, 2, 2.1], gap="small")
            with cols[0], st.container(key="dash_ppe"):
                heading(
                    "EPP detectado", "Distribución de cajas del modelo.", "helmet", st
                )
                if data["classes"]:
                    fig = go.Figure(
                        go.Pie(
                            labels=[LABELS[r["label"]] for r in data["classes"]],
                            values=[r["count"] for r in data["classes"]],
                            hole=0.7,
                            sort=False,
                            marker=dict(
                                colors=COLORS, line=dict(color="#07242A", width=1)
                            ),
                            textinfo="none",
                            hovertemplate="%{label}: %{value} cajas (%{percent})<extra></extra>",
                        )
                    )
                    styled(fig, 164)
                    fig.update_layout(
                        legend=dict(
                            orientation="v",
                            x=1,
                            y=0.5,
                            yanchor="middle",
                            font=dict(size=11),
                        ),
                        annotations=[
                            dict(
                                text=f"<b>{sum(r['count'] for r in data['classes'])}</b><br>Cajas EPP",
                                x=0.5,
                                y=0.5,
                                xref="paper",
                                yref="paper",
                                showarrow=False,
                                font=dict(size=17),
                            )
                        ],
                    )
                    chart(st, fig, "dash_ppe_chart")
                else:
                    empty(st, "Sin detecciones EPP del modelo")
            with cols[1], st.container(key="dash_period_chart"):
                heading(
                    "Análisis por período",
                    "Cantidad por fecha de análisis.",
                    "chart",
                    st,
                )
                if data["daily"]:
                    fig = go.Figure(
                        go.Bar(
                            x=[r["day"] for r in data["daily"]],
                            y=[r["count"] for r in data["daily"]],
                            marker=dict(
                                color="#00D6B1", line=dict(color="#60FEE1", width=1)
                            ),
                            text=[r["count"] for r in data["daily"]],
                            textposition="outside",
                            cliponaxis=False,
                            hovertemplate="%{x}: %{y} análisis<extra></extra>",
                        )
                    )
                    styled(fig, 164).update_xaxes(type="category", nticks=7)
                    fig.update_yaxes(
                        dtick=1 if max(r["count"] for r in data["daily"]) < 6 else None
                    )
                    chart(st, fig, "dash_daily_chart")
                else:
                    empty(st)
            with cols[2], st.container(key="dash_review"):
                heading(
                    "Revisión registrada",
                    "Observaciones marcadas revisadas.",
                    "shield",
                    st,
                )
                if totals["observations"]:
                    value = 100 * totals["reviewed"] / totals["observations"]
                    fig = go.Figure(
                        go.Indicator(
                            mode="gauge+number",
                            value=value,
                            number=dict(suffix="%", font=dict(size=32)),
                            gauge=dict(
                                axis=dict(range=[0, 100], visible=False),
                                bar=dict(color="#00DDB4"),
                                bgcolor="#34545B",
                                borderwidth=0,
                            ),
                        )
                    )
                    styled(fig, 140)
                    chart(st, fig, "dash_review_chart")
                    st.caption(
                        f"{totals['reviewed']} de {totals['observations']} · no acredita cumplimiento"
                    )
                else:
                    empty(st, "Revisión: N/A")
            with cols[3], st.container(key="dash_insights"):
                heading(
                    "Principales insights",
                    "Calculados sobre el filtro activo.",
                    "help",
                    st,
                )
                insights = []
                if data["classes"]:
                    top = data["classes"][0]
                    insights.append(
                        f"Mayor conteo EPP: {LABELS[top['label']]} ({top['count']} cajas)."
                    )
                if data["daily"]:
                    peak = max(data["daily"], key=lambda r: r["count"])
                    insights.append(
                        f"Pico de análisis: {peak['day']} ({peak['count']})."
                    )
                insights.append(
                    f"{totals['pending']} observaciones pendientes de revisión."
                )
                insights.append(
                    f"{totals['videos']} videos; sus muestras no representan personas únicas."
                )
                st.markdown(
                    '<ul class="sb-insights">'
                    + "".join(
                        "<li>" + icon("shield", 18) + escape(item) + "</li>"
                        for item in insights
                    )
                    + "</ul>",
                    unsafe_allow_html=True,
                )
        with st.container(key="dash_row_two"):
            cols = st.columns([4.5, 3.3, 2.1], gap="small")
            with cols[0], st.container(key="dash_trend"):
                heading(
                    "Tendencia de observaciones",
                    "Estado actual por fecha del análisis; no fecha de revisión.",
                    "chart",
                    st,
                )
                if data["trend"]:
                    fig = go.Figure()
                    for key, label, color in [
                        ("count", "Observaciones", "#43EDE1"),
                        ("pending", "Pendientes", "#FFC345"),
                        ("reviewed", "Revisadas", "#00BC99"),
                    ]:
                        fig.add_trace(
                            go.Scatter(
                                x=[r["day"] for r in data["trend"]],
                                y=[r[key] for r in data["trend"]],
                                name=label,
                                mode="lines+markers",
                                line=dict(color=color, width=2),
                                fill="tozeroy" if key == "count" else None,
                                fillcolor="rgba(41,230,207,.08)",
                                hovertemplate="%{x}: %{y}<extra>%{fullData.name}</extra>",
                            )
                        )
                    styled(fig, 140).update_xaxes(type="category", nticks=7)
                    fig.update_yaxes(
                        dtick=1 if max(r["count"] for r in data["trend"]) < 6 else None
                    )
                    chart(st, fig, "dash_trend_chart")
                else:
                    empty(st, "Sin observaciones registradas")
            with cols[1], st.container(key="dash_categories"):
                heading(
                    "Observaciones por estado",
                    "Categorías registradas; no infracciones.",
                    "layers",
                    st,
                )
                if data["categories"]:
                    fig = go.Figure(
                        go.Bar(
                            x=[r["count"] for r in data["categories"]],
                            y=[r["category"] for r in data["categories"]],
                            orientation="h",
                            marker=dict(
                                color="#00D6B1", line=dict(color="#50F3DA", width=1)
                            ),
                            text=[r["count"] for r in data["categories"]],
                            textposition="auto",
                            hovertemplate="%{y}: %{x}<extra></extra>",
                        )
                    )
                    styled(fig, 140).update_yaxes(
                        autorange="reversed", showgrid=False, tickfont=dict(size=10)
                    )
                    fig.update_xaxes(
                        dtick=1
                        if max(r["count"] for r in data["categories"]) < 6
                        else None
                    )
                    chart(st, fig, "dash_categories_chart")
                else:
                    empty(st, "Sin categorías registradas")
            with cols[2], st.container(key="dash_attention"):
                heading(
                    "Puntos de atención",
                    "Pendientes en la selección actual.",
                    "alert",
                    st,
                )
                st.markdown(
                    f'<p class="sb-attention-count">{totals["pending"]} <span>observaciones pendientes</span></p>',
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Requieren revisión de evidencia y contexto. No confirman ausencia de EPP."
                )
                if data["attention"]:
                    with st.expander("Consultar pendientes"):
                        choices = {
                            f"{r['analysis_id']}:{r['frame_index']}:{r['id']}": r
                            for r in data["attention"]
                        }
                        chosen = st.selectbox(
                            "Observación pendiente",
                            list(choices),
                            format_func=lambda k: choices[k]["id"]
                            + " · "
                            + choices[k]["analysis_id"][:8],
                            key="dash_attention_pick",
                        )
                        if st.button(
                            "Ver observación",
                            key="dash_attention_open",
                            width="stretch",
                        ):
                            st.session_state["dash_detail"] = (
                                scope(settings),
                                choices[chosen]["analysis_id"],
                                choices[chosen]["frame_index"],
                                choices[chosen]["id"],
                            )
        with st.container(key="dash_recent"):
            title, button = st.columns([5, 1.3], vertical_alignment="center")
            with title:
                heading(
                    "Últimos análisis realizados",
                    "Hasta 20 registros de la obra, procedencia y período seleccionados.",
                    "layers",
                    st,
                )
            with button:
                if st.button(
                    "Ver historial completo", key="dash_history", width="stretch"
                ):
                    navigate("Historial", st)
            if data["recent"]:
                table = []
                for row in data["recent"]:
                    ts = datetime.fromisoformat(row["created_utc"])
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    table.append(
                        {
                            "Fecha y hora": ts.astimezone(LOCAL).strftime(
                                "%d/%m/%Y · %H:%M"
                            ),
                            "Tipo": row["kind"],
                            "Archivo / Evidencia": row["filename"]
                            or "Sin nombre registrado",
                            "Detecciones": row["detections"],
                            "Observaciones": row["observations"],
                            "Pendientes": row["pending"],
                            "Revisión del análisis": {
                                "pending": "Pendiente",
                                "reviewed": "Revisado",
                            }[row["review_status"]],
                            "ID": row["id"],
                        }
                    )
                st.dataframe(table, hide_index=True, width="stretch", height=140)
                options = {r["id"]: r for r in data["recent"]}
                pick, button = st.columns([5, 1.3], vertical_alignment="bottom")
                with pick:
                    selected = st.selectbox(
                        "Análisis para consultar",
                        list(options),
                        format_func=lambda k: (options[k]["filename"] or "Sin nombre")
                        + " · "
                        + k[:8],
                        key="dash_recent_pick",
                        label_visibility="collapsed",
                    )
                with button:
                    if st.button(
                        "Abrir detalle", key="dash_detail_open", width="stretch"
                    ):
                        st.session_state["dash_detail"] = (
                            scope(settings),
                            selected,
                            None,
                            None,
                        )
            else:
                empty(st)
        active = st.session_state.get("dash_detail")
        allowed = {r["id"] for r in data["recent"]} | {
            r["analysis_id"] for r in data["attention"]
        }
        if active and (active[0] != scope(settings) or active[1] not in allowed):
            st.session_state.pop("dash_detail", None)
            active = None
        if active:
            with st.container(key="dash_detail", border=True):
                try:
                    detail = OperationalQueryService(settings["db_path"]).analysis(
                        active[1],
                        settings["company_id"],
                        settings["site_id"],
                        settings["origin"],
                    )
                    st.subheader("Detalle del análisis")
                    st.text("ID: " + active[1])
                    st.caption(
                        "Detecciones y observaciones: máximo 200 filas por tabla. IDs efímeros por fotograma."
                    )
                    people = detail["selected_analysis"]["people"]
                    if active[3] is not None:
                        people = [
                            r
                            for r in people
                            if r["frame_index"] == active[2] and r["id"] == active[3]
                        ]
                        st.caption("Observación seleccionada: " + active[3])
                        if not people:
                            st.info(
                                "La observación no está incluida en las primeras 200 filas del detalle disponible. El agregado de pendientes incluye todas las filas."
                            )
                    st.dataframe(people, width="stretch", hide_index=True)
                    with st.expander("Detecciones del análisis"):
                        st.dataframe(
                            detail["selected_analysis"]["detections"],
                            width="stretch",
                            hide_index=True,
                        )
                    if detail["selected_analysis"]["kind"] == "imagen" and st.button(
                        "Consultar este análisis con Copilot", key="dash_copilot"
                    ):
                        select_analysis(st.session_state, settings, active[1])
                        navigate("Copilot · Asistente", st)
                    if st.button("Cerrar detalle", key="dash_detail_close"):
                        st.session_state.pop("dash_detail", None)
                        st.rerun()
                except (sqlite3.Error, OSError, ValueError):
                    st.warning("El detalle no está disponible para este contexto.")
        with st.expander("Qué miden estos gráficos y sus límites"):
            st.write(
                "Los filtros de empresa, obra, procedencia, período y medio se aplican a todos los paneles. Fechas en Buenos Aires (UTC−3)."
            )
            st.write(
                "EPP: cajas del modelo de casco, chaleco, guantes, botas y gafas; excluye personas, clases negativas y heurísticas. Son detecciones, no uso confirmado ni trabajadores únicos."
            )
            st.write(
                "Revisión = observaciones con review_status reviewed / observaciones del período. Sin observaciones: N/A. No mide cumplimiento ni certificación."
            )
            st.write(
                "La tendencia agrupa el estado de revisión actual por fecha del análisis. No existe una historia de cambios de revisión en la base."
            )
            st.write(
                "Los días sin análisis se omiten; las líneas conectan fechas con registros. Videos: conteos por fotogramas muestreados, sin seguimiento temporal."
            )
            st.write(
                "Los estados del análisis y de sus observaciones son independientes. No hay miniaturas porque SQLite conserva hashes, no imágenes."
            )
        st.caption(
            "Consulta local: "
            + data["queried_at"].strftime("%d/%m/%Y %H:%M:%S")
            + " · Buenos Aires · revisión no equivale a cumplimiento legal."
        )
