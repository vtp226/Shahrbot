import datetime as dt
from zoneinfo import ZoneInfo
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import db

TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "Asia/Tehran"))


def _extract_content(message):
    """Return (content_type, text, file_id) or (None, None, None) if unsupported."""
    if message.photo:
        return "photo", message.caption or "", message.photo[-1].file_id
    if message.video:
        return "video", message.caption or "", message.video.file_id
    if message.text:
        return "text", message.text, None
    return None, None, None


async def incoming_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    message = update.message
    content_type, text, file_id = _extract_content(message)
    if content_type is None:
        await message.reply_text(
            "این نوع پیام پشتیبانی نمی‌شود. فقط متن، عکس یا ویدیو بفرستید."
        )
        return

    owner_id = update.effective_user.id
    chats = await db.get_owner_chats(owner_id)
    if not chats:
        await message.reply_text(
            "شما هنوز مالک هیچ کانال/گروهی نیستید. اول ربات را در کانال/گروه خود ادمین کنید."
        )
        return

    if len(chats) == 1:
        chat_id = chats[0]["chat_id"]
        post_id = await db.add_post(chat_id, owner_id, content_type, text, file_id)
        await message.reply_text(f"✅ پست #{post_id} به صفِ «{chats[0]['title']}» اضافه شد.")
        return

    # چند کانال داریم -> محتوا را موقت نگه داریم و بپرسیم برای کدام چت است
    pending_id = str(message.message_id)
    context.user_data.setdefault("pending_posts", {})[pending_id] = {
        "content_type": content_type,
        "text": text,
        "file_id": file_id,
    }
    kb = [
        [InlineKeyboardButton(c["title"], callback_data=f"postto:{pending_id}:{c['chat_id']}")]
        for c in chats
    ]
    await message.reply_text(
        "این پست برای کدام کانال/گروه است؟", reply_markup=InlineKeyboardMarkup(kb)
    )


async def choose_target_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, pending_id, chat_id = query.data.split(":")
    chat_id = int(chat_id)
    pending = context.user_data.get("pending_posts", {}).pop(pending_id, None)
    if pending is None:
        await query.edit_message_text("این درخواست منقضی شده، دوباره پست را بفرستید.")
        return
    owner_id = update.effective_user.id
    post_id = await db.add_post(
        chat_id, owner_id, pending["content_type"], pending["text"], pending["file_id"]
    )
    chat = await db.get_chat(chat_id)
    title = chat["title"] if chat else str(chat_id)
    await query.edit_message_text(f"✅ پست #{post_id} به صفِ «{title}» اضافه شد.")


def _fmt_time(iso_value):
    if not iso_value:
        return "در انتظار زمان‌بندی"
    try:
        d = dt.datetime.fromisoformat(iso_value).astimezone(TIMEZONE)
        return d.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso_value


def _preview(post):
    if post["content_type"] == "text":
        t = (post["text"] or "").strip().replace("\n", " ")
        return t[:30] + ("…" if len(t) > 30 else "")
    label = "🖼 عکس" if post["content_type"] == "photo" else "🎬 ویدیو"
    cap = (post["text"] or "").strip().replace("\n", " ")
    if cap:
        cap = " - " + cap[:20] + ("…" if len(cap) > 20 else "")
    return label + cap


async def queue_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    chats = await db.get_owner_chats(update.effective_user.id)
    if not chats:
        await update.message.reply_text("هیچ کانال/گروهی برای شما ثبت نشده.")
        return
    kb = [[InlineKeyboardButton(c["title"], callback_data=f"q_chat:{c['chat_id']}")] for c in chats]
    await update.message.reply_text("صف کدام کانال/گروه را می‌خواهید ببینید؟", reply_markup=InlineKeyboardMarkup(kb))


async def queue_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = int(query.data.split(":", 1)[1])
    posts = await db.get_queue(chat_id)
    if not posts:
        await query.edit_message_text("صف خالی است.")
        return
    lines = []
    kb_rows = []
    for p in posts:
        lines.append(f"#{p['id']} | {_fmt_time(p['scheduled_time'])} | {_preview(p)}")
        kb_rows.append([InlineKeyboardButton(f"❌ لغو #{p['id']}", callback_data=f"cancel:{p['id']}:{chat_id}")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb_rows))


async def cancel_post_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, post_id, chat_id = query.data.split(":")
    await db.cancel_post(int(post_id))
    posts = await db.get_queue(int(chat_id))
    if not posts:
        await query.edit_message_text("پست لغو شد. صف الان خالی است.")
        return
    lines = []
    kb_rows = []
    for p in posts:
        lines.append(f"#{p['id']} | {_fmt_time(p['scheduled_time'])} | {_preview(p)}")
        kb_rows.append([InlineKeyboardButton(f"❌ لغو #{p['id']}", callback_data=f"cancel:{p['id']}:{chat_id}")])
    await query.edit_message_text("پست لغو شد.\n\n" + "\n".join(lines), reply_markup=InlineKeyboardMarkup(kb_rows))
