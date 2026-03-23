import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from bot.db.models import create_tables
from bot.handlers import admin, cabinet, owner_stats, pay_logs
from bot.handlers import payment, plan_builder, user_payment, start
from bot.handlers import blacklist, plan_custom, white_label
from bot.middlewares.auto_register import AutoRegisterMiddleware
from bot.wl_manager import WLBotManager
from bot.yukassa_webhook import register_yukassa_webhook
from bot.scheduler.kick_checker import (
    check_expired_subscriptions,
    check_expiry_reminders,
    check_expired_keys,
    check_pending_payments,
    check_renewal_offers,
)

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
REDIS_URL    = os.getenv("REDIS_URL", "")
WEBHOOK_HOST = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL  = f"https://{WEBHOOK_HOST}{WEBHOOK_PATH}" if WEBHOOK_HOST else ""
WEBAPP_HOST  = "0.0.0.0"
WEBAPP_PORT  = int(os.getenv("PORT", "8080"))
USE_WEBHOOK  = bool(WEBHOOK_HOST)


def _build_storage():
    if REDIS_URL:
        try:
            s = RedisStorage.from_url(REDIS_URL)
            logger.info("FSM: Redis")
            return s
        except Exception as e:
            logger.warning(f"Redis failed ({e}), using Memory")
    logger.info("FSM: Memory")
    return MemoryStorage()


def _build_scheduler(bot: Bot, wl: WLBotManager) -> AsyncIOScheduler:
    s = AsyncIOScheduler(timezone="UTC")
    s.add_job(check_expired_subscriptions, "interval", minutes=10, args=[bot])
    s.add_job(check_expiry_reminders,      "interval", hours=6,   args=[bot])
    s.add_job(check_renewal_offers,        "interval", hours=1,   args=[bot])
    s.add_job(check_expired_keys,          "interval", hours=1)
    s.add_job(check_pending_payments,      "interval", minutes=5, args=[bot])
    return s


def _build_dispatcher(storage) -> Dispatcher:
    dp = Dispatcher(storage=storage)
    dp.update.middleware(AutoRegisterMiddleware())
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(payment.router)
    dp.include_router(user_payment.router)
    dp.include_router(plan_builder.router)
    dp.include_router(cabinet.router)
    dp.include_router(owner_stats.router)
    dp.include_router(pay_logs.router)
    dp.include_router(blacklist.router)
    dp.include_router(plan_custom.router)
    dp.include_router(white_label.router)
    return dp


async def on_startup(bot: Bot, scheduler: AsyncIOScheduler, wl: WLBotManager):
    await bot.set_webhook(
        url=WEBHOOK_URL,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
    )
    scheduler.start()
    await wl.start_all()
    logger.info(f"Webhook: {WEBHOOK_URL}")


async def on_shutdown(bot: Bot, scheduler: AsyncIOScheduler, wl: WLBotManager):
    scheduler.shutdown(wait=False)
    await wl.stop_all()
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("Shutdown complete")


async def run_webhook(bot: Bot, dp: Dispatcher, wl: WLBotManager):
    scheduler = _build_scheduler(bot, wl)
    dp.startup.register(lambda: on_startup(bot, scheduler, wl))
    dp.shutdown.register(lambda: on_shutdown(bot, scheduler, wl))

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    register_yukassa_webhook(app, bot)

    async def health(_): return web.Response(text="ok")
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT).start()
    logger.info(f"Webhook server: {WEBAPP_HOST}:{WEBAPP_PORT}")
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


async def run_polling(bot: Bot, dp: Dispatcher, wl: WLBotManager):
    scheduler = _build_scheduler(bot, wl)
    scheduler.start()
    await wl.start_all()
    logger.info(f"WL bots running: {wl.count()}")
    logger.info("POLLING mode")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        scheduler.shutdown(wait=False)
        await wl.stop_all()
        await bot.session.close()
        logger.info("Shutdown complete")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = _build_storage()
    dp = _build_dispatcher(storage)

    # Инициализируем WL-менеджер и передаём в white_label handler
    wl = WLBotManager()
    white_label.wl_manager = wl

    await create_tables()
    logger.info("Database ready")

    mode = "WEBHOOK" if USE_WEBHOOK else "POLLING"
    logger.info(f"Starting in {mode} mode")

    if USE_WEBHOOK:
        await run_webhook(bot, dp, wl)
    else:
        await run_polling(bot, dp, wl)


if __name__ == "__main__":
    asyncio.run(main())
