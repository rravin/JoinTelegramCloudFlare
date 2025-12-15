# JoinCloudFlare.py - Fix v4.1 (Final Import and Error Handling Fix for Cloudflare Workers)

import os
import logging
from typing import Final
# اطمینان از Import تمام اشیاء مورد نیاز برای دکمه و خطا
from telegram import Update, error, InlineKeyboardMarkup, InlineKeyboardButton 
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackContext,
)
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

# --- 1. تنظیمات و متغیرهای محیطی ---

# تنظیمات Logging
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
    
    # تبدیل رشته ADMIN_IDS به لیست اعداد صحیح 
    ADMIN_IDS: Final[list[int]] = [int(i.strip()) for i in ADMIN_IDS_STR.split(',') if i.strip()]

    if not all([BOT_TOKEN, API_SECRET, REQUIRED_CHANNEL, ADMIN_IDS_STR]):
        # اگر متغیرهای اساسی تنظیم نشده باشند، خطا می‌دهد (فقط هنگام استقرار)
        raise ValueError("One or more essential environment variables are missing.")
except Exception as e:
    logger.error(f"Error loading environment variables: {e}")


# --- 2. توابع اصلی ربات ---

# تابع کمکی برای بررسی عضویت
async def is_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if a user is a member of the required channel."""
    try:
        # get_chat_member برای گرفتن اطلاعات کاربر در کانال استفاده می‌شود.
        member = await context.bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        # عضویت با یکی از این وضعیت‌ها تایید می‌شود.
        return member.status in ['creator', 'administrator', 'member']
    except error.BadRequest:
        # اگر کاربر در کانال وجود نداشته باشد یا کانال خصوصی باشد و ربات ادمین نباشد، این خطا رخ می‌دهد.
        # در اکثر موارد، این به معنی عدم عضویت است.
        return False
    except Exception as e:
        logger.error(f"Error checking membership for user {user_id} in {REQUIRED_CHANNEL}: {e}")
        # در صورت بروز خطای ناشناخته، برای احتیاط دسترسی را رد می‌کنیم.
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
        # ساخت دکمه اینلاین
        keyboard = InlineKeyboardMarkup([
            # ساخت لینک عضویت با استفاده از نام کاربری کانال
            [InlineKeyboardButton("عضویت در کانال", url=f"https://t.me/{REQUIRED_CHANNEL.strip('@')}")]
        ])
        
        await update.message.reply_text(
            f"⚠️ برای استفاده از ربات، لطفاً ابتدا در کانال {REQUIRED_CHANNEL} عضو شوید.",
            reply_markup=keyboard
        )

# فرمان /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message."""
    if update.effective_user and update.effective_user.id in ADMIN_IDS:
        message = (
            "راهنمای ادمین:\n"
            "/start - شروع کار با ربات\n"
        )
    else:
        message = (
            "راهنمای کاربر:\n"
            "این ربات برای کنترل عضویت شما در کانال‌های اجباری طراحی شده است.\n"
            "با دستور /start عضویت شما بررسی می‌شود."
        )
    await update.message.reply_text(message)


# --- 3. ساختار اصلی Webhook ---

application = (
    Application.builder()
    .token(BOT_TOKEN)
    .updater(None)  # حالت Webhook
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
    
    # 1. بررسی API Secret
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != API_SECRET:
        return JSONResponse(
            content={"message": "Invalid API Secret"}, 
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    # 2. پردازش به‌روزرسانی
    try:
        update_json = await request.json()
        update = Update.de_json(update_json, application.bot)
        await application.process_update(update)

        # پاسخ موفقیت‌آمیز به تلگرام (مهم است که سریع پاسخ دهیم)
        return JSONResponse(content={"message": "OK"}, status_code=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error processing update: {e}")
        # در صورت خطا، همچنان پاسخ 200 می‌دهیم.
        return JSONResponse(content={"message": "Error"}, status_code=status.HTTP_200_OK)

