import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.db import queries as q
from bot import texts
from bot.keyboards import cabinet_no_key_kb, cabinet_active_kb, back_cabinet_kb, key_duration_kb

logger = logging.getLogger(__name__)
router = Router()


class EnterKeyState(StatesGroup):
    waiting_key = State()


class UserKeyState(StatesGroup):
    choose_duration = State()
    custom_duration = State()


async def show_cabinet(target, user_id: int, edit: bool = True):
    msg = target.message if isinstance(target, CallbackQuery) else target
    user = await q.get_user(user_id)
    if not user:
        return

    key_valid = await q.is_key_valid_for_user(user_id)
    key_status = texts.KEY_ACTIVE if key_valid else texts.KEY_INACTIVE
    expires_line = ""
    if key_valid and user.get("key_expires_at"):
        try:
            dt = datetime.strptime(user["key_expires_at"], "%Y-%m-%d %H:%M:%S")
            expires_line = texts.KEY_EXPIRES_LINE.format(date=dt.strftime("%d.%m.%Y %H:%M"))
        except ValueError:
            pass

    channels = await q.get_channels_by_owner(user_id)
    plans_count = await q.count_plans_by_owner(user_id)
    username = f"@{user['username']}" if user.get("username") else f"id{user_id}"

    text = texts.CABINET_TEMPLATE.format(
        username=username,
        key_status=key_status,
        expires_line=expires_line,
        channels_count=len(channels),
        plans_count=plans_count,
    )
    kb = cabinet_active_kb() if key_valid else cabinet_no_key_kb()

    if edit:
        await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=kb, parse_mode="HTML")

    if isinstance(target, CallbackQuery):
        await target.answer()


@router.callback_query(F.data == "cabinet")
async def open_cabinet(callback: CallbackQuery):
    await show_cabinet(callback, callback.from_user.id)


# ── Ввод ключа (для владельца канала) ─────────────────────────────────────────

@router.callback_query(F.data == "enter_key")
async def ask_key(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EnterKeyState.waiting_key)
    await callback.message.edit_text(texts.ASK_KEY, parse_mode="HTML")
    await callback.answer()


@router.message(EnterKeyState.waiting_key)
async def process_key(message: Message, state: FSMContext):
    key_code = message.text.strip().upper()
    key = await q.get_key(key_code)
    if not key:
        await message.answer(texts.KEY_NOT_FOUND, parse_mode="HTML")
        return

    total_days = await q.activate_key_for_user(message.from_user.id, key_code, key["duration_days"])
    bonus = total_days - key["duration_days"]
    bonus_line = texts.KEY_BONUS_LINE.format(days=bonus) if bonus > 0 else ""
    from datetime import timedelta
    expires_at = datetime.utcnow() + timedelta(days=total_days)

    await state.clear()
    await message.answer(
        texts.KEY_ACTIVATED.format(
            date=expires_at.strftime("%d.%m.%Y"),
            bonus_line=bonus_line,
        ),
        parse_mode="HTML",
    )
    await show_cabinet(message, message.from_user.id, edit=False)


# ── Мои каналы ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "my_channels")
async def my_channels(callback: CallbackQuery):
    channels = await q.get_channels_by_owner(callback.from_user.id)
    if not channels:
        await callback.message.edit_text(
            texts.MY_CHANNELS_EMPTY, reply_markup=back_cabinet_kb(), parse_mode="HTML"
        )
        await callback.answer()
        return

    text = texts.MY_CHANNELS_HEADER
    for ch in channels:
        subs = await q.count_active_subs_for_channel(ch["channel_id"])
        status = texts.CHANNEL_STATUS_ACTIVE if ch["is_active"] else texts.CHANNEL_STATUS_INACTIVE
        text += texts.CHANNEL_ITEM.format(
            title=ch.get("channel_title", "—"),
            username=ch.get("channel_username") or "—",
            status=status,
            subs=subs,
        )
    await callback.message.edit_text(text, reply_markup=back_cabinet_kb(), parse_mode="HTML")
    await callback.answer()


# ── Мои планы ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "my_plans")
async def my_plans(callback: CallbackQuery):
    plans = await q.get_plans_by_owner(callback.from_user.id)
    if not plans:
        await callback.message.edit_text(
            texts.MY_PLANS_EMPTY, reply_markup=back_cabinet_kb(), parse_mode="HTML"
        )
        await callback.answer()
        return

    bot_info = await callback.bot.get_me()
    text = texts.MY_PLANS_HEADER
    for p in plans:
        ch = await q.get_channel_by_id(p["channel_id"])
        ch_title = ch.get("channel_title", str(p["channel_id"])) if ch else str(p["channel_id"])
        subs = await q.count_active_subs_for_channel(p["channel_id"])
        bot_link = f"https://t.me/{bot_info.username}?start=join_{p['id']}"
        text += texts.PLAN_ITEM.format(
            title=p["title"],
            channel=ch_title,
            days=p["membership_duration_days"],
            subs=subs,
            bot_link=bot_link,
        )
    await callback.message.edit_text(text, reply_markup=back_cabinet_kb(), parse_mode="HTML")
    await callback.answer()


# ── Создать ключ участника ────────────────────────────────────────────────────

@router.callback_query(F.data == "create_user_key")
async def create_user_key_start(callback: CallbackQuery, state: FSMContext):
    if not await q.is_key_valid_for_user(callback.from_user.id):
        await callback.answer(texts.NO_ACCESS, show_alert=True)
        return
    await state.set_state(UserKeyState.choose_duration)
    await callback.message.edit_text(
        texts.USER_KEY_STEP1, reply_markup=key_duration_kb(admin=False), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(UserKeyState.choose_duration, F.data.startswith("key_dur:"))
async def user_key_duration(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":")[1]
    if value == "custom":
        await state.set_state(UserKeyState.custom_duration)
        await callback.message.edit_text(texts.USER_KEY_CUSTOM, parse_mode="HTML")
    else:
        await _finish_user_key(callback.message, state, callback.from_user.id, int(value))
    await callback.answer()


@router.message(UserKeyState.custom_duration)
async def user_key_custom(message: Message, state: FSMContext):
    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.INVALID_NUMBER)
        return
    await _finish_user_key(message, state, message.from_user.id, days)


async def _finish_user_key(msg, state: FSMContext, creator_id: int, days: int):
    from bot.utils.key_generator import generate_key
    key_code = generate_key()
    await q.create_key(key_code, days, creator_id)
    await state.clear()
    await msg.answer(
        texts.USER_KEY_RESULT.format(key_code=key_code, days=days),
        parse_mode="HTML", reply_markup=back_cabinet_kb(),
    )


@router.callback_query(F.data == "cancel_fsm")
async def cancel_fsm(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer(texts.CANCELLED)
    await show_cabinet(callback, callback.from_user.id)
