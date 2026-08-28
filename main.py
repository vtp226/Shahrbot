import os
import logging

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ChatMemberHandler,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

import db
import scheduling
from handlers import common, membership, windows, posts, signature

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
TICK_SECONDS = int(os.environ.get("TICK_SECONDS", "60"))


async def _post_init(app: Application):
    await db.init_db()
    logger.info("Database ready.")


def build_app() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("متغیر محیطی BOT_TOKEN تنظیم نشده است.")

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(_post_init).build()

    # ---- membership ----
    app.add_handler(ChatMemberHandler(membership.on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # ---- basic commands ----
    app.add_handler(CommandHandler("start", common.start))
    app.add_handler(CommandHandler("help", common.help_cmd))
    app.add_handler(CommandHandler("menu", common.menu_cmd))
    app.add_handler(CommandHandler("mychats", common.my_chats))
    app.add_handler(CallbackQueryHandler(common.noop_callback, pattern=r"^noop:"))

    # ---- add window conversation ----
    menu_button_filter = filters.Text(
        [common.BTN_ADDWINDOW, common.BTN_WINDOWS, common.BTN_QUEUE, common.BTN_MYCHATS, common.BTN_HELP]
    )
    addwindow_conv = ConversationHandler(
        entry_points=[
            CommandHandler("addwindow", windows.addwindow_start),
            MessageHandler(filters.Text([common.BTN_ADDWINDOW]), windows.addwindow_start),
        ],
        states={
            windows.CHOOSE_CHAT: [CallbackQueryHandler(windows.addwindow_choose_chat, pattern=r"^aw_chat:")],
            windows.ENTER_START: [
                MessageHandler(menu_button_filter, windows.menu_button_escape),
                MessageHandler(filters.TEXT & ~filters.COMMAND, windows.addwindow_enter_start),
            ],
            windows.ENTER_END: [
                MessageHandler(menu_button_filter, windows.menu_button_escape),
                MessageHandler(filters.TEXT & ~filters.COMMAND, windows.addwindow_enter_end),
            ],
            windows.ENTER_INTERVAL: [
                MessageHandler(menu_button_filter, windows.menu_button_escape),
                MessageHandler(filters.TEXT & ~filters.COMMAND, windows.addwindow_enter_interval),
            ],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, windows.addwindow_timeout)],
        },
        fallbacks=[CommandHandler("cancel", common.cancel_cmd)],
        conversation_timeout=300,  # 5 دقیقه؛ جلوی گیر کردن دائمی را می‌گیرد
    )
    app.add_handler(addwindow_conv)

    # ---- set/remove per-chat signature (ID appended to the end of posts) ----
    setid_conv = ConversationHandler(
        entry_points=[CommandHandler("setid", signature.setid_start)],
        states={
            signature.CHOOSE_CHAT: [
                CallbackQueryHandler(signature.setid_choose_chat, pattern=r"^si_chat:")
            ],
            signature.ENTER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, signature.setid_enter_id),
            ],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, signature.setid_timeout)],
        },
        fallbacks=[CommandHandler("cancel", common.cancel_cmd)],
        conversation_timeout=300,
    )
    app.add_handler(setid_conv)

    # ---- windows list / delete ----
    app.add_handler(CommandHandler("windows", windows.windows_list_start))
    app.add_handler(MessageHandler(filters.Text([common.BTN_WINDOWS]), windows.windows_list_start))
    app.add_handler(CallbackQueryHandler(windows.windows_list_choose_chat, pattern=r"^wl_chat:"))
    app.add_handler(CallbackQueryHandler(windows.windows_delete, pattern=r"^wd:"))

    # ---- queue ----
    app.add_handler(CommandHandler("queue", posts.queue_start))
    app.add_handler(MessageHandler(filters.Text([common.BTN_QUEUE]), posts.queue_start))
    app.add_handler(CallbackQueryHandler(posts.queue_show, pattern=r"^q_chat:"))
    app.add_handler(CallbackQueryHandler(posts.cancel_post_cb, pattern=r"^cancel:"))
    app.add_handler(CallbackQueryHandler(posts.choose_target_chat, pattern=r"^postto:"))

    # ---- remaining menu buttons ----
    app.add_handler(MessageHandler(filters.Text([common.BTN_MYCHATS]), common.my_chats))
    app.add_handler(MessageHandler(filters.Text([common.BTN_HELP]), common.help_cmd))

    # ---- incoming content (must be added after commands, catches the rest) ----
    supported_content = (
        filters.TEXT
        | filters.PHOTO
        | filters.VIDEO
        | filters.ANIMATION
        | filters.Sticker.ALL
        | filters.VOICE
        | filters.AUDIO
        | filters.Document.ALL
        | filters.VIDEO_NOTE
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & supported_content & ~filters.COMMAND,
            posts.incoming_message,
        )
    )

    # ---- scheduler tick ----
    app.job_queue.run_repeating(scheduling.tick, interval=TICK_SECONDS, first=10)

    return app


def main():
    app = build_app()
    logger.info("Bot starting (polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
