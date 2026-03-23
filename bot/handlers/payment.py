"""
FSM настройки оплаты для владельца канала.
Привязывает CryptoBot / YooKassa к конкретному плану подписки.
"""
import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.db import queries as q
from bot import texts
from bot.keyboards import plan_select_kb, pay_mode_kb, crypto_asset_kb, back_cabinet_kb
from bot.utils import cryptobot as cb

logger = logging.getLogger(__name__)
router = Router()


class PaySetupState(StatesGroup):
    choose_plan = State()
    choose_mode = State()
    cb_token = State()
    cb_asset = State()
    cb_amount = State()
    yk_shop_id = State()
    yk_secret = State()
    yk_amount = State()
    both_cb_token = State()
    both_cb_asset = State()
    both_cb_amount = State()
    both_yk_shop_id = State()
    both_yk_secret = State()
    both_yk_amount = State()


@router.callback_query(F.data == "pay_setup")
async def pay_setup_start(callback: CallbackQuery, state: FSMContext):
    if not await q.is_key_valid_for_user(callback.from_user.id):
        await callback.answer(texts.NO_ACCESS, show_alert=True)
        return
    plans = await q.get_plans_by_owner(callback.from_user.id)
    if not plans:
        await callback.answer(texts.PAY_SETUP_NO_PLANS, show_alert=True)
        return
    await state.set_state(PaySetupState.choose_plan)
    await callback.message.edit_text(
        texts.PAY_SETUP_CHOOSE_PLAN,
        reply_markup=plan_select_kb(plans),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(PaySetupState.choose_plan, F.data.startswith("plan_sel:"))
async def plan_chosen(callback: CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split(":")[1])
    plan = await q.get_plan(plan_id)
    if not plan:
        await callback.answer("План не найден.", show_alert=True)
        return
    await state.update_data(setup_plan_id=plan_id, setup_plan_title=plan["title"])
    await state.set_state(PaySetupState.choose_mode)
    await callback.message.edit_text(
        texts.PAY_SETUP_CHOOSE_MODE.format(plan_title=plan["title"]),
        reply_markup=pay_mode_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(PaySetupState.choose_mode, F.data.startswith("pmode:"))
async def mode_chosen(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.split(":")[1]
    await state.update_data(setup_mode=mode)
    if mode == "cryptobot":
        await state.set_state(PaySetupState.cb_token)
        await callback.message.edit_text(texts.PAY_SETUP_CB_TOKEN, parse_mode="HTML")
    elif mode == "yukassa":
        await state.set_state(PaySetupState.yk_shop_id)
        await callback.message.edit_text(texts.PAY_SETUP_YK_SHOP, parse_mode="HTML")
    else:
        await state.set_state(PaySetupState.both_cb_token)
        await callback.message.edit_text(
            "🔀 <b>Оба способа</b>\n\nСначала настроим CryptoBot.\n\n" + texts.PAY_SETUP_CB_TOKEN,
            parse_mode="HTML",
        )
    await callback.answer()


# ── CryptoBot ─────────────────────────────────────────────────────────────────

@router.message(PaySetupState.cb_token)
async def cb_token(message: Message, state: FSMContext):
    token = message.text.strip()
    if not await cb.check_token(token):
        await message.answer(texts.PAY_SETUP_CB_TOKEN_INVALID)
        return
    await state.update_data(cb_token=token)
    await state.set_state(PaySetupState.cb_asset)
    await message.answer(texts.PAY_SETUP_CB_ASSET, reply_markup=crypto_asset_kb(), parse_mode="HTML")


@router.callback_query(PaySetupState.cb_asset, F.data.startswith("asset:"))
async def cb_asset(callback: CallbackQuery, state: FSMContext):
    asset = callback.data.split(":")[1]
    await state.update_data(cb_asset=asset)
    await state.set_state(PaySetupState.cb_amount)
    await callback.message.edit_text(
        texts.PAY_SETUP_CB_AMOUNT.format(asset=asset), parse_mode="HTML"
    )
    await callback.answer()


@router.message(PaySetupState.cb_amount)
async def cb_amount(message: Message, state: FSMContext):
    amount = _parse_amount(message.text)
    if amount is None:
        await message.answer(texts.PAY_SETUP_INVALID_AMOUNT, parse_mode="HTML")
        return
    data = await state.get_data()
    await state.clear()
    await q.update_plan_payment(
        data["setup_plan_id"], "cryptobot",
        cryptobot_token=data["cb_token"],
        cryptobot_asset=data["cb_asset"],
        cryptobot_amount=amount,
    )
    await message.answer(
        texts.PAY_SETUP_SAVED.format(
            mode="CryptoBot",
            details=texts.PAY_SETUP_CB_DETAILS.format(asset=data["cb_asset"], amount=amount),
        ),
        parse_mode="HTML", reply_markup=back_cabinet_kb(),
    )


# ── YooKassa ──────────────────────────────────────────────────────────────────

@router.message(PaySetupState.yk_shop_id)
async def yk_shop(message: Message, state: FSMContext):
    await state.update_data(yk_shop_id=message.text.strip())
    await state.set_state(PaySetupState.yk_secret)
    await message.answer(texts.PAY_SETUP_YK_SECRET, parse_mode="HTML")


@router.message(PaySetupState.yk_secret)
async def yk_secret(message: Message, state: FSMContext):
    await state.update_data(yk_secret=message.text.strip())
    await state.set_state(PaySetupState.yk_amount)
    await message.answer(texts.PAY_SETUP_YK_AMOUNT, parse_mode="HTML")


@router.message(PaySetupState.yk_amount)
async def yk_amount(message: Message, state: FSMContext):
    amount = _parse_amount(message.text)
    if amount is None:
        await message.answer(texts.PAY_SETUP_INVALID_AMOUNT, parse_mode="HTML")
        return
    data = await state.get_data()
    await state.clear()
    await q.update_plan_payment(
        data["setup_plan_id"], "yukassa",
        yukassa_shop_id=data["yk_shop_id"],
        yukassa_secret_key=data["yk_secret"],
        yukassa_amount=amount,
    )
    await message.answer(
        texts.PAY_SETUP_SAVED.format(
            mode="ЮKassa",
            details=texts.PAY_SETUP_YK_DETAILS.format(amount=amount),
        ),
        parse_mode="HTML", reply_markup=back_cabinet_kb(),
    )


# ── Both: CB part ─────────────────────────────────────────────────────────────

@router.message(PaySetupState.both_cb_token)
async def both_cb_token(message: Message, state: FSMContext):
    token = message.text.strip()
    if not await cb.check_token(token):
        await message.answer(texts.PAY_SETUP_CB_TOKEN_INVALID)
        return
    await state.update_data(cb_token=token)
    await state.set_state(PaySetupState.both_cb_asset)
    await message.answer(texts.PAY_SETUP_CB_ASSET, reply_markup=crypto_asset_kb(), parse_mode="HTML")


@router.callback_query(PaySetupState.both_cb_asset, F.data.startswith("asset:"))
async def both_cb_asset(callback: CallbackQuery, state: FSMContext):
    await state.update_data(cb_asset=callback.data.split(":")[1])
    await state.set_state(PaySetupState.both_cb_amount)
    await callback.message.edit_text(
        texts.PAY_SETUP_CB_AMOUNT.format(asset=callback.data.split(":")[1]), parse_mode="HTML"
    )
    await callback.answer()


@router.message(PaySetupState.both_cb_amount)
async def both_cb_amount(message: Message, state: FSMContext):
    amount = _parse_amount(message.text)
    if amount is None:
        await message.answer(texts.PAY_SETUP_INVALID_AMOUNT, parse_mode="HTML")
        return
    await state.update_data(cb_amount=amount)
    await state.set_state(PaySetupState.both_yk_shop_id)
    await message.answer(
        "✅ CryptoBot настроен!\n\nТеперь ЮKassa.\n\n" + texts.PAY_SETUP_YK_SHOP,
        parse_mode="HTML",
    )


@router.message(PaySetupState.both_yk_shop_id)
async def both_yk_shop(message: Message, state: FSMContext):
    await state.update_data(yk_shop_id=message.text.strip())
    await state.set_state(PaySetupState.both_yk_secret)
    await message.answer(texts.PAY_SETUP_YK_SECRET, parse_mode="HTML")


@router.message(PaySetupState.both_yk_secret)
async def both_yk_secret(message: Message, state: FSMContext):
    await state.update_data(yk_secret=message.text.strip())
    await state.set_state(PaySetupState.both_yk_amount)
    await message.answer(texts.PAY_SETUP_YK_AMOUNT, parse_mode="HTML")


@router.message(PaySetupState.both_yk_amount)
async def both_yk_amount(message: Message, state: FSMContext):
    amount = _parse_amount(message.text)
    if amount is None:
        await message.answer(texts.PAY_SETUP_INVALID_AMOUNT, parse_mode="HTML")
        return
    data = await state.get_data()
    await state.clear()
    await q.update_plan_payment(
        data["setup_plan_id"], "both",
        cryptobot_token=data["cb_token"],
        cryptobot_asset=data["cb_asset"],
        cryptobot_amount=data["cb_amount"],
        yukassa_shop_id=data["yk_shop_id"],
        yukassa_secret_key=data["yk_secret"],
        yukassa_amount=amount,
    )
    await message.answer(
        texts.PAY_SETUP_SAVED.format(
            mode="CryptoBot + ЮKassa",
            details=(
                texts.PAY_SETUP_CB_DETAILS.format(asset=data["cb_asset"], amount=data["cb_amount"])
                + texts.PAY_SETUP_YK_DETAILS.format(amount=amount)
            ),
        ),
        parse_mode="HTML", reply_markup=back_cabinet_kb(),
    )


def _parse_amount(text: str):
    try:
        v = float(text.strip().replace(",", "."))
        return v if v > 0 else None
    except ValueError:
        return None
