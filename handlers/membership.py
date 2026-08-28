import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

import db

logger = logging.getLogger(__name__)

ADMIN_LIKE = {"administrator", "creator"}


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmu = update.my_chat_member
    chat = cmu.chat
    new_status = cmu.new_chat_member.status
    old_status = cmu.old_chat_member.status
    performer = cmu.from_user

    if new_status in ADMIN_LIKE and old_status not in ADMIN_LIKE:
        title = chat.title or chat.username or str(chat.id)
        await db.upsert_chat(chat.id, title, chat.type, performer.id)
        try:
            await context.bot.send_message(
                chat_id=performer.id,
                text=(
                    f"✅ ربات با موفقیت در «{title}» ادمین شد.\n\n"
                    "حالا با /addwindow بازه‌های زمانی ارسال پست را تعریف کنید، "
                    "سپس پست‌های خود را همینجا برای من بفرستید تا در صف قرار بگیرند."
                ),
            )
        except TelegramError:
            # کاربر هنوز ربات را در پیوی استارت نکرده؛ وقتی /start بزند لیست کانال‌هایش را می‌بیند.
            logger.info("Could not DM owner %s yet (chat %s)", performer.id, chat.id)

    elif new_status not in ADMIN_LIKE and old_status in ADMIN_LIKE:
        await db.deactivate_chat(chat.id)
