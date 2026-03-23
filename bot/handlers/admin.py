import asyncio
import logging
import os

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.db import queries as q
from bot import texts
from bot.keyboards import (
    admin_main_kb,
    admin_back_kb,
    admin_channel_toggle_kb,
    broadcast_confirm_kb,
    key_duration_kb,
    back_cabinet_kb,
)
from bot.utils.key_generator import generate_key

logger = logging.getLogger(__name__)
router = Router()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


class AdminState(StatesGroup):
    broadcast_text = State()
    broadcast_confirm = State()
    key_custom_days = State()


# ── ADMIN ENTRY ───────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer(texts.ADMIN_ONLY, parse_mode="HTML")
        return
    await state.clear()
    await message.answer(texts.ADMIN_WELCOME, reply_markup=admin_main_kb(), parse_mode="HTML")


@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        texts.ADMIN_WELCOME, reply_markup=admin_main_kb(), parse_mode="HTML"
    )
    await callback.answer()


# ── STATS ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return

    total_users = await q.count_users()
    active_keys = await q.count_active_keys()
    total_channels = await q.count_channels()
    active_subs = await q.count_active_subscriptions()

    await callback.message.edit_text(
        texts.ADMIN_STATS.format(
            total_users=total_users,
            active_keys=active_keys,
            total_channels=total_channels,
            active_subs=active_subs,
        ),
        reply_markup=admin_back_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── CHANNELS ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_channels")
async def admin_channels(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return

    channels = await q.get_all_channels()
    if not channels:
        await callback.message.edit_text(
            texts.ADMIN_CHANNELS_EMPTY, reply_markup=admin_back_kb(), parse_mode="HTML"
        )
        await callback.answer()
        return

    # Send each channel as a separate message with toggle button
    await callback.message.edit_text(
        texts.ADMIN_CHANNELS_HEADER, reply_markup=admin_back_kb(), parse_mode="HTML"
    )
    for ch in channels:
        subs = await q.count_active_subs_for_channel(ch["channel_id"])
        status = texts.CHANNEL_STATUS_ACTIVE if ch["is_active"] else texts.CHANNEL_STATUS_INACTIVE
        uname = ch.get("channel_username") or "—"
        text = texts.ADMIN_CHANNEL_ITEM.format(
            title=ch.get("channel_title", "—"),
            username=uname,
            owner=ch["owner_id"],
            subs=subs,
            status=status,
        )
        await callback.message.answer(
            text,
            reply_markup=admin_channel_toggle_kb(ch["channel_id"], ch["is_active"]),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_ch:"))
async def toggle_channel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    _, ch_id_str, new_status_str = callback.data.split(":")
    channel_id = int(ch_id_str)
    new_status = int(new_status_str)
    await q.toggle_channel_status(channel_id, new_status)
    status_label = texts.CHANNEL_STATUS_ACTIVE if new_status else texts.CHANNEL_STATUS_INACTIVE
    await callback.answer(f"Статус изменён: {status_label}", show_alert=True)
    # Update button
    await callback.message.edit_reply_markup(
        reply_markup=admin_channel_toggle_kb(channel_id, new_status)
    )


# ── BROADCAST ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    await state.set_state(AdminState.broadcast_text)
    await callback.message.edit_text(texts.ADMIN_BROADCAST_ASK, parse_mode="HTML")
    await callback.answer()


@router.message(AdminState.broadcast_text)
async def broadcast_got_text(message: Message, state: FSMContext):
    text = message.text or message.caption or ""
    user_ids = await q.get_all_user_ids()
    count = len(user_ids)
    await state.update_data(broadcast_text=text, user_ids=user_ids)
    await state.set_state(AdminState.broadcast_confirm)
    await message.answer(
        texts.ADMIN_BROADCAST_CONFIRM.format(count=count),
        reply_markup=broadcast_confirm_kb(count),
        parse_mode="HTML",
    )


@router.callback_query(AdminState.broadcast_confirm, F.data == "bc_confirm")
async def broadcast_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    bc_text = data.get("broadcast_text", "")
    user_ids: list[int] = data.get("user_ids", [])
    await state.clear()

    await callback.message.edit_text("📢 Рассылка запущена...", parse_mode="HTML")
    sent = 0
    errors = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, bc_text, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)  # flood control
        except Exception:
            errors += 1

    await callback.message.answer(
        texts.ADMIN_BROADCAST_DONE.format(sent=sent, errors=errors),
        reply_markup=admin_back_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(AdminState.broadcast_confirm, F.data == "bc_cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        texts.ADMIN_BROADCAST_CANCELLED,
        reply_markup=admin_back_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── CREATE KEY ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_create_key")
async def admin_create_key_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    await callback.message.edit_text(
        texts.ADMIN_KEY_STEP1,
        reply_markup=key_duration_kb(admin=True),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("key_dur:"))
async def admin_key_duration(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    value = callback.data.split(":")[1]
    if value == "custom":
        await state.set_state(AdminState.key_custom_days)
        await callback.message.edit_text("Введи количество дней:", parse_mode="HTML")
        await callback.answer()
        return
    days = int(value)
    await _finish_admin_key(callback.message, callback.from_user.id, days)
    await callback.answer()


@router.message(AdminState.key_custom_days)
async def admin_key_custom_days(message: Message, state: FSMContext):
    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.LB_INVALID_NUMBER)
        return
    await state.clear()
    await _finish_admin_key(message, message.from_user.id, days)


async def _finish_admin_key(msg, creator_id: int, days: int):
    key_code = generate_key()
    await q.create_key(key_code, days, creator_id)
    await msg.answer(
        texts.ADMIN_KEY_RESULT.format(key_code=key_code, days=days),
        parse_mode="HTML",
        reply_markup=admin_back_kb(),
    )


# ── WHITE-LABEL BOTS (admin) ─────────────────────────────────────────────────

@router.callback_query(F.data == "admin_wl")
async def admin_wl_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    from bot.db.queries import get_all_wl_bots
    bots = await get_all_wl_bots()
    if not bots:
        await callback.message.edit_text(
            texts.ADMIN_WL_EMPTY, reply_markup=admin_back_kb(), parse_mode="HTML"
        )
        await callback.answer()
        return

    from bot.keyboards import admin_wl_toggle_kb
    await callback.message.edit_text(texts.ADMIN_WL_HEADER, reply_markup=admin_back_kb(), parse_mode="HTML")
    from datetime import datetime
    for wl in bots:
        key_exp = wl.get("key_expires_at", "—")
        if key_exp and key_exp != "—":
            try:
                dt = datetime.strptime(key_exp, "%Y-%m-%d %H:%M:%S")
                key_exp = dt.strftime("%d.%m.%Y")
            except Exception:
                pass
        status = "✅ работает" if wl["is_active"] else "⛔ остановлен"
        text = texts.ADMIN_WL_ITEM.format(
            bot_username=wl.get("bot_username", "—"),
            bot_name=wl.get("bot_name", "—"),
            owner_username=wl.get("owner_username") or str(wl["owner_id"]),
            owner_id=wl["owner_id"],
            key_expires=key_exp,
            status=status,
        )
        await callback.message.answer(
            text,
            reply_markup=admin_wl_toggle_kb(wl["owner_id"], wl["is_active"]),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_wl_toggle:"))
async def admin_wl_toggle(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    parts = callback.data.split(":")
    owner_id, new_status = int(parts[1]), int(parts[2])
    from bot.db.queries import toggle_wl_bot, get_wl_bot_by_owner
    await toggle_wl_bot(owner_id, new_status)
    wl = await get_wl_bot_by_owner(owner_id)
    # Стартуем/стопаем через wl_manager
    from bot.handlers.white_label import wl_manager
    if wl_manager:
        if new_status == 1 and wl:
            await wl_manager.start_bot(owner_id, wl["bot_token"])
        else:
            await wl_manager.stop_bot(owner_id)
    from bot.keyboards import admin_wl_toggle_kb
    await callback.message.edit_reply_markup(
        reply_markup=admin_wl_toggle_kb(owner_id, new_status)
    )
    status_label = "✅ включён" if new_status else "⛔ отключён"
    await callback.answer(f"Бот {status_label}", show_alert=True)
