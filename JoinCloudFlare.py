# JoinCloudFlare.py - Fix v4.3 (Added Fail-Safe Handler)

import os
import logging
from typing import Final
from telegram import Update, error, InlineKeyboardMarkup, InlineKeyboardButton 
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

# --- 1. تنظیمات و متغیرهای محیطی ---

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# اطمینان از تعریف صحیح متغیرهای محیطی
try:
    BOT_TOKEN: Final[str] = os.environ.get("BOT_TOKEN")
    API_SECRET: Final[str] = os.environ.get("API_SECRET")
    REQUIRED_CHANNEL: Final[str] = os.environ.get("REQUIRED_CHANNEL")
    ADMIN_IDS_STR: Final[str] = os.environ.get("ADMIN_IDS")
    
    # فیکس قوی‌تر ADMIN_IDS: مطمئن می‌شویم که رشته به عدد تبدیل می‌شود.
    # حتی اگر متغیر به درستی خوانده نشود، ADMIN_IDS خالی خواهد بود و خطایی ایجاد نمی‌کند.
    admin_ids_temp = []
    if ADMIN_IDS_STR:
        try:
            admin_ids_temp = [int(i.strip()) for i in ADMIN_IDS_STR.split(',') if i.strip().isdigit()]
        except Exception:
            pass # در صورت خطای تبدیل، لیست خالی باقی می‌ماند
            
    ADMIN_IDS: Final[list[int]] = admin_ids_temp

    if not all([BOT_TOKEN, API_SECRET, REQUIRED_CHANNEL]):
        raise ValueError("One or more essential environment variables are missing.")
except Exception as e:
    logger.error(f"FATAL ERROR: Environment variables failed to load or parse: {e}")
    # اگر در این مرحله خطا رخ دهد، برنامه کرش می‌کند و پاسخ نمی‌دهد.

# --- 2. توابع اصلی ربات ---

async def is_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['creator', 'administrator', 'member']
    except error.BadRequest:
        return False
    except Exception:
        # در صورت بروز خطا در بررسی عضویت (مثلاً ربات ادمین کانال نباشد)
        return False

# فرمان /start با مکانیزم Fail-Safe
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Fail-Safe: اگر در هر مرحله‌ای در این تابع خطا رخ دهد، حداقل این پیام را ارسال کند.
    try:
        if update.effective_user is None:
            return

        user_id = update.effective_user.id

        if user_id in ADMIN_IDS:
            await update.message.reply_text(
                f"🚀 ادمین عزیز، خوش آمدید. ربات آماده کار است. (ID: {user_id})"
            )
            return

        if await is_member(user_id, context):
            await update.message.reply_text(
                "✅ شما قبلاً در کانال عضو شده‌اید. به ربات خوش آمدید."
            )
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("عضویت در کانال", url=f"https://t.me/{REQUIRED_CHANNEL.strip('@')}")]
            ])
            
            await update.message.reply_text(
                f"⚠️ برای استفاده از ربات، لطفاً ابتدا در کانال {REQUIRED_CHANNEL} عضو شوید.",
                reply_markup=keyboard
            )

    except Exception as e:
        # این پیام Fail-Safe است. اگر به این مرحله برسد، یعنی اجرای کد داخلی شما با خطا مواجه شده.
        await update.message.reply_text(f"❌ خطای داخلی: ربات نتوانست دستور را پردازش کند. (Err: {type(e).__name__})")
        logger.error(f"Critical error in start_command: {e}")


# فرمان /help (بدون تغییر)
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = "راهنمای کاربر: با دستور /start عضویت شما بررسی می‌شود."
    await update.message.reply_text(message)


# --- 3. ساختار اصلی Webhook ---

if not BOT_TOKEN:
    logger.error("BOT_TOKEN is missing, Application cannot be built.")
    application = None 
else:
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .updater(None)
        .concurrent_updates(True)
        .build()
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

# --- 4. تنظیم Webhook و Fast API ---

api = FastAPI()

@api.post(f"/bot")
async def telegram_webhook(request: Request):
    """Handles incoming Telegram updates via Webhook."""
    
    # ... (بقیه کد Fast API بدون تغییر)
    if not application:
         return JSONResponse(content={"message": "Internal Bot Error"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != API_SECRET:
        return JSONResponse(
            content={"message": "Invalid API Secret"}, 
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    try:
        update_json = await request.json()
        update = Update.de_json(update_json, application.bot)
        await application.process_update(update)
        return JSONResponse(content={"message": "OK"}, status_code=status.HTTP_200_OK)

    except Exception as e:
        # این خطا در سطح Worker است، نه خود ربات.
        logger.error(f"Error processing update in FastAPI: {e}")
        return JSONResponse(content={"message": "Error processing update"}, status_code=status.HTTP_200_OK)

