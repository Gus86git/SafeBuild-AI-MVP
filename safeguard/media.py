"""Ingreso validado y muestreo descriptivo. Sin inferencia ni tracking implícitos."""

from io import BytesIO
from pathlib import Path
import math
import os
import tempfile
import time
import warnings

IMAGE_BYTES = 20 * 1024 * 1024
VIDEO_BYTES = 100 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_SIDE = 8192
MAX_VIDEO_FRAMES = 6000
MAX_VIDEO_SECONDS = 120
MAX_SAMPLES = 60
IMAGE_FORMATS = {
    "JPEG": {".jpg", ".jpeg", ".jpe", ".jfif"},
    "PNG": {".png"},
    "BMP": {".bmp"},
    "WEBP": {".webp"},
    "TIFF": {".tif", ".tiff"},
    "GIF": {".gif"},
    "AVIF": {".avif"},
}
IMAGE_EXTENSIONS = sorted(
    ext[1:] for values in IMAGE_FORMATS.values() for ext in values
)


class MediaError(ValueError):
    pass


def check_size(data, limit):
    if not data:
        raise MediaError("El archivo está vacío.")
    if len(data) > limit:
        raise MediaError(f"El archivo supera el límite de {limit // (1024 * 1024)} MB.")


def check_dimensions(width, height):
    if (
        width <= 0
        or height <= 0
        or max(width, height) > MAX_SIDE
        or width * height > MAX_PIXELS
    ):
        raise MediaError(
            "Dimensiones fuera de límite: hasta 8192 px por lado y 20 megapíxeles."
        )


def read_image(data, name, mime=None, *, max_bytes=IMAGE_BYTES):
    from PIL import Image, ImageOps, UnidentifiedImageError

    check_size(data, min(max_bytes, IMAGE_BYTES))
    formats = IMAGE_FORMATS
    mimes = {
        "JPEG": {"image/jpeg", "image/pjpeg"},
        "PNG": {"image/png"},
        "BMP": {"image/bmp", "image/x-ms-bmp"},
        "WEBP": {"image/webp"},
        "TIFF": {"image/tiff"},
        "GIF": {"image/gif"},
        "AVIF": {"image/avif"},
    }
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as probe:
                fmt = probe.format
                if fmt not in formats or Path(name).suffix.lower() not in formats[fmt]:
                    raise MediaError(
                        "El contenido y la extensión de imagen no coinciden o no están admitidos."
                    )
                if (
                    mime
                    and mime != "application/octet-stream"
                    and mime not in mimes[fmt]
                ):
                    raise MediaError("El MIME declarado no coincide con la imagen.")
                check_dimensions(*probe.size)
                probe.verify()
            with Image.open(BytesIO(data)) as image:
                # An uploaded animation or multipage photo is a still-image task.
                # Explicitly retain this fact for the UI rather than hiding frames.
                frames = getattr(image, "n_frames", 1)
                image.seek(0)
                image.load()
                result = ImageOps.exif_transpose(image).convert("RGB")
                result.info["source_frames"] = frames
                return result
    except MediaError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise MediaError("La imagen está corrupta o no se puede decodificar.") from exc


def png_bytes(image, max_side=None):
    image = image.copy()
    if max_side:
        image.thumbnail((max_side, max_side))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def video_format(data, name, mime=None, *, max_bytes=VIDEO_BYTES):
    check_size(data, min(max_bytes, VIDEO_BYTES))
    ext = Path(name).suffix.lower()
    if ext not in {".mp4", ".mov", ".avi", ".mkv"}:
        raise MediaError("Formato de video no admitido.")
    signatures = {
        ".mp4": len(data) >= 12 and data[4:8] == b"ftyp",
        ".mov": len(data) >= 12 and data[4:8] in (b"ftyp", b"moov", b"mdat", b"wide"),
        ".avi": data[:4] == b"RIFF" and data[8:12] == b"AVI ",
        ".mkv": data[:4] == b"\x1aE\xdf\xa3",
    }
    if not signatures[ext]:
        raise MediaError("La cabecera no corresponde a la extensión declarada.")
    allowed = {
        ".mp4": {"video/mp4"},
        ".mov": {"video/quicktime"},
        ".avi": {"video/x-msvideo", "video/avi"},
        ".mkv": {"video/x-matroska", "video/matroska"},
    }
    if mime and mime != "application/octet-stream" and mime not in allowed[ext]:
        raise MediaError("El MIME declarado no corresponde al contenedor.")
    return ext


