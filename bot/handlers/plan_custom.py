"""handlers/plan_custom.py — кастомные тексты приветствия и после оплаты."""
import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.db import queries as q
from bot import texts
from bot.keyboards import plan_custom_texts_kb, plan_select_kb, back_cabinet_kb

logger = logging.getLogger(__name__)
router = Router()


class PlanCustomState(StatesGroup):
    choose_plan = State()
    edit_welcome = State()
    edit_success = State()


@router.callback_query(F.data == "plan_custom_texts")
async def plan_custom_start(callback: CallbackQuery, state: FSMContext):
    if not await q.is_key_valid_for_user(callback.from_user.id):
        await callback.answer(texts.NO_ACCESS, show_alert=True)
        return
    plans = await q.get_plans_by_owner(callback.from_user.id)
    if not plans:
        await callback.answer("Нет планов для настройки.", show_alert=True)
        return
    await state.set_state(PlanCustomState.choose_plan)
    await callback.message.edit_text(
        "✏️ Выбери план для настройки текстов:",
        reply_markup=plan_select_kb(plans),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(PlanCustomState.choose_plan, F.data.startswith("plan_sel:"))
async def plan_custom_chosen(callback: CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split(":")[1])
    plan = await q.get_plan(plan_id)
    if not plan:
        await callback.answer("План не найден.", show_alert=True)
        return
    await state.clear()
    await _show_custom_menu(callback.message, plan)
    await callback.answer()


@router.callback_query(F.data.startswith("pct_welcome:"))
async def edit_welcome_start(callback: CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split(":")[1])
    await state.set_state(PlanCustomState.edit_welcome)
    await state.update_data(edit_plan_id=plan_id)
    await callback.message.edit_text(texts.PLAN_CUSTOM_WELCOME_PROMPT, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("pct_success:"))
async def edit_success_start(callback: CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split(":")[1])
    await state.set_state(PlanCustomState.edit_success)
    await state.update_data(edit_plan_id=plan_id)
    await callback.message.edit_text(texts.PLAN_CUSTOM_SUCCESS_PROMPT, parse_mode="HTML")
    await callback.answer()


@router.message(PlanCustomState.edit_welcome)
async def save_welcome(message: Message, state: FSMContext):
    data = await state.get_data()
    plan_id = data["edit_plan_id"]
    plan = await q.get_plan(plan_id)
    new_text = None if message.text.strip() == "-" else message.text.strip()
    await q.update_plan_texts(plan_id, new_text, plan.get("success_text"))
    await state.clear()
    plan = await q.get_plan(plan_id)
    await message.answer(texts.PLAN_CUSTOM_SAVED, parse_mode="HTML")
    await _show_custom_menu(message, plan)


@router.message(PlanCustomState.edit_success)
async def save_success(message: Message, state: FSMContext):
    data = await state.get_data()
    plan_id = data["edit_plan_id"]
    plan = await q.get_plan(plan_id)
    new_text = None if message.text.strip() == "-" else message.text.strip()
    await q.update_plan_texts(plan_id, plan.get("welcome_text"), new_text)
    await state.clear()
    plan = await q.get_plan(plan_id)
    await message.answer(texts.PLAN_CUSTOM_SAVED, parse_mode="HTML")
    await _show_custom_menu(message, plan)


async def _show_custom_menu(msg, plan: dict):
    welcome = plan.get("welcome_text") or "<i>стандартное</i>"
    success = plan.get("success_text") or "<i>стандартное</i>"
    # Обрезаем для превью
    if len(welcome) > 80:
        welcome = welcome[:80] + "..."
    if len(success) > 80:
        success = success[:80] + "..."
    text = texts.PLAN_CUSTOM_TEXTS_MENU.format(
        plan_title=plan["title"],
        welcome=welcome,
        success=success,
    )
    await msg.answer(
        text,
        reply_markup=plan_custom_texts_kb(plan["id"]),
        parse_mode="HTML",
    )
