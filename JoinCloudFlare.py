# JoinCloudFlare.py - Fix v3.0 for Cloudflare Workers/Pages Functions (Webhook Only)

import os
import logging
import asyncio
from typing import Final, Coroutine, Any, Callable
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    CallbackContext,
)
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

# --- 1. تنظیمات و متغیرهای محیطی ---

# اطمینان از تعریف صحیح متغیرهای محیطی
try:
    BOT_TOKEN: Final[str] = os.environ.get("BOT_TOKEN")
    API_SECRET: Final[str] = os.environ.get("API_SECRET")
    REQUIRED_CHANNEL: Final[str] = os.environ.get("REQUIRED_CHANNEL")
    ADMIN_IDS_STR: Final[str] = os.environ.get("ADMIN_IDS")
    
    # تبدیل رشته ADMIN_IDS به لیست اعداد صحیح
    ADMIN_IDS: Final[list[int]] = [int(i.strip()) for i in ADMIN_IDS_STR.split(',') if i.strip()]

    if not all([BOT_TOKEN, API_SECRET, REQUIRED_CHANNEL, ADMIN_IDS_STR]):
        raise ValueError("One or more essential environment variables are missing.")
except Exception as e:
    # این خطا فقط در زمان Deploy نشان داده می‌شود.
    logging.error(f"Error loading environment variables: {e}")
    # اگر متغیرها در محیط Deploy تنظیم شده باشند، این بخش اجرا نمی‌شود.


# --- 2. توابع اصلی ربات ---

# تنظیم Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# تابع کمکی برای بررسی عضویت
async def is_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if a user is a member of the required channel."""
    try:
        # get_chat_member برای گرفتن اطلاعات کاربر در کانال استفاده می‌شود.
        member = await context.bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        # عضویت با یکی از این وضعیت‌ها تایید می‌شود.
        return member.status in ['creator', 'administrator', 'member']
    except Exception as e:
        logger.error(f"Error checking membership for user {user_id} in {REQUIRED_CHANNEL}: {e}")
        return False

# فرمان /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and checks membership."""
    if update.effective_user is None:
        return

    user_id = update.effective_user.id

    if user_id in ADMIN_IDS:
        await update.message.reply_text(
            f"🚀 ادمین عزیز، خوش آمدید. ربات شما آماده کار است. (ID: {user_id})"
        )
        return

    if await is_member(user_id, context):
        await update.message.reply_text(
            "✅ شما قبلاً در کانال عضو شده‌اید. به ربات خوش آمدید."
        )
    else:
        # پیام و دکمه عضویت
        await update.message.reply_text(
            f"⚠️ برای استفاده از ربات، لطفاً ابتدا در کانال {REQUIRED_CHANNEL} عضو شوید.",
            # در اینجا باید لینک کانال را قرار دهید. 
            # اگر فقط نام کاربری کانال را دارید، تلگرام آن را به لینک تبدیل می‌کند.
            reply_markup=telegram.InlineKeyboardMarkup([
                [telegram.InlineKeyboardButton("عضویت در کانال", url=f"https://t.me/{REQUIRED_CHANNEL.strip('@')}")]
            ])
        )

# فرمان /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message."""
    if update.effective_user and update.effective_user.id in ADMIN_IDS:
        message = (
            "راهنمای ادمین:\n"
            "/start - شروع کار با ربات\n"
            "/stats - مشاهده آمار و وضعیت ربات (اختیاری)\n"
            "ربات در حال حاضر فقط برای بررسی عضویت طراحی شده است."
        )
    else:
        message = (
            "راهنمای کاربر:\n"
            "این ربات برای کنترل عضویت شما در کانال‌های اجباری طراحی شده است.\n"
            "با دستور /start عضویت شما بررسی می‌شود."
        )
    await update.message.reply_text(message)


# --- 3. ساختار اصلی Webhook ---

# ساخت Application (تنها یک بار در زمان لود شدن برنامه در Worker اجرا می‌شود)
# Application.builder() را به صورت مستقیم در متغیر نگه می‌داریم.
# نیازی به استفاده از .run_polling() یا Updater نیست.
application = (
    Application.builder()
    .token(BOT_TOKEN)
    .updater(None)  # جلوگیری از ساخت Updater اضافی
    .concurrent_updates(True)
    .build()
)

# افزودن هندلرها به Application
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("help", help_command))
# application.add_handler(CallbackQueryHandler(button_handler))  # اگر دکمه دارید، این را فعال کنید.

# --- 4. تنظیم Webhook و Fast API ---

# تعریف شیء FastAPI برای مدیریت درخواست‌های HTTP
api = FastAPI()

@api.post(f"/bot")
async def telegram_webhook(request: Request):
    """Handles incoming Telegram updates via Webhook."""
    
    # 1. بررسی API Secret
    # برای امنیت، این SECRET باید با SECRET ست شده در Webhook URL یکی باشد.
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != API_SECRET:
        return JSONResponse(
            content={"message": "Invalid API Secret"}, 
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    # 2. پردازش به‌روزرسانی
    try:
        # دریافت داده‌های JSON از درخواست
        update_json = await request.json()
        
        # تبدیل JSON به شیء Update تلگرام
        update = Update.de_json(update_json, application.bot)
        
        # پردازش به‌روزرسانی توسط Application تلگرام
        await application.process_update(update)

        # پاسخ موفقیت‌آمیز به تلگرام (مهم است که سریع پاسخ دهیم)
        return JSONResponse(content={"message": "OK"}, status_code=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error processing update: {e}")
        # در صورت خطا، همچنان به تلگرام پاسخ موفقیت‌آمیز می‌دهیم تا دوباره تلاش نکند.
        return JSONResponse(content={"message": "Error"}, status_code=status.HTTP_200_OK)


# --- 5. خروجی اصلی برای _worker.py ---

# این شیء 'api' است که توسط _worker.py import می‌شود و به عنوان Worker اجرا می‌گردد.
# نیازی به افزودن کد در if __name__ == "__main__": نیست.


