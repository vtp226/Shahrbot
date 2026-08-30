import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import db

CHOOSE_CHAT, ENTER_START, ENTER_END, ENTER_INTERVAL = range(4)
EW_FIELD, EW_VALUE = range(4, 6)

CANCEL_HINT = "\n\n(هر لحظه می‌توانید با /cancel این عملیات را لغو کنید.)"

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
TIME_RE_24 = re.compile(r"^(24:00|[01]?\d:[0-5]\d|2[0-3]:[0-5]\d)$")


def _chat_kb(chats, prefix):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(c["title"], callback_data=f"{prefix}:{c['chat_id']}")] for c in chats]
    )


def _windows_view(chat_title: str, chat_id: int, wins: list):
    """متن + دکمه‌های شیشه‌ای برای نمایش بازه‌های یک چت، همراه دکمه ویرایش/حذف هر بازه."""
    kb_rows = []
    if not wins:
        lines = [f"🗂 بازه‌های «{chat_title}»", "", "هنوز بازه‌ای برای این کانال/گروه تعریف نشده."]
    else:
        lines = [f"🗂 بازه‌های «{chat_title}»:", ""]
        for w in wins:
            lines.append(f"• {w['start_time']} تا {w['end_time']} — هر {w['interval_hours']} ساعت")
            kb_rows.append(
                [
                    InlineKeyboardButton(
                        f"✏️ ویرایش {w['start_time']}-{w['end_time']}", callback_data=f"we:{w['id']}:{chat_id}"
                    ),
                    InlineKeyboardButton("🗑 حذف", callback_data=f"wd:{w['id']}:{chat_id}"),
                ]
            )
    kb_rows.append([InlineKeyboardButton("➕ افزودن بازه به این کانال", callback_data=f"aw_direct:{chat_id}")])
    return "\n".join(lines), InlineKeyboardMarkup(kb_rows)


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

    if len(chats) == 1:
        chat = chats[0]
        context.user_data["aw_chat_id"] = chat["chat_id"]
        await update.message.reply_text(
            f"در حال افزودن بازه برای «{chat['title']}».\n\n"
            "ساعت شروع بازه را به شکل HH:MM وارد کنید (مثلاً 12:00):" + CANCEL_HINT
        )
        return ENTER_START

    await update.message.reply_text(
        "بازه زمانی برای کدام کانال/گروه است؟", reply_markup=_chat_kb(chats, "aw_chat")
    )
    return CHOOSE_CHAT


async def addwindow_direct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ورود مستقیم به فرم افزودن بازه برای یک چتِ از قبل مشخص (مثلاً از داشبورد کانال)."""
    query = update.callback_query
    await query.answer()
    chat_id = int(query.data.split(":", 1)[1])
    chat = await db.get_chat(chat_id)
    title = chat["title"] if chat else str(chat_id)
    context.user_data["aw_chat_id"] = chat_id
    await query.edit_message_text(
        f"در حال افزودن بازه برای «{title}».\n\n"
        "ساعت شروع بازه را به شکل HH:MM وارد کنید (مثلاً 12:00):" + CANCEL_HINT
    )
    return ENTER_START


async def addwindow_choose_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = int(query.data.split(":", 1)[1])
    context.user_data["aw_chat_id"] = chat_id
    await query.edit_message_text(
        "ساعت شروع بازه را به شکل HH:MM وارد کنید (مثلاً 12:00):" + CANCEL_HINT
    )
    return ENTER_START


async def addwindow_enter_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not TIME_RE.match(text):
        await update.message.reply_text("فرمت درست نیست. دوباره مثل 12:00 وارد کنید:" + CANCEL_HINT)
        return ENTER_START
    context.user_data["aw_start"] = text
    await update.message.reply_text(
        "ساعت پایان بازه را وارد کنید (برای نیمه‌شب می‌توانید 24:00 بنویسید):" + CANCEL_HINT
    )
    return ENTER_END


async def addwindow_enter_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not TIME_RE_24.match(text):
        await update.message.reply_text("فرمت درست نیست. مثل 24:00 یا 18:30 وارد کنید:" + CANCEL_HINT)
        return ENTER_END
    context.user_data["aw_end"] = text
    await update.message.reply_text(
        "هر چند ساعت یک‌بار پست منتشر شود؟ (عدد، مثلاً 3 یا 1.5):" + CANCEL_HINT
    )
    return ENTER_INTERVAL


async def addwindow_enter_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", ".")
    try:
        interval = float(text)
        if interval <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "لطفاً یک عدد معتبر بزرگ‌تر از صفر وارد کنید:" + CANCEL_HINT
        )
        return ENTER_INTERVAL

    chat_id = context.user_data.pop("aw_chat_id")
    start = context.user_data.pop("aw_start")
    end = context.user_data.pop("aw_end")
    await db.add_window(chat_id, start, end, interval)

    chat = await db.get_chat(chat_id)
    title = chat["title"] if chat else str(chat_id)
    wins = await db.get_windows(chat_id)
    text, kb = _windows_view(title, chat_id, wins)
    await update.message.reply_text(
        f"✅ بازه زمانی {start} تا {end} هر {interval} ساعت برای «{title}» اضافه شد.\n\n" + text,
        reply_markup=kb,
    )
    return ConversationHandler.END


async def addwindow_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Runs automatically if the user doesn't respond for a while, so the bot
    never gets permanently stuck waiting for a time input."""
    context.user_data.pop("aw_chat_id", None)
    context.user_data.pop("aw_start", None)
    context.user_data.pop("aw_end", None)
    chat_id = update.effective_chat.id if update and update.effective_chat else None
    if chat_id:
        try:
            await context.bot.send_message(
                chat_id,
                "⏱ زمانِ تنظیم بازه (۵ دقیقه) بدون پاسخ تمام شد و لغو گردید.\n"
                "برای شروع دوباره /addwindow را بزنید.",
            )
        except Exception:
            pass
    return ConversationHandler.END


