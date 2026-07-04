# Без изменений в логике — файл оставлен для полноты комплекта.

from pathlib import Path

import stats as stats_module

# Метки для медиа-типов в TXT
_MEDIA_LABELS: dict[str, str] = {
    "voice":   "[Голосовое]",
    "video":   "[Видео]",
    "photo":   "[Фото]",
    "sticker": "[Стикер]",
    "file":    "[Файл]",
}


def format_messages(messages: list[dict], output_path: str) -> str:
    """
    Записывает TXT файл: сначала статистика, потом все сообщения.
    Возвращает путь к записанному файлу.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []

    if not messages:
        lines.append("No messages found.")
        path.write_text("\n".join(lines), encoding="utf-8")
        return str(path)

    # ── Блок статистики ──────────────────────────────────────────────────────
    chat_stats = stats_module.collect_stats(messages)
    lines.append(stats_module.format_stats(chat_stats, max_users=None))
    lines.append("")
    lines.append("=" * 50)
    lines.append("")

    # ── Блок сообщений ───────────────────────────────────────────────────────
    for msg in messages:
        author = msg.get("author", "Unknown")
        text   = msg.get("text", "")
        mt     = msg.get("media_type")
        date   = msg.get("date", "")

        date_short = date[:10] if "T" in date else date
        time_short = date[11:16] if len(date) >= 16 else ""
        timestamp  = f"[{date_short} {time_short}]" if date_short else ""

        if mt and not text:
            body = _MEDIA_LABELS.get(mt, f"[{mt}]")
        elif text:
            body = text
        else:
            continue

        lines.append(f"{timestamp} {author}: {body}")

    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)
