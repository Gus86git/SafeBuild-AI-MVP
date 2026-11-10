"""Contratos, asociación geométrica conservadora y decisiones explicables.

Los parámetros geométricos son experimentales, no métricas validadas.
Las cajas no prueban visibilidad ni ausencia de EPP.
"""

from dataclasses import asdict, dataclass
from enum import Enum
from math import isfinite


class State(str, Enum):
    VERIFIED = "Cumplimiento visual verificable"
    POSSIBLE = "Posible incumplimiento"
    UNKNOWN = "No verificable"
    REVIEW = "Requiere revisión humana"


ALIASES = {
    "worker": "person",
    "hardhat": "helmet",
    "hard-hat": "helmet",
    "safety_vest": "vest",
    "safety-vest": "vest",
}
RULE_VERSION = "visual-1a.1"


def canonical(label):
    label = label.strip().lower()
    return ALIASES.get(label, label)


@dataclass(frozen=True)
class Detection:
    id: str
    label: str
    bbox: tuple[float, float, float, float]
    confidence: float
    source: str = "model"
    occluded: bool = False

    def __post_init__(self):
        if (
            len(self.bbox) != 4
            or not all(isfinite(v) for v in self.bbox)
            or self.bbox[2] <= self.bbox[0]
            or self.bbox[3] <= self.bbox[1]
        ):
            raise ValueError("Caja inválida")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("Confianza fuera de rango")
        if self.source not in ("model", "heuristic"):
            raise ValueError("Origen desconocido")

    @classmethod
    def from_mapping(cls, index, value):
        return cls(
            str(index),
            canonical(value["class"]),
            tuple(value["bbox"]),
            float(value["confidence"]),
            "heuristic" if value.get("inferred") else value.get("source", "model"),
            bool(value.get("occluded", False)),
        )


@dataclass(frozen=True)
class PersonObservation:
    person_id: str
    helmet_id: str | None
    vest_id: str | None
    ambiguous: bool = False
    obstructed: bool = False
    heuristic_hint: bool = False


@dataclass(frozen=True)
class Decision:
    person_id: str
    state: State
    reason: str
    rule_version: str = RULE_VERSION


def decide(observation, *, evidence_reviewed=False, visible_missing=()):
    """Afirmaciones positivas/negativas requieren evidencia externa revisada.

    La UI automática no aporta esta revisión. visible_missing nunca se deriva
    de una caja faltante: es una observación explícita de una región visible.
    """
    missing = set(visible_missing)
    if not missing <= {"helmet", "vest"}:
        raise ValueError("EPP fuera del alcance")
    if observation.ambiguous:
        state, reason = State.REVIEW, "Asociación ambigua; no se asigna EPP compartido."
    elif observation.obstructed:
        state, reason = State.UNKNOWN, "Persona o región ocluida/recortada."
    elif missing and evidence_reviewed:
        conflict = (
            "helmet" in missing
            and observation.helmet_id is not None
            or "vest" in missing
            and observation.vest_id is not None
        )
        state = State.REVIEW if conflict else State.POSSIBLE
        reason = (
            "Evidencias contradictorias."
            if conflict
            else "Ausencia visual informada por revisión; requiere evaluación profesional del contexto."
        )
    elif observation.helmet_id and observation.vest_id:
        state = State.VERIFIED if evidence_reviewed else State.REVIEW
        reason = (
            "Casco y chaleco visibles según evidencia revisada; no certifica seguridad ni cumplimiento legal."
            if evidence_reviewed
            else "Candidatos de casco y chaleco asociados; detecciones sin validación visual."
        )
    elif observation.heuristic_hint:
        state, reason = State.REVIEW, "Indicio experimental de color; no acredita EPP."
    else:
        state, reason = (
            State.UNKNOWN,
            "Evidencia insuficiente; una falta de detección no confirma ausencia.",
        )
    return Decision(observation.person_id, state, reason)


def intersection(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )


def fits(person, item):
    """Centro y al menos 50% del área del objeto en región anatómica 2D."""
    x1, y1, x2, y2 = person.bbox
    height = y2 - y1
    lo, hi = (0, 0.35) if item.label == "helmet" else (0.2, 0.8)
    region = (x1, y1 + height * lo, x2, y1 + height * hi)
    a, b, c, d = item.bbox
    cx, cy = (a + c) / 2, (b + d) / 2
    return (
        region[0] <= cx <= region[2]
        and region[1] <= cy <= region[3]
        and intersection(region, item.bbox) / ((c - a) * (d - b)) >= 0.5
    )


