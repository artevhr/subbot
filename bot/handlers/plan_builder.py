"""
FSM для создания плана подписки (4 шага).
Владелец получает bot-ссылку t.me/bot?start=join_<plan_id>
"""
import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.db import queries as q
from bot import texts
from bot.keyboards import membership_duration_kb, require_key_kb, back_cabinet_kb

logger = logging.getLogger(__name__)
router = Router()


class PlanBuilderState(StatesGroup):
    step1_channel = State()
    step2_title = State()
    step3_duration = State()
    step3_custom = State()
    step4_require_key = State()


@router.callback_query(F.data == "create_plan")
async def create_plan_start(callback: CallbackQuery, state: FSMContext):
    if not await q.is_key_valid_for_user(callback.from_user.id):
        await callback.answer(texts.NO_ACCESS, show_alert=True)
        return
    await state.set_state(PlanBuilderState.step1_channel)
    await callback.message.edit_text(texts.PB_STEP1, parse_mode="HTML")
    await callback.answer()


@router.message(PlanBuilderState.step1_channel)
async def step1_channel(message: Message, state: FSMContext, bot: Bot):
    raw = message.text.strip()
    info = await _resolve_channel(bot, raw)
    if not info:
        await message.answer(texts.PB_CHANNEL_NOT_FOUND, parse_mode="HTML")
        return
    channel_id, channel_username, channel_title = info
    if not await _bot_is_admin(bot, channel_id):
        await message.answer(texts.PB_NOT_ADMIN.format(channel=channel_title), parse_mode="HTML")
        return
    await state.update_data(
        channel_id=channel_id,
        channel_username=channel_username,
        channel_title=channel_title,
    )
    await state.set_state(PlanBuilderState.step2_title)
    await message.answer(texts.PB_STEP2, parse_mode="HTML")


@router.message(PlanBuilderState.step2_title)
async def step2_title(message: Message, state: FSMContext):
    await state.update_data(plan_title=message.text.strip())
    await state.set_state(PlanBuilderState.step3_duration)
    await message.answer(texts.PB_STEP3, reply_markup=membership_duration_kb(), parse_mode="HTML")


@router.callback_query(PlanBuilderState.step3_duration, F.data.startswith("membership:"))
async def step3_duration(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":")[1]
    if value == "custom":
        await state.set_state(PlanBuilderState.step3_custom)
        await callback.message.edit_text("Введи количество дней:", parse_mode="HTML")
    else:
        await state.update_data(membership_days=int(value))
        await state.set_state(PlanBuilderState.step4_require_key)
        await callback.message.edit_text(texts.PB_STEP4, reply_markup=require_key_kb(), parse_mode="HTML")
    await callback.answer()


@router.message(PlanBuilderState.step3_custom)
async def step3_custom(message: Message, state: FSMContext):
    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.INVALID_NUMBER)
        return
    await state.update_data(membership_days=days)
    await state.set_state(PlanBuilderState.step4_require_key)
    await message.answer(texts.PB_STEP4, reply_markup=require_key_kb(), parse_mode="HTML")


@router.callback_query(PlanBuilderState.step4_require_key, F.data.startswith("require_key:"))
async def step4_require_key(callback: CallbackQuery, state: FSMContext, bot: Bot):
    require_key = callback.data.split(":")[1] == "yes"
    data = await state.get_data()
    await state.clear()

    channel_id: int = data["channel_id"]
    channel_title: str = data["channel_title"]
    channel_username = data.get("channel_username")
    plan_title: str = data["plan_title"]
    membership_days: int = data["membership_days"]

    # Сохраняем канал
    await q.get_or_create_channel(callback.from_user.id, channel_id, channel_username, channel_title)

    # Создаём план
    plan = await q.create_plan(
        channel_id=channel_id,
        owner_id=callback.from_user.id,
        title=plan_title,
        payment_methods_text="не настроено",
        membership_duration_days=membership_days,
        require_key=require_key,
    )

    # Формируем bot-ссылку
    bot_info = await bot.get_me()
    bot_link = f"https://t.me/{bot_info.username}?start=join_{plan['id']}"

    await callback.message.edit_text(
        texts.PB_SUCCESS.format(
            title=plan_title,
            channel=channel_title,
            days=membership_days,
            payment_info=texts.PB_PAYMENT_NOT_CONFIGURED,
            require_key=texts.PB_REQUIRE_KEY_YES if require_key else texts.PB_REQUIRE_KEY_NO,
            bot_link=bot_link,
        ),
        reply_markup=back_cabinet_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_fsm")
async def cancel_fsm(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer(texts.CANCELLED, show_alert=False)
    from bot.handlers.cabinet import show_cabinet
    await show_cabinet(callback, callback.from_user.id)


async def _resolve_channel(bot: Bot, raw: str):
    try:
        chat = await bot.get_chat(int(raw) if raw.lstrip("-").isdigit() else (
            raw if raw.startswith("@") else f"@{raw}"
        ))
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
        logger.warning(f"Admin check failed for {channel_id}: {e}")
        return False
