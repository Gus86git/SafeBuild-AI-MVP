"""Carga exclusivamente local y trazabilidad factual de artefactos."""

import hashlib
import json
import time
import os
from importlib import metadata
from pathlib import Path


def load_local_model(factory, root, paths=None):
    errors = []
    for relative in paths or ("models/best.pt", "yolov8n.pt"):
        path = Path(root) / relative
        if not path.is_file():
            continue  # No pasar nombres ausentes a YOLO: podría descargarlos.
        try:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            started = time.perf_counter()
            model = factory(str(path.resolve()))
            load_seconds = time.perf_counter() - started
            names = model.names
            classes = list(names.values()) if isinstance(names, dict) else list(names)
            return (
                model,
                {
                    "path": relative,
                    "sha256": digest.hexdigest(),
                    "classes": classes,
                    "provenance": "No verificada",
                    "license": "No verificada",
                    "ppe_validated": False,
                    "load_seconds": load_seconds,
                    "device": "cpu",
                },
                errors,
            )
        except Exception as exc:
            errors.append(f"{relative}: {type(exc).__name__}")
    return None, None, errors


def dependency_versions():
    versions = {}
    for name in (
        "streamlit",
        "ultralytics",
        "opencv-python",
        "opencv-python-headless",
        "numpy",
        "Pillow",
        "pandas",
        "xlsxwriter",
        "plotly",
        "torch",
    ):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "No instalada en este intérprete"
    return versions


def runtime_model(root):
    configured = os.environ.get("SAFEGUARD_MODEL_PATH", "models/epp_v1/best.pt")
    paths = (configured,)
    if not (Path(root) / configured).is_file():
        return None, None, ["No hay pesos locales autorizados disponibles."]
    try:

        def factory(path):
            os.environ["YOLO_OFFLINE"] = "true"
            os.environ["YOLO_AUTOINSTALL"] = "false"
            os.environ.setdefault(
                "YOLO_CONFIG_DIR", str(Path(root) / "data/local/ultralytics")
            )
            from ultralytics import YOLO
            from ultralytics import settings

            settings.update({"sync": False})
            import torch

            torch.set_num_threads(min(4, os.cpu_count() or 1))
            model = YOLO(path, task="detect")
            model.to("cpu")
            return model

        return load_authorized_model(factory, root, paths=paths)
    except Exception as exc:
        return None, None, [f"Inferencia no disponible ({type(exc).__name__})."]


def load_authorized_model(factory, root, paths=None):
    """La aplicación solo carga artefactos aprobados por hash y procedencia.

    No se deserializa un .pt desconocido. El manifiesto es configuración local
    administrada por el responsable del proyecto, no contenido de uploads.
    """
    manifest = Path(root) / "models/authorized.json"
    if not manifest.is_file():
        return None, None, ["No hay manifiesto local de modelos autorizados."]
    try:
        records = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(records, dict):
            raise ValueError("manifest")
    except (OSError, ValueError):
        return None, None, ["El manifiesto local de autorización no es válido."]

    def authorized_factory(path):
        relative = Path(path).relative_to(Path(root).resolve()).as_posix()
        record = records.get(relative, {})
        if (
            not isinstance(record, dict)
            or record.get("approved") is not True
            or not str(record.get("source", "")).strip()
            or not str(record.get("license", "")).strip()
        ):
            raise ValueError("Artefacto sin autorización, fuente o licencia declarada")
        with open(path, "rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != record.get("sha256"):
            raise ValueError("Hash no autorizado")
        model = factory(path)
        names = model.names
        classes = list(names.values()) if isinstance(names, dict) else list(names)
        expected = record.get("expected_classes")
        if expected is not None and classes != expected:
            raise ValueError("Clases del modelo diferentes al manifiesto autorizado")
        return model

    model, info, errors = load_local_model(authorized_factory, root, paths=paths)
    if info:
        relative = (
            (Path(root) / info["path"])
            .resolve()
            .relative_to(Path(root).resolve())
            .as_posix()
        )
        record = records[relative]
        info.update(
            provenance=record["source"],
            license=record["license"],
            authorization="Declaración local y hash coincidente; no certifica precisión",
            ppe_validated=False,
            version=record.get("version", "No registrada"),
            expected_classes_verified=bool(record.get("expected_classes")),
        )
    return model, info, errors
