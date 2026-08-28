from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import db

CHOOSE_CHAT, ENTER_ID = range(2)

CANCEL_HINT = "\n\n(هر لحظه می‌توانید با /cancel این عملیات را لغو کنید.)"


def _chat_kb(chats, prefix):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(c["title"], callback_data=f"{prefix}:{c['chat_id']}")] for c in chats]
    )


async def setid_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return ConversationHandler.END
    chats = await db.get_owner_chats(update.effective_user.id)
    if not chats:
        await update.message.reply_text(
            "هیچ کانال/گروهی برای شما ثبت نشده. اول ربات را در کانال خود ادمین کنید."
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "آیدی/امضا برای کدام کانال یا گروه تنظیم شود؟", reply_markup=_chat_kb(chats, "si_chat")
    )
    return CHOOSE_CHAT


async def setid_choose_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = int(query.data.split(":", 1)[1])
    context.user_data["si_chat_id"] = chat_id

    chat = await db.get_chat(chat_id)
    current = chat.get("signature") if chat else None
    hint = f"\n\nآیدی فعلیِ این چت:\n{current}" if current else "\n\nاین چت الان آیدی‌ای تنظیم ندارد."

    await query.edit_message_text(
        "آیدی/امضایی که می‌خواهید ته همه‌ی پست‌های این چت اضافه شود را بفرستید "
        "(مثلاً @your_channel).\n"
        "این ربات خودش هر آیدیِ قبلیِ ته پست را پاک می‌کند و آیدیِ جدید را جای آن می‌گذارد.\n"
        "برای حذف کامل آیدی، یک خط تیره (-) بفرستید."
        + hint
        + CANCEL_HINT
    )
    return ENTER_ID


async def setid_enter_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = context.user_data.pop("si_chat_id", None)
    if chat_id is None:
        await update.message.reply_text("خطا رخ داد، دوباره با /setid امتحان کنید.")
        return ConversationHandler.END

    if text == "-":
        await db.set_signature(chat_id, None)
        await update.message.reply_text("✅ آیدیِ این چت حذف شد؛ از این پس چیزی به ته پست‌ها اضافه نمی‌شود.")
        return ConversationHandler.END

    await db.set_signature(chat_id, text)
    await update.message.reply_text(
        f"✅ از این پس این آیدی ته پست‌های این چت اضافه می‌شود:\n{text}\n\n"
        "(برای پست‌هایی که از قبل در صف هستند اعمال نمی‌شود، فقط روی پست‌های جدید اثر دارد.)"
    )
    return ConversationHandler.END


async def setid_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اگر کاربر مدتی جواب ندهد، فرم به‌طور خودکار لغو می‌شود تا ربات گیر نکند."""
    context.user_data.pop("si_chat_id", None)
    chat_id = update.effective_chat.id if update and update.effective_chat else None
    if chat_id:
        try:
            await context.bot.send_message(
                chat_id,
                "⏱ زمانِ تنظیم آیدی (۵ دقیقه) بدون پاسخ تمام شد و لغو گردید.\n"
                "برای شروع دوباره /setid را بزنید.",
            )
        except Exception:
            pass
    return ConversationHandler.END
