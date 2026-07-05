import logging
from pathlib import Path

try:
    import orjson
    _FAST_JSON = True
except ImportError:
    import json as _json
    _FAST_JSON = False

logger = logging.getLogger(__name__)

_MEDIA_TYPE_MAP = {
    "voice_message": "voice",
    "video_message": "video",
    "sticker":       "sticker",
}

def _extract_text(raw_text) -> str:
    if isinstance(raw_text, str):
        return raw_text.strip()
    if isinstance(raw_text, list):
        parts = []
        for item in raw_text:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", ""))
        return "".join(parts).strip()
    return ""

def _detect_media_type(msg: dict) -> str | None:
    raw_mt = msg.get("media_type", "")
    if raw_mt in _MEDIA_TYPE_MAP:
        return _MEDIA_TYPE_MAP[raw_mt]
    if msg.get("photo"):
        return "photo"
    if msg.get("file"):
        return "file"
    return None

def parse_json(path: str) -> list[dict]:
    try:
        raw_bytes = Path(path).read_bytes()
        if _FAST_JSON:
            data = orjson.loads(raw_bytes)
        else:
            data = _json.loads(raw_bytes.decode("utf-8-sig"))
    except Exception as e:
        raise ValueError(f"Invalid JSON file: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object, not array or scalar")
    if "messages" not in data:
        raise ValueError("JSON is missing required 'messages' field")

    raw_messages = data["messages"]
    if not isinstance(raw_messages, list):
        raise ValueError("'messages' must be a list")

    result = []
    skipped = 0

    for msg in raw_messages:
        if not isinstance(msg, dict):
            skipped += 1
            continue
        if msg.get("type") in ("service", "system"):
            continue
        author = msg.get("from") or msg.get("actor") or "Unknown"
        text = _extract_text(msg.get("text", ""))
        media_type = _detect_media_type(msg)
        date = msg.get("date", "")
        if not text and not media_type:
            skipped += 1
            continue
        result.append({
            "author":     str(author),
            "text":       text,
            "date":       date,
            "media_type": media_type,
        })

    if skipped:
        logger.debug("Skipped %d non-message entries", skipped)

    return result