def observe(detections, threshold=0.4, image_size=None):
    if not isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Umbral fuera de rango")
    if image_size is not None and (
        len(image_size) != 2 or any(not isfinite(v) or v <= 0 for v in image_size)
    ):
        raise ValueError("Dimensiones inválidas")
    ds = [Detection.from_mapping(i, d) for i, d in enumerate(detections)]
    accepted = [d for d in ds if d.confidence >= threshold]
    persons = [d for d in accepted if d.label == "person" and d.source == "model"]
    equipment = [
        d for d in accepted if d.label in ("helmet", "vest") and d.source == "model"
    ]
    assignments = {p.id: {} for p in persons}
    ambiguous = set()
    # Multiple plausible owners => abstain for all involved, independent of input order.
    for item in equipment:
        owners = [p for p in persons if fits(p, item)]
        if len(owners) > 1:
            ambiguous.update(p.id for p in owners)
        elif len(owners) == 1:
            owner = owners[0]
            previous = assignments[owner.id].get(item.label)
            if previous is None or item.confidence > previous.confidence:
                assignments[owner.id][item.label] = item
    observations = []
    for p in persons:
        assigned = assignments[p.id]
        obstructed = p.occluded or any(d.occluded for d in assigned.values())
        if image_size:
            h, w = image_size
            obstructed |= (
                p.bbox[0] <= 0 or p.bbox[1] <= 0 or p.bbox[2] >= w or p.bbox[3] >= h
            )
        hint = any(
            d.source == "heuristic" and d.label in ("helmet", "vest") and fits(p, d)
            for d in accepted
        )
        observations.append(
            PersonObservation(
                "person-" + p.id,
                assigned["helmet"].id if "helmet" in assigned else None,
                assigned["vest"].id if "vest" in assigned else None,
                p.id in ambiguous,
                obstructed,
                hint,
            )
        )
    return accepted, observations


class SafetyExpertSystem:
    """Adaptador de resultado para UI; no calcula cumplimiento por conteos."""

    def analyze(self, detections, conf_threshold=0.4, image_size=None):
        accepted, observations = observe(detections, conf_threshold, image_size)
        decisions = [decide(o) for o in observations]
        state = State.UNKNOWN
        if any(d.state == State.REVIEW for d in decisions):
            state = State.REVIEW
        stats = {
            name: sum(d.label == label and d.source == "model" for d in accepted)
            for name, label in [
                ("persons", "person"),
                ("helmets", "helmet"),
                ("vests", "vest"),
            ]
        }
        stats.update(
            total_detections=len(accepted),
            heuristic_hints=sum(d.source == "heuristic" for d in accepted),
            associated_pairs=sum(
                o.helmet_id is not None and o.vest_id is not None for o in observations
            ),
        )
        return {
            "level": state.value,
            "message": state.value,
            "action": "Revisar la evidencia y el contexto con un profesional. No constituye una orden operativa.",
            "stats": stats,
            "compliance": None,
            "rule": RULE_VERSION,
            "detections": [asdict(d) for d in accepted],
            "observations": [asdict(o) for o in observations],
            "decisions": [dict(asdict(d), state=d.state.value) for d in decisions],
        }


def summarize_video(frame_detections, threshold=0.4):
    """Conteos descriptivos por muestra, nunca personas únicas o cumplimiento."""
    frames = [SafetyExpertSystem().analyze(ds, threshold) for ds in frame_detections]
    return summarize_results(frames)


def summarize_results(frames):
    """Agrega evaluaciones existentes sin repetir ni alterar sus reglas."""
    n = len(frames)
    stats = {
        k: sum(f["stats"][k] for f in frames) / n if n else 0
        for k in ("persons", "helmets", "vests", "heuristic_hints")
    }
    stats.update(
        total_detections=sum(f["stats"]["total_detections"] for f in frames),
        associated_pairs=None,
    )
    return {
        "level": State.UNKNOWN.value,
        "compliance": None,
        "rule": RULE_VERSION,
        "stats": stats,
        "frames": frames,
        "sample_count": n,
    }
