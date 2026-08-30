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
    "/cancel — لغو عملیات جاری\n\n"
    "نکته: با زدن روی هر کانال/گروه در «📢 کانال‌های من» یک داشبورد مخصوص همان چت باز می‌شود "
    "که در آن می‌توانید بازه‌های همان کانال را جدا از بقیه ببینید/ویرایش/حذف کنید، بازه تازه اضافه کنید، "
    "و آن چت را به‌عنوان مقصد پیش‌فرض ارسال پست تنظیم کنید تا پست‌های بعدی بدون سؤالِ «برای کدام کانال؟» "
    "مستقیم همان‌جا در صف قرار بگیرند.\n"
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
    kb = [[InlineKeyboardButton(c["title"], callback_data=f"chat_dash:{c['chat_id']}")] for c in chats]
    await update.message.reply_text(
        "کانال‌ها/گروه‌های تحت مدیریت شما — برای مدیریت هرکدام روی آن بزنید:",
        reply_markup=InlineKeyboardMarkup(kb),
    )


def _dashboard_kb(chat_id: int, is_default: bool):
    rows = [
        [InlineKeyboardButton("🗓 بازه‌های این کانال", callback_data=f"wl_chat:{chat_id}")],
        [InlineKeyboardButton("➕ افزودن بازه به این کانال", callback_data=f"aw_direct:{chat_id}")],
        [InlineKeyboardButton("🗒 صف پست‌های این کانال", callback_data=f"q_chat:{chat_id}")],
    ]
    if is_default:
        rows.append([InlineKeyboardButton("❌ برداشتن مقصد پیش‌فرض", callback_data=f"cleardef:{chat_id}")])
    else:
        rows.append([InlineKeyboardButton("📌 تنظیم به‌عنوان مقصد پیش‌فرض ارسال", callback_data=f"setdef:{chat_id}")])
    return InlineKeyboardMarkup(rows)


async def _render_dashboard(query, owner_id: int, chat_id: int):
    chat = await db.get_chat(chat_id)
    if not chat:
        await query.edit_message_text("این کانال/گروه دیگر پیدا نشد.")
        return

    default_chat_id = await db.get_default_chat(owner_id)
    is_default = default_chat_id == chat_id

    lines = [f"📢 «{chat['title']}»"]
    if chat.get("signature"):
        lines.append(f"آیدی ته پست: {chat['signature']}")
    if is_default:
        lines.append(
            "\n✅ این چت الان مقصدِ پیش‌فرضِ ارسال پست شماست: هرچه همین‌جا برای ربات بفرستید، "
            "بدون سؤال «برای کدام کانال؟» مستقیم در صفِ همین چت قرار می‌گیرد."
        )

    await query.edit_message_text("\n".join(lines), reply_markup=_dashboard_kb(chat_id, is_default))


async def chat_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = int(query.data.split(":", 1)[1])
    await _render_dashboard(query, update.effective_user.id, chat_id)


async def set_default_chat_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("این کانال به‌عنوان مقصد پیش‌فرض تنظیم شد ✅")
    chat_id = int(query.data.split(":", 1)[1])
    await db.set_default_chat(update.effective_user.id, chat_id)
    await _render_dashboard(query, update.effective_user.id, chat_id)


async def clear_default_chat_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("مقصد پیش‌فرض برداشته شد")
    chat_id = int(query.data.split(":", 1)[1])
    await db.set_default_chat(update.effective_user.id, None)
    await _render_dashboard(query, update.effective_user.id, chat_id)


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.")
    from telegram.ext import ConversationHandler

    return ConversationHandler.END


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
