"""
bot/handlers/wl_client.py

Клиентские хэндлеры для white-label ботов.
Каждый раз возвращает НОВЫЙ Router() — нельзя переиспользовать
один и тот же роутер в нескольких Dispatcher'ах.
"""
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot.db import queries as q
from bot import texts
from bot.keyboards import main_menu_kb


def build_wl_router() -> Router:
    """
    Вызывается при старте каждого WL-бота.
    Возвращает свежий Router с зарегистрированными хэндлерами.
    """
    router = Router()

    # ── /start + deeplink join_<plan_id> ──────────────────────────────────────

    @router.message(CommandStart())
    async def wl_start(message: Message, command: CommandObject, state: FSMContext):
        user = message.from_user
        username = user.username or user.full_name
        await q.get_or_create_user(user.id, username)
        await q.update_username(user.id, username)

        args = command.args or ""

        if args.startswith("join_"):
            try:
                plan_id = int(args.replace("join_", ""))
            except ValueError:
                plan_id = None
            if plan_id:
                from bot.handlers.user_payment import start_purchase_flow
                await start_purchase_flow(message, plan_id, state)
                return

        # Обычный /start — минимальное приветствие
        await message.answer(
            f"👋 Привет, <b>{user.first_name}</b>!\n\n"
            "Перейди по ссылке от владельца канала чтобы оформить подписку.",
            parse_mode="HTML",
        )

    # ── Оплата: выбор метода, проверка, кнопка продлить ──────────────────────

    @router.callback_query(F.data.startswith("pay_with:"))
    async def wl_pay_method(callback: CallbackQuery, state: FSMContext):
        from bot.handlers.user_payment import pay_method_chosen
        await pay_method_chosen(callback, state, callback.bot)

    @router.callback_query(F.data.startswith("pay_check:"))
    async def wl_pay_check(callback: CallbackQuery, state: FSMContext):
        from bot.handlers.user_payment import pay_check
        await pay_check(callback, state, callback.bot)

    @router.callback_query(F.data == "pay_cancel")
    async def wl_pay_cancel(callback: CallbackQuery, state: FSMContext):
        from bot.handlers.user_payment import pay_cancel
        await pay_cancel(callback, state)

    @router.callback_query(F.data.startswith("renew:"))
    async def wl_renew(callback: CallbackQuery, state: FSMContext):
        from bot.handlers.user_payment import renewal_button
        await renewal_button(callback, state)

    @router.message()
    async def wl_key_input(message: Message, state: FSMContext):
        """Ловим ввод ключа доступа в состоянии enter_key."""
        from aiogram.fsm.state import State
        current = await state.get_state()
        if current == "UserPayState:enter_key":
            from bot.handlers.user_payment import process_key
            await process_key(message, state, message.bot)

    return router
