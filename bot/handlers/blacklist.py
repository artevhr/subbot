"""handlers/blacklist.py — управление чёрным списком для владельца канала."""
import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.db import queries as q
from bot import texts
from bot.keyboards import blacklist_kb, back_cabinet_kb

logger = logging.getLogger(__name__)
router = Router()


class BlacklistState(StatesGroup):
    add_user_id = State()


@router.callback_query(F.data == "blacklist")
async def blacklist_view(callback: CallbackQuery):
    entries = await q.get_blacklist_by_owner(callback.from_user.id)
    text = texts.BL_LIST_HEADER
    if entries:
        for e in entries:
            from datetime import datetime
            try:
                dt = datetime.strptime(e["created_at"], "%Y-%m-%d %H:%M:%S")
                date_str = dt.strftime("%d.%m.%Y")
            except Exception:
                date_str = "—"
            uname = e.get("username") or "—"
            text += texts.BL_LIST_ITEM.format(
                user_id=e["banned_user_id"],
                username=uname,
                reason=e.get("reason") or "—",
                date=date_str,
            )
    else:
        text += texts.BL_LIST_EMPTY

    await callback.message.edit_text(
        text, reply_markup=blacklist_kb(entries), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "bl_add")
async def blacklist_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BlacklistState.add_user_id)
    await callback.message.edit_text(texts.BL_ADD_PROMPT, parse_mode="HTML")
    await callback.answer()


@router.message(BlacklistState.add_user_id)
async def blacklist_add_process(message: Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи числовой Telegram ID, например: <code>123456789</code>", parse_mode="HTML")
        return

    added = await q.add_to_blacklist(message.from_user.id, user_id)
    await state.clear()
    if added:
        await message.answer(
            texts.BL_ADD_SUCCESS.format(user_id=user_id),
            parse_mode="HTML",
            reply_markup=back_cabinet_kb(),
        )
    else:
        await message.answer(texts.BL_ADD_ALREADY, parse_mode="HTML", reply_markup=back_cabinet_kb())


@router.callback_query(F.data.startswith("bl_unban:"))
async def blacklist_unban(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    removed = await q.remove_from_blacklist(callback.from_user.id, user_id)
    if removed:
        await callback.answer(texts.BL_REMOVE_SUCCESS.format(user_id=user_id), show_alert=True)
    else:
        await callback.answer(texts.BL_REMOVE_NOT_FOUND, show_alert=True)
    # Обновляем список
    entries = await q.get_blacklist_by_owner(callback.from_user.id)
    text = texts.BL_LIST_HEADER + (
        "".join(
            texts.BL_LIST_ITEM.format(
                user_id=e["banned_user_id"],
                username=e.get("username") or "—",
                reason=e.get("reason") or "—",
                date=e.get("created_at", "")[:10],
            ) for e in entries
        ) if entries else texts.BL_LIST_EMPTY
    )
    await callback.message.edit_text(
        text, reply_markup=blacklist_kb(entries), parse_mode="HTML"
    )
