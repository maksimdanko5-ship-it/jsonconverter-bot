# [ИЗМЕНЕНО] Парсинг даты: datetime.fromisoformat вместо срезов строки.
# Корректно обрабатывает форматы "2024-01-15T23:45:01" и "2024-01-15T23:45:01+03:00".

from collections import defaultdict
from datetime import datetime
from typing import Any

import config


def collect_stats(messages: list[dict]) -> dict[str, Any]:
    """
    Считает полную статистику по списку сообщений из parser.parse_json().
    Возвращает словарь с готовыми числами.
    """
    per_user: dict[str, int] = defaultdict(int)
    voice = video = photos = stickers = files = night = 0
    text_lengths: list[int] = []

    for msg in messages:
        author = msg.get("author", "Unknown")
        per_user[author] += 1

        mt = msg.get("media_type")
        if mt == "voice":
            voice += 1
        elif mt == "video":
            video += 1
        elif mt == "photo":
            photos += 1
        elif mt == "sticker":
            stickers += 1
        elif mt == "file":
            files += 1

        text = msg.get("text", "")
        if text:
            text_lengths.append(len(text))

        # [ИЗМЕНЕНО] Ночная активность через datetime.fromisoformat
        # Обрабатывает форматы со смещением часового пояса и без него.
        date_str = msg.get("date", "")
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str)
                if 0 <= dt.hour < 6:
                    night += 1
            except (ValueError, TypeError):
                # Дата в неизвестном формате — пропускаем без падения
                pass

    avg_len = round(sum(text_lengths) / len(text_lengths), 1) if text_lengths else 0.0

    return {
        "total_messages": len(messages),
        "messages_per_user": dict(per_user),
        "voice_messages": voice,
        "video_messages": video,
        "photos": photos,
        "stickers": stickers,
        "files": files,
        "avg_message_length": avg_len,
        "night_messages": night,
    }


def format_stats(stats: dict[str, Any], *, max_users: int | None = None) -> str:
    """
    Форматирует статистику в читаемый текст.
    max_users — сколько пользователей показывать (None = брать из config).
    """
    if max_users is None:
        max_users = config.MAX_STATS_PREVIEW_USERS

    total = stats["total_messages"]
    night = stats["night_messages"]
    night_pct = round(night / total * 100, 1) if total else 0

    lines = [
        "📊 Chat Statistics",
        "─" * 30,
        f"Total messages:      {total:,}",
        f"Voice messages:      {stats['voice_messages']:,}",
        f"Video messages:      {stats['video_messages']:,}",
        f"Photos:              {stats['photos']:,}",
        f"Stickers:            {stats['stickers']:,}",
        f"Files:               {stats['files']:,}",
        f"Avg message length:  {stats['avg_message_length']} chars",
        f"Night (00–06):       {night:,} ({night_pct}%)",
        "",
        "👥 Messages per user:",
        "─" * 30,
    ]

    sorted_users = sorted(
        stats["messages_per_user"].items(),
        key=lambda kv: kv[1],
        reverse=True,
    )

    for user, count in sorted_users[:max_users]:
        pct = round(count / total * 100, 1) if total else 0
        lines.append(f"  {user}: {count:,} ({pct}%)")

    if len(sorted_users) > max_users:
        lines.append(f"  … и ещё {len(sorted_users) - max_users} участников")

    return "\n".join(lines)
