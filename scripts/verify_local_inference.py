"""Explicit local smoke test. No downloads, training or synthetic detections."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from safeguard.models import runtime_model, dependency_versions
from safeguard.media import read_image, png_bytes
from safeguard.vision import analyze_image
from safeguard.workflow import image_record
from safeguard import storage
from safeguard.reporting import csv_bytes, excel_bytes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "output/verification-fase2a"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = args.image.read_bytes()
    image = read_image(data, args.image.name)
    model, info, errors = runtime_model(ROOT)
    if model is None:
        raise RuntimeError("Modelo no cargado: " + repr(errors))
    if next(model.model.parameters()).device.type != "cpu":
        raise AssertionError("Se esperaba CPU")
    result, annotated = analyze_image(image, model, 0.4, use_color=False, imgsz=480)
    record = image_record(args.image.name, result, info, 0.4)
    database = args.output / "verification.sqlite3"
    storage.initialize(database)
    identifier, created = storage.save_analysis(
        database,
        record,
        "TECHCORP-DEMO",
        "OBRA-NORTE-001",
        sha256(data).hexdigest(),
        origin="real_inference",
        input_origin="supplied_notebook_display_resized_origin_unverified",
    )
    duplicate, second_created = storage.save_analysis(
        database,
        record,
        "TECHCORP-DEMO",
        "OBRA-NORTE-001",
        sha256(data).hexdigest(),
        origin="real_inference",
        input_origin="supplied_notebook_display_resized_origin_unverified",
    )
    assert duplicate == identifier and not second_created
    loaded = storage.history(database, "TECHCORP-DEMO", "OBRA-NORTE-001")
    saved = next(r for r in loaded if r["analysis_id"] == identifier)
    assert saved["detections"] == json.loads(storage.encode(result["detections"]))
    assert saved["observations"] == json.loads(storage.encode(result["observations"]))
    assert saved["compliance"] is None
    with storage.connect(database) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        normalized_count = connection.execute(
            "SELECT count(*) FROM detections WHERE analysis_id=?", (identifier,)
        ).fetchone()[0]
        assert normalized_count == len(result["detections"])
    (args.output / "annotated.png").write_bytes(png_bytes(annotated))
    (args.output / "analysis.csv").write_bytes(csv_bytes([saved]))
    (args.output / "analysis.xlsx").write_bytes(excel_bytes([saved]))
    summary = dict(
        model=info,
        versions=dependency_versions(),
        python=platform.python_version(),
        cpu=platform.processor(),
        image_size=image.size,
        input_sha256=sha256(data).hexdigest(),
        input_origin=saved["input_origin"],
        stats=result["stats"],
        class_counts=dict(Counter(d["label"] for d in result["detections"])),
        performance=result["performance"],
        configuration=result["configuration"],
        sqlite_id=identifier,
        duplicate_prevented=True,
        foreign_keys_valid=True,
        detections_roundtrip=True,
        observations_roundtrip=True,
        limitations=[
            "Una imagen aportada; no benchmark ni validación de precisión.",
            "Sin anotaciones independientes; origen real/sintético de la imagen no acreditado.",
        ],
    )
    (args.output / "result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