# ---------------- list / delete windows ----------------

async def windows_list_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    chats = await db.get_owner_chats(update.effective_user.id)
    if not chats:
        await update.message.reply_text("هیچ کانال/گروهی برای شما ثبت نشده.")
        return

    if len(chats) == 1:
        chat = chats[0]
        wins = await db.get_windows(chat["chat_id"])
        text, kb = _windows_view(chat["title"], chat["chat_id"], wins)
        await update.message.reply_text(text, reply_markup=kb)
        return

    await update.message.reply_text(
        "بازه‌های کدام کانال/گروه را می‌خواهید ببینید؟", reply_markup=_chat_kb(chats, "wl_chat")
    )


async def windows_list_choose_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = int(query.data.split(":", 1)[1])
    chat = await db.get_chat(chat_id)
    title = chat["title"] if chat else str(chat_id)
    wins = await db.get_windows(chat_id)
    text, kb = _windows_view(title, chat_id, wins)
    await query.edit_message_text(text, reply_markup=kb)


async def menu_button_escape(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """If the user taps another menu button while mid-way through /addwindow,
    cleanly cancel the form instead of swallowing the tap as a time value."""
    from handlers import common, posts  # local import avoids circular import at module load

    context.user_data.pop("aw_chat_id", None)
    context.user_data.pop("aw_start", None)
    context.user_data.pop("aw_end", None)
    context.user_data.pop("ew_window_id", None)
    context.user_data.pop("ew_chat_id", None)
    context.user_data.pop("ew_field", None)

    text = update.message.text
    if text == common.BTN_WINDOWS:
        await windows_list_start(update, context)
    elif text == common.BTN_QUEUE:
        await posts.queue_start(update, context)
    elif text == common.BTN_MYCHATS:
        await common.my_chats(update, context)
    elif text == common.BTN_HELP:
        await common.help_cmd(update, context)
    elif text == common.BTN_ADDWINDOW:
        await update.message.reply_text(
            "فرم قبلی لغو شد. دوباره روی «➕ افزودن بازه» بزنید تا از اول شروع کنیم."
        )
    return ConversationHandler.END


async def windows_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, window_id, chat_id = query.data.split(":")
    chat_id = int(chat_id)
    await db.delete_window(int(window_id))
    chat = await db.get_chat(chat_id)
    title = chat["title"] if chat else str(chat_id)
    wins = await db.get_windows(chat_id)
    text, kb = _windows_view(title, chat_id, wins)
    await query.edit_message_text("✅ بازه حذف شد.\n\n" + text, reply_markup=kb)


# ---------------- edit an existing window ----------------

async def edit_window_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, window_id, chat_id = query.data.split(":")
    window = await db.get_window(int(window_id))
    if not window:
        await query.edit_message_text("این بازه دیگر وجود ندارد (شاید قبلاً حذف شده).")
        return ConversationHandler.END

    context.user_data["ew_window_id"] = int(window_id)
    context.user_data["ew_chat_id"] = int(chat_id)

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"⏰ ساعت شروع ({window['start_time']})", callback_data="ewf:start")],
            [InlineKeyboardButton(f"⏰ ساعت پایان ({window['end_time']})", callback_data="ewf:end")],
            [InlineKeyboardButton(f"🔁 فاصله ({window['interval_hours']} ساعت)", callback_data="ewf:interval")],
            [InlineKeyboardButton("↩️ انصراف", callback_data="ewf:cancel")],
        ]
    )
    await query.edit_message_text(
        "کدام مقدار این بازه را می‌خواهید ویرایش کنید؟\n\n"
        f"فعلی: {window['start_time']} تا {window['end_time']} — هر {window['interval_hours']} ساعت",
        reply_markup=kb,
    )
    return EW_FIELD


