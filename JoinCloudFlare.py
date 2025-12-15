# JoinCloudFlare.py - Fix v5.0 (Simplified Architecture and Fail-Safe)

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

# بارگذاری متغیرها با مدیریت خطا
try:
    BOT_TOKEN: Final[str] = os.environ.get("BOT_TOKEN")
    API_SECRET: Final[str] = os.environ.get("API_SECRET")
    REQUIRED_CHANNEL: Final[str] = os.environ.get("REQUIRED_CHANNEL")
    ADMIN_IDS_STR: Final[str] = os.environ.get("ADMIN_IDS")
    
    # اطمینان از تبدیل صحیح ADMIN_IDS
    admin_ids_temp = []
    if ADMIN_IDS_STR:
        try:
            admin_ids_temp = [int(i.strip()) for i in ADMIN_IDS_STR.split(',') if i.strip().isdigit()]
        except Exception:
            pass
            
    ADMIN_IDS: Final[list[int]] = admin_ids_temp

    if not all([BOT_TOKEN, API_SECRET, REQUIRED_CHANNEL]):
        raise ValueError("Essential environment variables are missing.")
except Exception as e:
    logger.error(f"FATAL ERROR: Environment variables failed to load: {e}")
    BOT_TOKEN = None # برای جلوگیری از ساخت Application در صورت خطا


# --- 2. توابع اصلی ربات ---

# تابع کمکی برای بررسی عضویت
async def is_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if a user is a member of the required channel."""
    try:
        # اگر ربات ادمین کانال نباشد، در اینجا خطا رخ می‌دهد.
        member = await context.bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        # وضعیت‌های مورد پذیرش
        return member.status in ['creator', 'administrator', 'member']
    except error.BadRequest as e:
        # خطای عدم وجود کانال یا عدم عضویت کاربر
        logger.warning(f"BadRequest: {e}. User {user_id} might not be a member or channel is private.")
        return False
    except Exception as e:
        # خطای عمومی (مثلاً ربات ادمین کانال نیست)
        logger.error(f"Unexpected error in is_member: {e}")
        # در این حالت، برای احتیاط، دسترسی را رد می‌کنیم.
        return False

# فرمان /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and checks membership."""
    if update.effective_user is None:
        return
    
    user_id = update.effective_user.id
    
    # 1. اگر ادمین باشد
    if user_id in ADMIN_IDS:
        await update.message.reply_text(
            f"🚀 ادمین عزیز، خوش آمدید. (ID: {user_id})"
        )
        return

    # 2. بررسی عضویت
    if await is_member(user_id, context):
        await update.message.reply_text(
            "✅ شما قبلاً در کانال عضو شده‌اید. به ربات خوش آمدید."
        )
    else:
        # 3. ارسال پیام عدم عضویت با دکمه
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("عضویت در کانال", url=f"https://t.me/{REQUIRED_CHANNEL.strip('@')}")]
        ])
        
        await update.message.reply_text(
            f"⚠️ برای استفاده از ربات، لطفاً ابتدا در کانال {REQUIRED_CHANNEL} عضو شوید.",
            reply_markup=keyboard
        )

# --- 3. ساختار اصلی Webhook ---

# ساخت Application فقط در صورتی که توکن موجود باشد
application = None
if BOT_TOKEN:
    try:
        application = (
            Application.builder()
            .token(BOT_TOKEN)
            .updater(None)
            .concurrent_updates(True)
            .build()
        )
        application.add_handler(CommandHandler("start", start_command))
    except Exception as e:
        logger.error(f"Failed to build Application: {e}")

# --- 4. تنظیم Webhook و Fast API ---

api = FastAPI()

@api.post(f"/bot")
async def telegram_webhook(request: Request):
    """Handles incoming Telegram updates via Webhook."""
    
    # بررسی صحت ساخت Application
    if not application:
         logger.error("Application not built, returning 500.")
         return JSONResponse(content={"message": "Internal Bot Error"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # 1. بررسی API Secret
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != API_SECRET:
        logger.warning("Unauthorized webhook request.")
        return JSONResponse(
            content={"message": "Invalid API Secret"}, 
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    # 2. پردازش به‌روزرسانی
    try:
        # تلگرام به روزرسانی را ارسال می‌کند
        update_json = await request.json()
        update = Update.de_json(update_json, application.bot)
        
        # پردازش به‌روزرسانی توسط PTB (Python Telegram Bot)
        # این تابع خود به خود پاسخ‌های ربات را ارسال می‌کند.
        await application.process_update(update) 
        
        # پاسخ فوری به تلگرام با کد 200 (مهم‌ترین گام)
        return JSONResponse(content={"message": "OK"}, status_code=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Unhandled exception during update processing: {e}")
        # حتی در صورت بروز خطای پردازش، باید به تلگرام OK بدهیم.
        return JSONResponse(content={"message": "Error processing update"}, status_code=status.HTTP_200_OK)

