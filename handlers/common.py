from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

import db

BTN_ADDWINDOW = "➕ افزودن بازه"
BTN_WINDOWS = "🗓 بازه‌های من"
BTN_QUEUE = "🗒 صف پست‌ها"
BTN_MYCHATS = "📢 کانال‌های من"
BTN_HELP = "❓ راهنما"

MAIN_MENU = ReplyKeyboardMarkup(
    [
        [BTN_ADDWINDOW, BTN_WINDOWS],
        [BTN_QUEUE, BTN_MYCHATS],
        [BTN_HELP],
    ],
    resize_keyboard=True,
)

HELP_TEXT = (
    "🤖 *راهنمای ربات زمان‌بند پست*\n\n"
    "۱. این ربات را در پیوی استارت کنید (همین الان انجام دادید ✅).\n"
    "۲. ربات را در کانال یا گروه خود *ادمین* کنید.\n"
    "۳. با دستور /addwindow برای آن کانال بازه‌های زمانی ارسال پست را تعریف کنید "
    "(مثلاً از ۱۲:۰۰ تا ۲۴:۰۰ هر ۳ ساعت یک‌بار).\n"
    "۴. حالا کافیست پست‌های خود (متن، عکس یا ویدیو) را همینجا برای ربات بفرستید یا فوروارد کنید؛ "
    "ربات آن‌ها را در صف قرار می‌دهد و خودش سر وقتِ تعریف‌شده در کانال منتشر می‌کند.\n\n"
    "دستورات مفید:\n"
    "/mychats — لیست کانال‌ها/گروه‌های شما\n"
    "/addwindow — افزودن بازه زمانی جدید\n"
    "/windows — مشاهده/حذف بازه‌های زمانی\n"
    "/queue — مشاهده صف پست‌ها\n"
    "/setid — تنظیم آیدی/امضایی که خودکار ته پست‌ها اضافه شود\n"
    "/cancel — لغو عملیات جاری\n"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    user = update.effective_user
    await update.message.reply_text(
        f"سلام {user.first_name}! 👋\n\n" + HELP_TEXT,
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )
    chats = await db.get_owner_chats(user.id)
    if chats:
        lines = "\n".join(f"• {c['title']}" for c in chats)
        await update.message.reply_text(
            f"شما مالک این کانال‌ها/گروه‌ها هستید:\n{lines}\n\n"
            "برای تعریف بازه زمانی از دکمه «➕ افزودن بازه» یا /addwindow استفاده کنید."
        )


async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    await update.message.reply_text("منو:", reply_markup=MAIN_MENU)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown", reply_markup=MAIN_MENU)


async def my_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    chats = await db.get_owner_chats(update.effective_user.id)
    if not chats:
        await update.message.reply_text(
            "هنوز هیچ کانال/گروهی ثبت نشده.\n"
            "ربات را در کانال یا گروه خود ادمین کنید تا اینجا نمایش داده شود.\n"
            "(دقت کنید که همان کسی که ربات را ادمین می‌کند باید قبلش این چت خصوصی با ربات را استارت کرده باشد.)"
        )
        return
    kb = [[InlineKeyboardButton(c["title"], callback_data=f"noop:{c['chat_id']}")] for c in chats]
    await update.message.reply_text(
        "کانال‌ها/گروه‌های تحت مدیریت شما:", reply_markup=InlineKeyboardMarkup(kb)
    )


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.")
    from telegram.ext import ConversationHandler

    return ConversationHandler.END


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
