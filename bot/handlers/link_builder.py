"""
Link Builder FSM — 7 шагов (добавлен шаг платёжного шлюза).
Шаг 7: Платёжный шлюз? (если у канала настроена оплата)
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.db import queries as q
from bot import texts
from bot.keyboards import (
    payment_methods_kb, link_expiry_kb, membership_duration_kb,
    max_members_kb, require_key_kb, payment_gate_kb, back_cabinet_kb,
)

logger = logging.getLogger(__name__)
router = Router()


class LinkBuilderState(StatesGroup):
    step1_channel = State()
    step2_payment = State()
    step3_link_expiry = State()
    step4_membership = State()
    step4_custom = State()
    step5_max_members = State()
    step6_require_key = State()
    step7_payment_gate = State()


# ── STEP 1 ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "create_link")
async def create_link_start(callback: CallbackQuery, state: FSMContext):
    if not await q.is_key_valid_for_user(callback.from_user.id):
        await callback.answer(texts.NO_ACCESS, show_alert=True)
        return
    await state.set_state(LinkBuilderState.step1_channel)
    await callback.message.edit_text(texts.LB_STEP1, parse_mode="HTML")
    await callback.answer()


@router.message(LinkBuilderState.step1_channel)
async def step1_channel(message: Message, state: FSMContext, bot: Bot):
    raw = message.text.strip()
    channel_info = await _resolve_channel(bot, raw)
    if channel_info is None:
        await message.answer(texts.LB_CHANNEL_NOT_FOUND, parse_mode="HTML")
        return
    channel_id, channel_username, channel_title = channel_info
    if not await _bot_is_admin(bot, channel_id):
        await message.answer(
            texts.LB_NOT_ADMIN.format(channel=channel_title or raw), parse_mode="HTML"
        )
        return
    await state.update_data(
        channel_id=channel_id, channel_username=channel_username,
        channel_title=channel_title, payment_methods=[],
    )
    await state.set_state(LinkBuilderState.step2_payment)
    await message.answer(texts.LB_STEP2_FIRST, reply_markup=payment_methods_kb(), parse_mode="HTML")


# ── STEP 2 ────────────────────────────────────────────────────────────────────

@router.message(LinkBuilderState.step2_payment)
async def step2_add_payment(message: Message, state: FSMContext):
    data = await state.get_data()
    methods: list = data.get("payment_methods", [])
    methods.append(message.text.strip())
    await state.update_data(payment_methods=methods)
    await message.answer(
        texts.LB_STEP2.format(methods=", ".join(methods)),
        reply_markup=payment_methods_kb(), parse_mode="HTML",
    )


@router.callback_query(LinkBuilderState.step2_payment, F.data == "add_payment")
async def step2_add_more(callback: CallbackQuery):
    await callback.answer("Введи следующий способ оплаты:")


@router.callback_query(LinkBuilderState.step2_payment, F.data == "payment_done")
async def step2_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("payment_methods"):
        await callback.answer("Добавь хотя бы один способ оплаты!", show_alert=True)
        return
    await state.set_state(LinkBuilderState.step3_link_expiry)
    await callback.message.edit_text(texts.LB_STEP3, reply_markup=link_expiry_kb(), parse_mode="HTML")
    await callback.answer()


# ── STEP 3 ────────────────────────────────────────────────────────────────────

@router.callback_query(LinkBuilderState.step3_link_expiry, F.data.startswith("link_expire:"))
async def step3_link_expiry(callback: CallbackQuery, state: FSMContext):
    value = int(callback.data.split(":")[1])
    await state.update_data(link_expire_days=value)
    await state.set_state(LinkBuilderState.step4_membership)
    await callback.message.edit_text(
        texts.LB_STEP4, reply_markup=membership_duration_kb(), parse_mode="HTML"
    )
    await callback.answer()


# ── STEP 4 ────────────────────────────────────────────────────────────────────

@router.callback_query(LinkBuilderState.step4_membership, F.data.startswith("membership:"))
async def step4_membership(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":")[1]
    if value == "custom":
        await state.set_state(LinkBuilderState.step4_custom)
        await callback.message.edit_text("Введи количество дней (срок подписки):", parse_mode="HTML")
        await callback.answer()
        return
    await state.update_data(membership_days=int(value))
    await state.set_state(LinkBuilderState.step5_max_members)
    await callback.message.edit_text(texts.LB_STEP5, reply_markup=max_members_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(LinkBuilderState.step4_custom)
async def step4_custom_days(message: Message, state: FSMContext):
    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.LB_INVALID_NUMBER)
        return
    await state.update_data(membership_days=days)
    await state.set_state(LinkBuilderState.step5_max_members)
    await message.answer(texts.LB_STEP5, reply_markup=max_members_kb(), parse_mode="HTML")


# ── STEP 5 ────────────────────────────────────────────────────────────────────

@router.callback_query(LinkBuilderState.step5_max_members, F.data.startswith("max_members:"))
async def step5_max_unlimited(callback: CallbackQuery, state: FSMContext):
    await state.update_data(max_members=None)
    await state.set_state(LinkBuilderState.step6_require_key)
    await callback.message.edit_text(texts.LB_STEP6, reply_markup=require_key_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(LinkBuilderState.step5_max_members)
async def step5_max_custom(message: Message, state: FSMContext):
    try:
        max_m = int(message.text.strip())
        if max_m <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.LB_INVALID_NUMBER)
        return
    await state.update_data(max_members=max_m)
    await state.set_state(LinkBuilderState.step6_require_key)
    await message.answer(texts.LB_STEP6, reply_markup=require_key_kb(), parse_mode="HTML")


# ── STEP 6 ────────────────────────────────────────────────────────────────────

@router.callback_query(LinkBuilderState.step6_require_key, F.data.startswith("require_key:"))
async def step6_require_key(callback: CallbackQuery, state: FSMContext):
    require = callback.data.split(":")[1] == "yes"
    await state.update_data(require_key=require)

    # Проверяем есть ли у этого канала настроенная оплата
    data = await state.get_data()
    ps = await q.get_payment_settings(data["channel_id"])
    has_payment = ps and ps.get("payment_mode") != "manual"

    if has_payment:
        await state.set_state(LinkBuilderState.step7_payment_gate)
        await callback.message.edit_text(
            "💳 <b>Шаг 7/7 — Платёжный шлюз</b>\n\n"
            "Для этого канала настроена оплата.\n"
            "Требовать оплату перед вступлением по этой ссылке?",
            reply_markup=payment_gate_kb(), parse_mode="HTML",
        )
    else:
        # Нет настроек оплаты — пропускаем шаг 7
        await state.update_data(payment_gate=False)
        await _finish(callback, state)

    await callback.answer()


# ── STEP 7 (опционально) ──────────────────────────────────────────────────────

@router.callback_query(LinkBuilderState.step7_payment_gate, F.data.startswith("payment_gate:"))
async def step7_payment_gate(callback: CallbackQuery, state: FSMContext, bot: Bot):
    payment_gate = callback.data.split(":")[1] == "yes"
    await state.update_data(payment_gate=payment_gate)
    await _finish(callback, state)
    await callback.answer()


# ── FINISH ────────────────────────────────────────────────────────────────────

async def _finish(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    await callback.message.edit_text("⏳ Создаю ссылку...", parse_mode="HTML")
    try:
        result = await _finish_link_creation(callback.bot, callback.from_user.id, data)
        await callback.message.edit_text(result, parse_mode="HTML", reply_markup=back_cabinet_kb())
    except Exception as e:
        logger.error(f"Link creation failed: {e}")
        await callback.message.edit_text(texts.GENERIC_ERROR, reply_markup=back_cabinet_kb())


async def _finish_link_creation(bot: Bot, owner_id: int, data: dict) -> str:
    channel_id: int = data["channel_id"]
    channel_username: Optional[str] = data.get("channel_username")
    channel_title: str = data.get("channel_title", str(channel_id))
    payment_methods: list[str] = data["payment_methods"]
    link_expire_days: int = data["link_expire_days"]
    membership_days: int = data["membership_days"]
    max_members: Optional[int] = data.get("max_members")
    require_key: bool = data.get("require_key", False)
    payment_gate: bool = data.get("payment_gate", False)

    await q.get_or_create_channel(owner_id, channel_id, channel_username, channel_title)

    link_expires_at: Optional[datetime] = None
    if link_expire_days > 0:
        link_expires_at = datetime.utcnow() + timedelta(days=link_expire_days)

    # Если включён платёжный шлюз — ссылка с подтверждением заявки
    tg_link_obj = await bot.create_chat_invite_link(
        chat_id=channel_id,
        expire_date=link_expires_at,
        member_limit=max_members,
        creates_join_request=payment_gate or require_key,
    )
    invite_link = tg_link_obj.invite_link

    link_record = await q.create_invite_link(
        channel_id=channel_id, owner_id=owner_id, invite_link=invite_link,
        payment_methods=payment_methods, link_expires_at=link_expires_at,
        membership_duration_days=membership_days, max_members=max_members,
        require_key=require_key, payment_gate=payment_gate,
    )

    link_expires_str = (
        link_expires_at.strftime("%d.%m.%Y") if link_expires_at else texts.LB_SUCCESS_UNLIMITED_LINK
    )
    max_members_str = str(max_members) if max_members else texts.LB_SUCCESS_UNLIMITED_MEMBERS
    require_key_str = texts.LB_REQUIRE_KEY_YES if require_key else texts.LB_REQUIRE_KEY_NO
    gate_str = "✅ включён" if payment_gate else "❌ выключен"

    return (
        texts.LB_SUCCESS.format(
            invite_link=invite_link,
            payment_methods=", ".join(payment_methods),
            link_expires=link_expires_str,
            max_members=max_members_str,
            membership_days=membership_days,
            require_key=require_key_str,
        )
        + f"\n💳 <b>Платёжный шлюз:</b> {gate_str}"
    )


# ── helpers ───────────────────────────────────────────────────────────────────

async def _resolve_channel(bot: Bot, raw: str):
    try:
        if raw.lstrip("-").isdigit():
            chat = await bot.get_chat(int(raw))
        else:
            chat = await bot.get_chat(raw if raw.startswith("@") else f"@{raw}")
        return chat.id, chat.username, chat.title or chat.full_name or str(chat.id)
    except Exception as e:
        logger.warning(f"Cannot resolve channel '{raw}': {e}")
        return None


async def _bot_is_admin(bot: Bot, channel_id: int) -> bool:
    try:
        bot_info = await bot.get_me()
        member = await bot.get_chat_member(channel_id, bot_info.id)
        return member.status in ("administrator", "creator")
    except Exception as e:
        logger.warning(f"Admin check failed for channel {channel_id}: {e}")
        return False


# ── CANCEL ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel_fsm")
async def cancel_fsm(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer(texts.CANCELLED, show_alert=False)
    from bot.handlers.cabinet import show_cabinet
    await show_cabinet(callback, callback.from_user.id)
