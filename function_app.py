import azure.functions as func
import logging
import json
import xml.etree.ElementTree as ET
import xml.dom.minidom

app = func.FunctionApp()


def _pretty_xml(raw: str) -> str:
    """Intenta formatear el XML de forma legible."""
    try:
        dom = xml.dom.minidom.parseString(raw)
        return dom.toprettyxml(indent="  ")
    except Exception:
        return raw


def _pretty_json(raw: str) -> str:
    """Intenta formatear el JSON de forma legible."""
    try:
        obj = json.loads(raw)
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except Exception:
        return raw


def _size_label(n: int) -> str:
    if n < 1024:
        return f"{n} bytes"
    elif n < 1024 * 1024:
        return f"{n / 1024:.2f} KB"
    else:
        return f"{n / (1024*1024):.2f} MB"


@app.route(
    route="diagnostico",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def diagnostico(req: func.HttpRequest) -> func.HttpResponse:
    """
    Endpoint de diagnóstico para recibir eventos de cámaras Hikvision (ISAPI Listening)
    o cualquier otra fuente HTTP. Registra en logs todo lo que llega.
    """

    sep = "=" * 60

    # ── Información básica ─────────────────────────────────────────
    logging.info(sep)
    logging.info("📡  NUEVA SOLICITUD RECIBIDA")
    logging.info(sep)
    logging.info(f"  Método   : {req.method}")
    logging.info(f"  URL      : {req.url}")

    # ── Headers ───────────────────────────────────────────────────
    logging.info("─── HEADERS ───────────────────────────────────────────")
    for key, value in req.headers.items():
        logging.info(f"  {key}: {value}")

    # ── Params de query string ─────────────────────────────────────
    if req.params:
        logging.info("─── QUERY PARAMS ──────────────────────────────────────")
        for key, value in req.params.items():
            logging.info(f"  {key} = {value}")

    # ── Body / Payload ─────────────────────────────────────────────
    logging.info("─── BODY / PAYLOAD ────────────────────────────────────")

    content_type: str = req.headers.get("Content-Type", "").lower().split(";")[0].strip()
    body_bytes: bytes = req.get_body()
    body_size: int = len(body_bytes)

    if body_size == 0:
        logging.info("  (sin cuerpo / body vacío)")

    elif "json" in content_type:
        # ── JSON ──────────────────────────────────────────────────
        raw_text = body_bytes.decode("utf-8", errors="replace")
        pretty = _pretty_json(raw_text)
        logging.info(f"  Tipo detectado : JSON")
        logging.info(f"  Tamaño         : {_size_label(body_size)}")
        logging.info("  Contenido:")
        for line in pretty.splitlines():
            logging.info(f"    {line}")

    elif "xml" in content_type or body_bytes.lstrip().startswith(b"<?xml") or body_bytes.lstrip().startswith(b"<"):
        # ── XML ───────────────────────────────────────────────────
        raw_text = body_bytes.decode("utf-8", errors="replace")
        pretty = _pretty_xml(raw_text)
        logging.info(f"  Tipo detectado : XML")
        logging.info(f"  Tamaño         : {_size_label(body_size)}")
        logging.info("  Contenido:")
        for line in pretty.splitlines():
            logging.info(f"    {line}")

    elif "form" in content_type:
        # ── Form data ─────────────────────────────────────────────
        logging.info(f"  Tipo detectado : Form Data (application/x-www-form-urlencoded o multipart)")
        logging.info(f"  Tamaño         : {_size_label(body_size)}")
        try:
            form_text = body_bytes.decode("utf-8", errors="replace")
            logging.info(f"  Contenido raw  : {form_text}")
        except Exception as e:
            logging.warning(f"  No se pudo decodificar el form: {e}")

    elif "text" in content_type:
        # ── Texto plano ───────────────────────────────────────────
        raw_text = body_bytes.decode("utf-8", errors="replace")
        logging.info(f"  Tipo detectado : Texto plano ({content_type})")
        logging.info(f"  Tamaño         : {_size_label(body_size)}")
        logging.info(f"  Contenido      : {raw_text}")

    elif content_type in ("application/octet-stream", "") and body_size > 0:
        # ── Binario / archivo desconocido ─────────────────────────
        # Intentar adivinar si es JSON o XML igualmente
        stripped = body_bytes.lstrip()
        if stripped.startswith(b"{") or stripped.startswith(b"["):
            raw_text = body_bytes.decode("utf-8", errors="replace")
            pretty = _pretty_json(raw_text)
            logging.info(f"  Tipo detectado : JSON (sin Content-Type correcto)")
            logging.info(f"  Tamaño         : {_size_label(body_size)}")
            for line in pretty.splitlines():
                logging.info(f"    {line}")
        elif stripped.startswith(b"<"):
            raw_text = body_bytes.decode("utf-8", errors="replace")
            pretty = _pretty_xml(raw_text)
            logging.info(f"  Tipo detectado : XML (sin Content-Type correcto)")
            logging.info(f"  Tamaño         : {_size_label(body_size)}")
            for line in pretty.splitlines():
                logging.info(f"    {line}")
        else:
            # Archivo binario real
            ext_guess = _guess_extension(body_bytes)
            logging.info(f"  Tipo detectado : Archivo binario / desconocido")
            logging.info(f"  Content-Type   : '{content_type or '(vacío)'}'")
            logging.info(f"  Extensión prob.: {ext_guess}")
            logging.info(f"  Tamaño         : {_size_label(body_size)}")
            logging.info(f"  Primeros bytes : {body_bytes[:32].hex()}")
    else:
        # ── Cualquier otro tipo ───────────────────────────────────
        logging.info(f"  Tipo detectado : {content_type or '(desconocido)'}")
        logging.info(f"  Tamaño         : {_size_label(body_size)}")
        try:
            text = body_bytes.decode("utf-8", errors="replace")
            logging.info(f"  Contenido      : {text[:500]}")
        except Exception:
            logging.info(f"  Primeros bytes : {body_bytes[:32].hex()}")

    logging.info(sep)
    logging.info("✅  FIN DE LA SOLICITUD")
    logging.info(sep)

    # Respuesta mínima para que la cámara no reintente
    return func.HttpResponse(
        body=json.dumps({"status": "ok", "message": "Solicitud registrada correctamente"}),
        status_code=200,
        mimetype="application/json",
    )


def _guess_extension(data: bytes) -> str:
    """Adivina la extensión de un archivo binario por sus magic bytes."""
    sigs = {
        b"\xFF\xD8\xFF": ".jpg",
        b"\x89PNG": ".png",
        b"GIF8": ".gif",
        b"BM": ".bmp",
        b"RIFF": ".wav/.avi",
        b"\x00\x00\x00\x18ftypmp4": ".mp4",
        b"\x00\x00\x00\x20ftyp": ".mp4",
        b"PK\x03\x04": ".zip",
        b"%PDF": ".pdf",
        b"\x1F\x8B": ".gz",
        b"OggS": ".ogg",
    }
    for sig, ext in sigs.items():
        if data.startswith(sig):
            return ext
    return "(desconocida)"