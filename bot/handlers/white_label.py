"""
handlers/white_label.py

Владелец подключает свой бот-токен.
Система запускает отдельный Dispatcher для его бота.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.db import queries as q
from bot import texts
from bot.keyboards import wl_choose_kb, wl_manage_kb, wl_replace_confirm_kb, back_cabinet_kb

logger = logging.getLogger(__name__)
router = Router()

# Ссылка на менеджер WL-ботов (инициализируется из main.py)
wl_manager = None


class WLState(StatesGroup):
    enter_token = State()
    confirm_replace = State()


@router.callback_query(F.data == "wl_bot")
async def wl_bot_menu(callback: CallbackQuery):
    existing = await q.get_wl_bot_by_owner(callback.from_user.id)
    if existing:
        status = "✅ работает" if existing["is_active"] else "⛔ остановлен"
        await callback.message.edit_text(
            texts.WL_STATUS.format(
                username=existing.get("bot_username", "—"),
                status=status,
            ),
            reply_markup=wl_manage_kb(existing["is_active"], callback.from_user.id),
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            texts.WL_CHOOSE,
            reply_markup=wl_choose_kb(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "wl_connect")
async def wl_connect_start(callback: CallbackQuery, state: FSMContext):
    if not await q.is_key_valid_for_user(callback.from_user.id):
        await callback.answer(texts.NO_ACCESS, show_alert=True)
        return
    existing = await q.get_wl_bot_by_owner(callback.from_user.id)
    if existing:
        # Предлагаем заменить
        await state.set_state(WLState.confirm_replace)
        await callback.message.edit_text(
            texts.WL_ALREADY_EXISTS.format(username=existing.get("bot_username", "—")),
            reply_markup=wl_replace_confirm_kb(),
            parse_mode="HTML",
        )
    else:
        await state.set_state(WLState.enter_token)
        await callback.message.edit_text(texts.WL_TOKEN_PROMPT, parse_mode="HTML")
    await callback.answer()


@router.callback_query(WLState.confirm_replace, F.data == "wl_replace_yes")
async def wl_replace_confirm(callback: CallbackQuery, state: FSMContext):
    await state.set_state(WLState.enter_token)
    await callback.message.edit_text(texts.WL_TOKEN_PROMPT, parse_mode="HTML")
    await callback.answer()


@router.callback_query(WLState.confirm_replace, F.data == "wl_my_bot")
async def wl_replace_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await wl_bot_menu(callback)


@router.message(WLState.enter_token)
async def wl_token_received(message: Message, state: FSMContext):
    token = message.text.strip()
    owner_id = message.from_user.id

    # Валидируем токен через Telegram API
    try:
        test_bot = Bot(token=token)
        bot_info = await test_bot.get_me()
        await test_bot.session.close()
    except Exception:
        await message.answer(texts.WL_TOKEN_INVALID, parse_mode="HTML")
        return

    await state.clear()

    # Удаляем старого WL-бота если есть
    old = await q.get_wl_bot_by_owner(owner_id)
    if old:
        if wl_manager:
            await wl_manager.stop_bot(owner_id)
        await q.delete_wl_bot(owner_id)

    # Сохраняем новый
    wl = await q.create_wl_bot(owner_id, token, bot_info.username, bot_info.full_name)
    if not wl:
        await message.answer(texts.WL_TOKEN_TAKEN, parse_mode="HTML")
        return

    # Запускаем
    if wl_manager:
        await wl_manager.start_bot(owner_id, token)

    await message.answer(
        texts.WL_SUCCESS.format(username=bot_info.username),
        parse_mode="HTML",
        reply_markup=back_cabinet_kb(),
    )


@router.callback_query(F.data.startswith("wl_stop:"))
async def wl_stop(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if owner_id != callback.from_user.id:
        await callback.answer("❌ Нет доступа.", show_alert=True)
        return
    wl = await q.get_wl_bot_by_owner(owner_id)
    if wl_manager:
        await wl_manager.stop_bot(owner_id)
    await q.toggle_wl_bot(owner_id, 0)
    await callback.answer(texts.WL_STOPPED.format(username=wl.get("bot_username", "—")), show_alert=True)
    await wl_bot_menu(callback)


@router.callback_query(F.data.startswith("wl_start:"))
async def wl_start(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if owner_id != callback.from_user.id:
        await callback.answer("❌ Нет доступа.", show_alert=True)
        return
    wl = await q.get_wl_bot_by_owner(owner_id)
    if wl and wl_manager:
        await wl_manager.start_bot(owner_id, wl["bot_token"])
    await q.toggle_wl_bot(owner_id, 1)
    await callback.answer(texts.WL_STARTED.format(username=wl.get("bot_username", "—")), show_alert=True)
    await wl_bot_menu(callback)


@router.callback_query(F.data.startswith("wl_delete:"))
async def wl_delete(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if owner_id != callback.from_user.id:
        await callback.answer("❌ Нет доступа.", show_alert=True)
        return
    wl = await q.get_wl_bot_by_owner(owner_id)
    if wl_manager:
        await wl_manager.stop_bot(owner_id)
    await q.delete_wl_bot(owner_id)
    await callback.answer(texts.WL_DELETED.format(username=wl.get("bot_username", "—")), show_alert=True)
    await callback.message.edit_text(
        texts.WL_CHOOSE, reply_markup=wl_choose_kb(), parse_mode="HTML"
    )
