import logging
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot.db import queries as q
from bot import texts
from bot.keyboards import main_menu_kb, back_cabinet_kb

logger = logging.getLogger(__name__)
router = Router()

REFERRAL_BONUS_DAYS = 7


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    user = message.from_user
    username = user.username or user.full_name

    is_new = (await q.get_user(user.id)) is None
    await q.get_or_create_user(user.id, username)
    await q.update_username(user.id, username)

    args = command.args or ""

    # ── Переход по ссылке плана: /start join_<plan_id> ────────────────────────
    if args.startswith("join_"):
        try:
            plan_id = int(args.replace("join_", ""))
        except ValueError:
            plan_id = None
        if plan_id:
            from bot.handlers.user_payment import start_purchase_flow
            await start_purchase_flow(message, plan_id, state)
            return

    # ── Реферальная ссылка: /start ref_<user_id> ─────────────────────────────
    ref_bonus_text = ""
    if args.startswith("ref_") and is_new:
        try:
            referrer_id = int(args.replace("ref_", ""))
            if referrer_id != user.id:
                await q.set_referred_by(user.id, referrer_id)
                ref = await q.create_referral(referrer_id, user.id, REFERRAL_BONUS_DAYS)
                if ref:
                    await q.add_bonus_days_to_user(user.id, REFERRAL_BONUS_DAYS)
                    ref_bonus_text = "\n\n" + texts.REFERRAL_WELCOME_BONUS.format(days=REFERRAL_BONUS_DAYS)
                    try:
                        await q.credit_pending_referrals(referrer_id)
                        await message.bot.send_message(
                            referrer_id,
                            texts.REFERRAL_CREDITED.format(days=REFERRAL_BONUS_DAYS),
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
            else:
                ref_bonus_text = "\n\n" + texts.REFERRAL_SELF
        except (ValueError, TypeError):
            pass

    await message.answer(
        texts.WELCOME.format(name=user.first_name) + ref_bonus_text,
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text(
        texts.WELCOME.format(name=callback.from_user.first_name),
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "referral_stats")
async def referral_stats(callback: CallbackQuery):
    stats = await q.get_referral_stats(callback.from_user.id)
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{callback.from_user.id}"
    await callback.message.edit_text(
        texts.REFERRAL_STATS.format(
            ref_link=ref_link,
            total=stats["total"],
            earned=stats["earned_days"],
            pending=stats["pending"],
            bonus_days=REFERRAL_BONUS_DAYS,
        ),
        reply_markup=back_cabinet_kb(),
        parse_mode="HTML",
    )
    await callback.answer()
