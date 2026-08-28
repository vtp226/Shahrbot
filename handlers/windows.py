import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import db

CHOOSE_CHAT, ENTER_START, ENTER_END, ENTER_INTERVAL = range(4)

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
TIME_RE_24 = re.compile(r"^(24:00|[01]?\d:[0-5]\d|2[0-3]:[0-5]\d)$")


def _chat_kb(chats, prefix):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(c["title"], callback_data=f"{prefix}:{c['chat_id']}")] for c in chats]
    )


# ---------------- add window ----------------

async def addwindow_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return ConversationHandler.END
    chats = await db.get_owner_chats(update.effective_user.id)
    if not chats:
        await update.message.reply_text(
            "هیچ کانال/گروهی برای شما ثبت نشده. اول ربات را در کانال خود ادمین کنید."
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "بازه زمانی برای کدام کانال/گروه است؟", reply_markup=_chat_kb(chats, "aw_chat")
    )
    return CHOOSE_CHAT


async def addwindow_choose_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = int(query.data.split(":", 1)[1])
    context.user_data["aw_chat_id"] = chat_id
    await query.edit_message_text(
        "ساعت شروع بازه را به شکل HH:MM وارد کنید (مثلاً 12:00):"
    )
    return ENTER_START


async def addwindow_enter_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not TIME_RE.match(text):
        await update.message.reply_text("فرمت درست نیست. دوباره مثل 12:00 وارد کنید:")
        return ENTER_START
    context.user_data["aw_start"] = text
    await update.message.reply_text(
        "ساعت پایان بازه را وارد کنید (برای نیمه‌شب می‌توانید 24:00 بنویسید):"
    )
    return ENTER_END


async def addwindow_enter_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not TIME_RE_24.match(text):
        await update.message.reply_text("فرمت درست نیست. مثل 24:00 یا 18:30 وارد کنید:")
        return ENTER_END
    context.user_data["aw_end"] = text
    await update.message.reply_text("هر چند ساعت یک‌بار پست منتشر شود؟ (عدد، مثلاً 3 یا 1.5):")
    return ENTER_INTERVAL


async def addwindow_enter_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", ".")
    try:
        interval = float(text)
        if interval <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("لطفاً یک عدد معتبر بزرگ‌تر از صفر وارد کنید:")
        return ENTER_INTERVAL

    chat_id = context.user_data.pop("aw_chat_id")
    start = context.user_data.pop("aw_start")
    end = context.user_data.pop("aw_end")
    await db.add_window(chat_id, start, end, interval)
    await update.message.reply_text(
        f"✅ بازه زمانی {start} تا {end} هر {interval} ساعت اضافه شد.\n"
        "برای افزودن بازه دوم دوباره /addwindow را بزنید، یا /windows را برای مشاهده لیست ببینید."
    )
    return ConversationHandler.END


# ---------------- list / delete windows ----------------

async def windows_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    chats = await db.get_owner_chats(update.effective_user.id)
    if not chats:
        await update.message.reply_text("هیچ کانال/گروهی برای شما ثبت نشده.")
        return
    await update.message.reply_text(
        "بازه‌های کدام کانال/گروه را می‌خواهید ببینید؟", reply_markup=_chat_kb(chats, "wl_chat")
    )


async def windows_list_choose_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = int(query.data.split(":", 1)[1])
    wins = await db.get_windows(chat_id)
    if not wins:
        await query.edit_message_text("برای این چت هنوز بازه‌ای تعریف نشده. از /addwindow استفاده کنید.")
        return
    lines = []
    kb_rows = []
    for w in wins:
        lines.append(f"• {w['start_time']} تا {w['end_time']} — هر {w['interval_hours']} ساعت")
        kb_rows.append(
            [InlineKeyboardButton(f"🗑 حذف {w['start_time']}-{w['end_time']}", callback_data=f"wd:{w['id']}:{chat_id}")]
        )
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb_rows))


async def windows_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, window_id, chat_id = query.data.split(":")
    await db.delete_window(int(window_id))
    wins = await db.get_windows(int(chat_id))
    if not wins:
        await query.edit_message_text("همه بازه‌ها حذف شدند.")
        return
    lines = []
    kb_rows = []
    for w in wins:
        lines.append(f"• {w['start_time']} تا {w['end_time']} — هر {w['interval_hours']} ساعت")
        kb_rows.append(
            [InlineKeyboardButton(f"🗑 حذف {w['start_time']}-{w['end_time']}", callback_data=f"wd:{w['id']}:{chat_id}")]
        )
    await query.edit_message_text("بازه حذف شد.\n\n" + "\n".join(lines), reply_markup=InlineKeyboardMarkup(kb_rows))