def sample_indices(total, count):
    if total < 1 or not 1 <= count <= MAX_SAMPLES:
        raise MediaError("Cantidad de fotogramas inválida.")
    if count == 1:
        return [0]
    return sorted({round(i * (total - 1) / (count - 1)) for i in range(count)})


def explore_video(
    data,
    name,
    mime=None,
    *,
    count=12,
    analyzer=None,
    cv_module=None,
    temp_dir=None,
    max_elapsed=30,
    max_bytes=VIDEO_BYTES,
    progress=None,
):
    """Decodifica y conserva índices reales. analyzer=None significa sin inferencia.

    Las cotas limitan trabajo entre llamadas; no pueden interrumpir un codec o
    inferencia nativa bloqueados. Para archivos hostiles se requeriría aislamiento.
    """
    from PIL import Image

    ext = video_format(data, name, mime, max_bytes=max_bytes)
    if cv_module is None:
        try:
            import cv2 as cv_module
        except ImportError as exc:
            raise MediaError(
                "OpenCV no está disponible para explorar el video."
            ) from exc
    cap = None
    tmp = None
    started = time.monotonic()
    try:
        with tempfile.NamedTemporaryFile(
            suffix=ext, delete=False, dir=temp_dir
        ) as stream:
            tmp = stream.name
            stream.write(data)
        cap = cv_module.VideoCapture(tmp)
        if not cap.isOpened():
            raise MediaError(
                "El video no se pudo abrir con el decodificador disponible."
            )
        raw_total = cap.get(cv_module.CAP_PROP_FRAME_COUNT)
        if not math.isfinite(raw_total) or not 1 <= raw_total <= MAX_VIDEO_FRAMES:
            raise MediaError(
                "Conteo de fotogramas desconocido o superior al límite de 6000."
            )
        total = int(raw_total)
        fps = cap.get(cv_module.CAP_PROP_FPS)
        fps = fps if math.isfinite(fps) and fps > 0 else None
        if fps and total / fps > MAX_VIDEO_SECONDS:
            raise MediaError("El video supera el límite estimado de 120 segundos.")
        targets = set(sample_indices(total, count))
        samples = []
        previous_time = None
        resolution = None
        for index in range(total):
            if time.monotonic() - started > max_elapsed:
                raise MediaError(
                    "Se alcanzó el tiempo de procesamiento permitido. Use un clip más corto."
                )
            ok, frame = cap.read()
            if not ok or frame is None:
                raise MediaError(
                    f"Falló la decodificación del fotograma {index}; no se guarda un análisis parcial."
                )
            check_dimensions(frame.shape[1], frame.shape[0])
            resolution = (frame.shape[1], frame.shape[0])
            if progress and (index % max(1, total // 100) == 0 or index == total - 1):
                progress((index + 1) / total)
            if index not in targets:
                continue
            image = Image.fromarray(cv_module.cvtColor(frame, cv_module.COLOR_BGR2RGB))
            milliseconds = cap.get(cv_module.CAP_PROP_POS_MSEC)
            seconds = milliseconds / 1000 if math.isfinite(milliseconds) else None
            if (
                seconds is not None
                and seconds >= 0
                and (index == 0 or seconds > 0)
                and (previous_time is None or seconds > previous_time)
            ):
                time_kind = "Referencia del decodificador (no verificada)"
            else:
                seconds = index / fps if fps else None
                time_kind = "Estimada por índice/FPS" if fps else "No disponible"
            if seconds is not None:
                previous_time = seconds
            result, annotated = analyzer(image) if analyzer else (None, None)
            samples.append(
                {
                    "index": index,
                    "seconds": seconds,
                    "time_kind": time_kind,
                    "original_png": png_bytes(image, 1280),
                    "annotated_png": png_bytes(annotated, 1280)
                    if annotated is not None
                    else None,
                    "result": result,
                }
            )
        return {
            "samples": samples,
            "total_frames": total,
            "fps": fps,
            "resolution": resolution,
            "estimated_duration": total / fps if fps else None,
            "elapsed_seconds": time.monotonic() - started,
            "omitted": total - len(samples),
            "inference_ran": analyzer is not None,
        }
    except MediaError:
        raise
    except Exception as exc:
        raise MediaError(
            f"No se completó el procesamiento ({type(exc).__name__})."
        ) from exc
    finally:
        try:
            if cap is not None:
                cap.release()
        finally:
            if tmp is not None:
                os.unlink(tmp)
