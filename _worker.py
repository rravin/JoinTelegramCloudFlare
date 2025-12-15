# نام فایل باید دقیقاً _worker.py باشد

from JoinCloudFlare import api # فرض می‌کنیم نام فایل اصلی شما backend_bot.py است
                            # اگر نام فایل شما JoinCloudFlare.py است، باید بنویسید:
                            # from JoinCloudFlare import api

from asgiref.wsgi import WsgiToAsgi
from typing import Awaitable
from starlette.requests import Request
from starlette.responses import Response

# ساخت یک واسط ASGI برای Cloudflare
asgi_app = WsgiToAsgi(api)

# تابع fetch که توسط Cloudflare Pages Functions فراخوانی می‌شود
async def fetch(request: Request) -> Response:
    return await asgi_app(request)
  
