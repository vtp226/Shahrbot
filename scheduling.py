import os
import logging
import datetime as dt
from zoneinfo import ZoneInfo

from telegram.constants import ParseMode
from telegram.error import TelegramError

import db

logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "Asia/Tehran"))


def _parse_hhmm(value: str):
    h, m = value.split(":")
    return int(h), int(m)


def generate_slots_for_window(window: dict, day: dt.date):
    """Return a sorted list of timezone-aware datetimes for one window on one day."""
    sh, sm = _parse_hhmm(window["start_time"])
    start_dt = dt.datetime(day.year, day.month, day.day, sh, sm, tzinfo=TIMEZONE)

    if window["end_time"] in ("24:00", "0:00", "00:00") and window["end_time"] != window["start_time"]:
        end_dt = dt.datetime(day.year, day.month, day.day, tzinfo=TIMEZONE) + dt.timedelta(days=1)
    else:
        eh, em = _parse_hhmm(window["end_time"])
        end_dt = dt.datetime(day.year, day.month, day.day, eh, em, tzinfo=TIMEZONE)
        if end_dt <= start_dt:
            end_dt += dt.timedelta(days=1)

    step = dt.timedelta(hours=float(window["interval_hours"]))
    if step.total_seconds() <= 0:
        return []

    slots = []
    t = start_dt
    while t <= end_dt:
        slots.append(t)
        t += step
    return slots


async def assign_slots_for_chat(chat_id: int):
    windows = await db.get_windows(chat_id)
    if not windows:
        return

    now = dt.datetime.now(TIMEZONE)
    today = now.date()
    tomorrow = today + dt.timedelta(days=1)
    day_after = today + dt.timedelta(days=2)

    all_slots = []
    for w in windows:
        for day in (today, tomorrow, day_after):
            all_slots.extend(generate_slots_for_window(w, day))

    all_slots = sorted(set(s for s in all_slots if s > now))

    used = await db.get_scheduled_times(chat_id)
    used_dt = set()
    for u in used:
        try:
            used_dt.add(dt.datetime.fromisoformat(u))
        except ValueError:
            pass

    available = [s for s in all_slots if s not in used_dt]

    pending = await db.get_pending_posts(chat_id)
    if not pending:
        return

    for post, slot in zip(pending, available):
        await db.assign_schedule(post["id"], slot.isoformat())


async def send_post(bot, post: dict):
    chat_id = post["chat_id"]
    caption = post["text"] or None
    ctype = post["content_type"]
    try:
        if ctype == "text":
            await bot.send_message(chat_id=chat_id, text=post["text"] or "")
        elif ctype == "photo":
            await bot.send_photo(chat_id=chat_id, photo=post["file_id"], caption=caption)
        elif ctype == "video":
            await bot.send_video(chat_id=chat_id, video=post["file_id"], caption=caption)
        elif ctype == "animation":
            await bot.send_animation(chat_id=chat_id, animation=post["file_id"], caption=caption)
        elif ctype == "sticker":
            await bot.send_sticker(chat_id=chat_id, sticker=post["file_id"])
        elif ctype == "voice":
            await bot.send_voice(chat_id=chat_id, voice=post["file_id"], caption=caption)
        elif ctype == "audio":
            await bot.send_audio(chat_id=chat_id, audio=post["file_id"], caption=caption)
        elif ctype == "document":
            await bot.send_document(chat_id=chat_id, document=post["file_id"], caption=caption)
        elif ctype == "video_note":
            await bot.send_video_note(chat_id=chat_id, video_note=post["file_id"])
        else:
            logger.warning("Unknown content_type for post %s", post["id"])
            await db.mark_failed(post["id"])
            return
        await db.mark_sent(post["id"])
    except TelegramError as e:
        logger.error("Failed to send post %s to chat %s: %s", post["id"], chat_id, e)
        await db.mark_failed(post["id"])


async def tick(context):
    """Periodic job: assign pending posts to slots, then send anything due."""
    chat_ids = await db.get_active_chat_ids()
    for chat_id in chat_ids:
        try:
            await assign_slots_for_chat(chat_id)
        except Exception:
            logger.exception("assign_slots_for_chat failed for %s", chat_id)

    now_iso = dt.datetime.now(TIMEZONE).isoformat()
    due = await db.get_due_posts(now_iso)
    for post in due:
        await send_post(context.bot, post)
