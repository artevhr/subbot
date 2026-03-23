"""
bot/wl_manager.py

Менеджер white-label ботов.
Каждый WL-бот — отдельная asyncio-задача с минимальным Dispatcher
(только пользовательские хэндлеры: join_<plan_id>, оплата).
"""
import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.middlewares.auto_register import AutoRegisterMiddleware

logger = logging.getLogger(__name__)


def _build_wl_dispatcher() -> Dispatcher:
    """
    Минимальный диспетчер для WL-бота.
    build_wl_router() возвращает НОВЫЙ Router каждый раз —
    один роутер нельзя подключить к двум Dispatcher'ам.
    """
    from bot.handlers.wl_client import build_wl_router
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(AutoRegisterMiddleware())
    dp.include_router(build_wl_router())
    return dp


class WLBotManager:
    def __init__(self):
        self._tasks: dict[int, asyncio.Task] = {}   # owner_id → Task
        self._bots: dict[int, Bot] = {}              # owner_id → Bot

    async def start_all(self):
        """Вызывается при старте главного бота — поднимает все активные WL-боты."""
        from bot.db.queries import get_all_active_wl_bots
        bots = await get_all_active_wl_bots()
        for wl in bots:
            await self.start_bot(wl["owner_id"], wl["bot_token"])
        logger.info(f"WL manager: started {len(bots)} white-label bots")

    async def start_bot(self, owner_id: int, token: str):
        """Запускает polling для одного WL-бота."""
        # Если уже запущен — стопаем старый
        await self.stop_bot(owner_id)

        bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        dp = _build_wl_dispatcher()
        self._bots[owner_id] = bot

        task = asyncio.create_task(
            self._run_polling(owner_id, bot, dp),
            name=f"wl_bot_{owner_id}",
        )
        self._tasks[owner_id] = task
        logger.info(f"WL bot started for owner {owner_id}")

    async def stop_bot(self, owner_id: int):
        """Останавливает WL-бота."""
        task = self._tasks.pop(owner_id, None)
        bot = self._bots.pop(owner_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=3)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        if bot:
            try:
                await bot.session.close()
            except Exception:
                pass
        logger.info(f"WL bot stopped for owner {owner_id}")

    async def stop_all(self):
        owner_ids = list(self._tasks.keys())
        for owner_id in owner_ids:
            await self.stop_bot(owner_id)
        logger.info("WL manager: all bots stopped")

    async def _run_polling(self, owner_id: int, bot: Bot, dp: Dispatcher):
        try:
            await dp.start_polling(
                bot,
                allowed_updates=["message", "callback_query"],
                handle_signals=False,
            )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"WL bot {owner_id} crashed: {e}")
        finally:
            try:
                await bot.session.close()
            except Exception:
                pass

    def is_running(self, owner_id: int) -> bool:
        task = self._tasks.get(owner_id)
        return task is not None and not task.done()

    def count(self) -> int:
        return sum(1 for t in self._tasks.values() if not t.done())