async def edit_window_choose_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field = query.data.split(":", 1)[1]
    chat_id = context.user_data.get("ew_chat_id")

    if field == "cancel":
        context.user_data.pop("ew_window_id", None)
        context.user_data.pop("ew_chat_id", None)
        chat = await db.get_chat(chat_id) if chat_id else None
        title = chat["title"] if chat else str(chat_id)
        wins = await db.get_windows(chat_id) if chat_id else []
        text, kb = _windows_view(title, chat_id, wins)
        await query.edit_message_text(text, reply_markup=kb)
        return ConversationHandler.END

    context.user_data["ew_field"] = field
    prompts = {
        "start": "ساعت شروع جدید را به شکل HH:MM وارد کنید (مثلاً 12:00):",
        "end": "ساعت پایان جدید را وارد کنید (برای نیمه‌شب می‌توانید 24:00 بنویسید):",
        "interval": "فاصله جدید بین پست‌ها را به ساعت وارد کنید (مثلاً 3 یا 1.5):",
    }
    await query.edit_message_text(prompts[field] + CANCEL_HINT)
    return EW_VALUE


async def edit_window_enter_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = context.user_data.get("ew_field")
    window_id = context.user_data.get("ew_window_id")
    chat_id = context.user_data.get("ew_chat_id")
    text = update.message.text.strip()

    if field == "start":
        if not TIME_RE.match(text):
            await update.message.reply_text("فرمت درست نیست. دوباره مثل 12:00 وارد کنید:" + CANCEL_HINT)
            return EW_VALUE
        await db.update_window(window_id, start_time=text)
    elif field == "end":
        if not TIME_RE_24.match(text):
            await update.message.reply_text("فرمت درست نیست. مثل 24:00 یا 18:30 وارد کنید:" + CANCEL_HINT)
            return EW_VALUE
        await db.update_window(window_id, end_time=text)
    elif field == "interval":
        norm = text.replace(",", ".")
        try:
            interval = float(norm)
            if interval <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("لطفاً یک عدد معتبر بزرگ‌تر از صفر وارد کنید:" + CANCEL_HINT)
            return EW_VALUE
        await db.update_window(window_id, interval_hours=interval)
    else:
        await update.message.reply_text("خطایی رخ داد، دوباره با «🗓 بازه‌های من» امتحان کنید.")
        return ConversationHandler.END

    context.user_data.pop("ew_window_id", None)
    context.user_data.pop("ew_chat_id", None)
    context.user_data.pop("ew_field", None)

    chat = await db.get_chat(chat_id)
    title = chat["title"] if chat else str(chat_id)
    wins = await db.get_windows(chat_id)
    view_text, kb = _windows_view(title, chat_id, wins)
    await update.message.reply_text("✅ بازه ویرایش شد.\n\n" + view_text, reply_markup=kb)
    return ConversationHandler.END


async def edit_window_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("ew_window_id", None)
    context.user_data.pop("ew_chat_id", None)
    context.user_data.pop("ew_field", None)
    chat_id = update.effective_chat.id if update and update.effective_chat else None
    if chat_id:
        try:
            await context.bot.send_message(
                chat_id,
                "⏱ زمانِ ویرایش بازه (۵ دقیقه) بدون پاسخ تمام شد و لغو گردید.\n"
                "برای شروع دوباره از «🗓 بازه‌های من» اقدام کنید.",
            )
        except Exception:
            pass
    return ConversationHandler.END
