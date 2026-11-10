"""Exploratory real YOLO evaluation on user-authorized photographs; no training."""

from pathlib import Path
from collections import Counter
import hashlib
import json
import platform
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from safeguard.models import runtime_model, dependency_versions
from safeguard.media import read_image, png_bytes, explore_video
from safeguard.vision import analyze_image
from safeguard.workflow import image_record, video_record
from safeguard import storage
from safeguard.reporting import csv_bytes, excel_bytes

CASES = [
    (
        "Contraste de seguridad en obra.png",
        2,
        2,
        1,
        "Escena relativamente simple; dos personas. Casco y chaleco no uniformes. EPP fuera de V1 visibles.",
    ),
    (
        "Obra en construcción con equipos de protección diversos.png",
        3,
        3,
        3,
        "Tres personas; oclusiones parciales de torso y piernas; persona posterior más pequeña.",
    ),
    (
        "Obras en marcha bajo el cielo urbano.png",
        10,
        9,
        8,
        "Escena densa; personas pequeñas al fondo; elementos parcialmente ocultos y algunos EPP no visibles.",
    ),
    (
        "Obreros con planos en una obra urbana.png",
        2,
        2,
        2,
        "Dos personas; plano oculta parte de torso y guantes; contraste y oclusión parcial.",
    ),
    (
        "Trabajadores en plena obra de construcción.png",
        3,
        3,
        3,
        "Tres personas a distintas escalas; carretilla, estructura y material ocluyen regiones.",
    ),
]


def memory():
    try:
        import psutil

        info = psutil.Process().memory_info()
        return {
            "rss_bytes": info.rss,
            "peak_working_set_bytes": getattr(info, "peak_wset", None),
            "system_ram_bytes": psutil.virtual_memory().total,
        }
    except ImportError:
        return {"available": False}


def main():
    out = ROOT / "output/audit-fase3a/vision"
    out.mkdir(parents=True, exist_ok=True)
    if (out / "results.json").exists():
        raise RuntimeError("Do not overwrite completed evidence")
    manifest = []
    for name, persons, helmets, vests, note in CASES:
        path = ROOT / "Imagenes de prueba para deteccion" / name
        manifest.append(
            {
                "filename": name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "provenance": "user_declared_real_authorized_not_independently_verified",
                "preliminary_visible_persons": persons,
                "preliminary_visible_helmets": helmets,
                "preliminary_visible_vests": vests,
                "notes": note,
            }
        )
    (out / "labels-before-inference.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8"
    )
    start = perf_counter()
    model, info, errors = runtime_model(ROOT)
    load = perf_counter() - start
    if model is None:
        raise RuntimeError("Local authorized model unavailable")
    db = out / "verification.sqlite3"
    storage.initialize(db)
    rows = []
    records = []
    for index, case in enumerate(manifest, 1):
        path = ROOT / "Imagenes de prueba para deteccion" / case["filename"]
        data = path.read_bytes()
        image = read_image(data, path.name)
        started = perf_counter()
        result, annotated = analyze_image(image, model, 0.4, use_color=False, imgsz=480)
        elapsed = perf_counter() - started
        record = image_record("evaluation-" + str(index) + ".png", result, info, 0.4)
        identifier, _ = storage.save_analysis(
            db,
            record,
            "TECHCORP-DEMO",
            "OBRA-NORTE-001",
            case["sha256"],
            origin="real_inference",
            input_origin=case["provenance"],
        )
        duplicate, created = storage.save_analysis(
            db,
            record,
            "TECHCORP-DEMO",
            "OBRA-NORTE-001",
            case["sha256"],
            origin="real_inference",
            input_origin=case["provenance"],
        )
        assert duplicate == identifier and not created
        (out / f"{index:02d}-annotated.png").write_bytes(png_bytes(annotated))
        stored = storage.get_analysis(db, identifier, "TECHCORP-DEMO", "OBRA-NORTE-001")
        records.append(stored)
        (out / f"{index:02d}-result.json").write_text(
            storage.encode(result), encoding="utf8"
        )
        rows.append(
            dict(
                case=case,
                image_size=image.size,
                stats=result["stats"],
                class_counts=dict(Counter(d["label"] for d in result["detections"])),
                states=dict(Counter(d["state"] for d in result["decisions"])),
                inference_seconds=elapsed,
                analysis_id=identifier,
                memory=memory(),
                count_deltas={
                    k: result["stats"][k] - case["preliminary_visible_" + k]
                    for k in ("persons", "helmets", "vests")
                },
            )
        )
    import cv2

    source = ROOT / "Imagenes de prueba para deteccion" / CASES[0][0]
    frame = cv2.imdecode(
        __import__("numpy").frombuffer(source.read_bytes(), dtype="uint8"),
        cv2.IMREAD_COLOR,
    )
    clip = out / "synthetic-repeated-frame.avi"
    writer = cv2.VideoWriter(
        str(clip), cv2.VideoWriter_fourcc(*"MJPG"), 2, (frame.shape[1], frame.shape[0])
    )
    assert writer.isOpened()
    for _ in range(12):
        writer.write(frame)
    writer.release()
    started = perf_counter()
    video = explore_video(
        clip.read_bytes(),
        clip.name,
        count=3,
        analyzer=lambda image: analyze_image(
            image, model, 0.4, use_color=False, imgsz=480
        ),
        max_elapsed=120,
        temp_dir=out,
    )
    video_seconds = perf_counter() - started
    record = video_record("synthetic-repeated-frame.avi", video, info, 0.4)
    vid, _ = storage.save_analysis(
        db,
        record,
        "TECHCORP-DEMO",
        "OBRA-NORTE-001",
        hashlib.sha256(clip.read_bytes()).hexdigest(),
        origin="experimental",
        input_origin="synthetic_repeated_frames_from_authorized_photo",
    )
    assert len(video["samples"]) == 3 and video["inference_ran"]
    (out / "image-analyses.csv").write_bytes(csv_bytes(records))
    (out / "image-analyses.xlsx").write_bytes(excel_bytes(records))
    with storage.connect(db) as c:
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not c.execute("PRAGMA foreign_key_check").fetchall()
        assert c.execute("SELECT count(*) FROM analyses").fetchone()[0] == 6
    report = {
        "model_sha256": info["sha256"],
        "classes": info["classes"],
        "load_seconds_including_imports": load,
        "device": "cpu",
        "imgsz": 480,
        "threshold": 0.4,
        "python": platform.python_version(),
        "cpu": platform.processor(),
        "versions": dependency_versions(),
        "memory_after": memory(),
        "images": rows,
        "video": {
            "provenance": "synthetic repeated still frames, not real motion",
            "sample_indices": [s["index"] for s in video["samples"]],
            "analysis_id": vid,
            "elapsed_seconds": video_seconds,
            "real_codec_and_model": True,
        },
        "sqlite_integrity": "ok",
        "duplicates_prevented": True,
        "exports_generated": ["CSV", "XLSX", "PNG"],
        "limitations": [
            "Same-team preliminary visual counts, no boxes or independent labels; no precision/recall/mAP computed.",
            "Photographic provenance declared by user; not independently authenticated.",
            "No claim of mandatory PPE, legal compliance or incident confirmation.",
        ],
    }
    (out / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8"
    )
    print(
        json.dumps(
            {
                "load_seconds": load,
                "images": [
                    {k: r[k] for k in ("stats", "count_deltas", "inference_seconds")}
                    for r in rows
                ],
                "video_seconds": video_seconds,
                "memory": memory(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
