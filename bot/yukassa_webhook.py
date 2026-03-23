"""
bot/yukassa_webhook.py

aiohttp-обработчик вебхуков от ЮKassa.
Маршрут: POST /yukassa/webhook
ЮKassa шлёт JSON при изменении статуса платежа.
Документация: https://yookassa.ru/developers/using-api/webhooks
"""
import hashlib
import hmac
import json
import logging
import os

from aiohttp import web

from bot.db import queries as q

logger = logging.getLogger(__name__)

YK_SECRET_HEADER = "Idempotence-Key"  # ЮKassa не подписывает вебхуки HMAC —
# проверка идёт по IP или доп. секрету, здесь проверяем наличие payment в БД.


async def yukassa_webhook_handler(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        logger.warning("YK webhook: invalid JSON")
        return web.Response(status=400, text="bad request")

    event_type = body.get("type")
    obj = body.get("object", {})

    if event_type != "payment.succeeded":
        # Нас интересует только успешная оплата
        return web.Response(text="ok")

    payment_id = obj.get("id")
    if not payment_id:
        return web.Response(status=400, text="no payment id")

    logger.info(f"YK webhook: payment.succeeded  id={payment_id}")

    # Ищем платёж в нашей БД
    payment = await q.get_payment_by_external_id(payment_id)
    if not payment:
        logger.warning(f"YK webhook: payment {payment_id} not found in DB")
        return web.Response(text="ok")  # 200 чтобы ЮKassa не ретраила

    if payment["status"] == "paid":
        logger.info(f"YK webhook: already paid {payment_id}")
        return web.Response(text="ok")

    # Подтверждаем
    await q.mark_payment_paid(payment_id)

    # Выдаём доступ
    from bot.db.queries import get_plan
    plan = await get_plan(payment["plan_id"])
    if plan:
        ch = await q.get_channel_by_id(payment["channel_id"])
        channel_title = ch.get("channel_title", str(payment["channel_id"])) if ch else ""

        # Получаем бот из app context
        bot = request.app["bot"]
        from bot.handlers.user_payment import _grant_access

        class _FakeMsg:
            async def answer(self, text, **kw):
                await bot.send_message(payment["user_id"], text, **kw)
            chat = None

        await _grant_access(bot, _FakeMsg(), payment["user_id"], plan, channel_title)
        logger.info(f"YK webhook: access granted to user {payment['user_id']}")

    return web.Response(text="ok")


def register_yukassa_webhook(app: web.Application, bot):
    """Регистрирует маршрут и передаёт бот в app context."""
    app["bot"] = bot
    app.router.add_post("/yukassa/webhook", yukassa_webhook_handler)
    logger.info("YooKassa webhook registered at /yukassa/webhook")
