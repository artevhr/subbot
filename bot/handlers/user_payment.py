"""
Флоу для клиента канала:
1. Клиент переходит по t.me/bot?start=join_<plan_id>
2. Видит план и способы оплаты
3. Платит (CryptoBot / YooKassa) или вводит ключ
4. Бот генерирует ОДНОРАЗОВУЮ ссылку (member_limit=1) → отправляет клиенту
5. Клиент заходит в канал → бот создаёт подписку → через N дней кик
"""
import logging
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.db import queries as q
from bot import texts
from bot.keyboards import pay_method_kb, pay_invoice_kb, back_cabinet_kb
from bot.utils import cryptobot as cb
from bot.utils import yukassa as yk

logger = logging.getLogger(__name__)
router = Router()


class UserPayState(StatesGroup):
    choose_method = State()
    enter_key = State()
    waiting_check = State()


async def start_purchase_flow(message: Message, plan_id: int, state: FSMContext):
    """Вызывается из start.py при deeplink join_<plan_id>."""
    plan = await q.get_plan(plan_id)
    if not plan:
        await message.answer("❌ Этот план подписки недоступен или был удалён.", parse_mode="HTML")
        return

    ch = await q.get_channel_by_id(plan["channel_id"])
    channel_title = ch.get("channel_title", str(plan["channel_id"])) if ch else str(plan["channel_id"])

    user_id = message.from_user.id

    # Проверка чёрного списка
    ch = await q.get_channel_by_id(plan["channel_id"])
    if ch:
        is_banned = await q.is_blacklisted(ch["owner_id"], user_id)
        if is_banned:
            await message.answer(texts.BL_BANNED, parse_mode="HTML")
            return

    # Уже есть активная подписка?
    from bot.db.models import DB_PATH
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscriptions WHERE user_id=? AND channel_id=? AND is_active=1 "
            "ORDER BY id DESC LIMIT 1",
            (user_id, plan["channel_id"]),
        ) as cur:
            existing = await cur.fetchone()

    if existing:
        existing = dict(existing)
        expires_dt = datetime.strptime(existing["expires_at"], "%Y-%m-%d %H:%M:%S")
        await message.answer(
            texts.PAY_USER_ALREADY_SUBSCRIBED.format(
                expires=expires_dt.strftime("%d.%m.%Y")
            ),
            parse_mode="HTML",
        )
        return

    mode = plan.get("payment_mode", "manual")
    has_crypto = mode in ("cryptobot", "both") and plan.get("cryptobot_token")
    has_yukassa = mode in ("yukassa", "both") and plan.get("yukassa_shop_id")
    require_key = bool(plan.get("require_key"))
    has_any_payment = has_crypto or has_yukassa

    await state.set_state(UserPayState.choose_method)
    await state.update_data(plan_id=plan_id, plan=dict(plan), channel_title=channel_title)

    if not has_any_payment and not require_key:
        # Оплата не настроена и ключ не требуется → показываем инфо
        await message.answer(
            texts.PAY_USER_NO_PAYMENT.format(
                plan_title=plan["title"],
                channel=channel_title,
                days=plan["membership_duration_days"],
                payment_methods=plan.get("payment_methods_text", "уточните у владельца"),
            ),
            parse_mode="HTML",
        )
        return

    welcome_text = plan.get("welcome_text") or texts.PAY_USER_WELCOME.format(
        plan_title=plan["title"],
        channel=channel_title,
        days=plan["membership_duration_days"],
    )
    await message.answer(
        welcome_text,
        reply_markup=pay_method_kb(has_crypto, has_yukassa, require_key),
        parse_mode="HTML",
    )


# ── Выбор метода ──────────────────────────────────────────────────────────────

@router.callback_query(UserPayState.choose_method, F.data.startswith("pay_with:"))
async def pay_method_chosen(callback: CallbackQuery, state: FSMContext, bot: Bot):
    method = callback.data.split(":")[1]
    data = await state.get_data()
    plan: dict = data["plan"]
    channel_title: str = data["channel_title"]
    user_id = callback.from_user.id

    await callback.answer()

    if method == "key":
        await state.set_state(UserPayState.enter_key)
        await callback.message.edit_text(
            texts.PAY_USER_KEY_PROMPT.format(channel=channel_title),
            parse_mode="HTML",
        )
        return

    if method == "cryptobot":
        invoice = await cb.create_invoice(
            token=plan["cryptobot_token"],
            asset=plan["cryptobot_asset"],
            amount=plan["cryptobot_amount"],
            description=f"{plan['title']} — {channel_title}",
            payload=f"{user_id}:{plan['id']}",
        )
        if not invoice:
            await callback.message.edit_text(texts.GENERIC_ERROR, parse_mode="HTML")
            await state.clear()
            return

        external_id = str(invoice["invoice_id"])
        pay_url = invoice.get("bot_invoice_url") or invoice.get("pay_url", "")

        await q.create_payment(
            user_id, plan["channel_id"], plan["id"],
            plan["cryptobot_amount"], plan["cryptobot_asset"],
            "cryptobot", external_id,
        )
        await state.update_data(external_id=external_id, pay_system="cryptobot", pay_url=pay_url)
        await state.set_state(UserPayState.waiting_check)
        await callback.message.edit_text(
            texts.PAY_USER_CB_INVOICE.format(
                amount=plan["cryptobot_amount"], asset=plan["cryptobot_asset"]
            ),
            reply_markup=pay_invoice_kb(pay_url, external_id, "cryptobot"),
            parse_mode="HTML",
        )

    elif method == "yukassa":
        payment = await yk.create_payment(
            shop_id=plan["yukassa_shop_id"],
            secret_key=plan["yukassa_secret_key"],
            amount=plan["yukassa_amount"],
            currency=plan.get("yukassa_currency", "RUB"),
            description=f"{plan['title']} — {channel_title}",
        )
        if not payment:
            await callback.message.edit_text(texts.GENERIC_ERROR, parse_mode="HTML")
            await state.clear()
            return

        external_id = payment["id"]
        pay_url = payment["url"]

        await q.create_payment(
            user_id, plan["channel_id"], plan["id"],
            plan["yukassa_amount"], plan.get("yukassa_currency", "RUB"),
            "yukassa", external_id,
        )
        await state.update_data(external_id=external_id, pay_system="yukassa", pay_url=pay_url)
        await state.set_state(UserPayState.waiting_check)
        await callback.message.edit_text(
            texts.PAY_USER_YK_INVOICE.format(amount=plan["yukassa_amount"]),
            reply_markup=pay_invoice_kb(pay_url, external_id, "yukassa"),
            parse_mode="HTML",
        )


# ── Ввод ключа ────────────────────────────────────────────────────────────────

@router.message(UserPayState.enter_key)
async def process_key(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    plan: dict = data["plan"]
    key_code = message.text.strip().upper()
    key = await q.get_key(key_code)

    if not key:
        await message.answer(texts.PAY_USER_KEY_INVALID, parse_mode="HTML")
        return

    await q.activate_key_for_user(message.from_user.id, key_code, key["duration_days"])
    await state.clear()
    await _grant_access(bot, message, message.from_user.id, plan, data["channel_title"])


# ── Проверка оплаты ───────────────────────────────────────────────────────────

@router.callback_query(UserPayState.waiting_check, F.data.startswith("pay_check:"))
async def pay_check(callback: CallbackQuery, state: FSMContext, bot: Bot):
    _, system, external_id = callback.data.split(":", 2)
    data = await state.get_data()
    plan: dict = data["plan"]
    await callback.answer("Проверяю оплату...")

    paid = await _verify_payment(system, external_id, plan)
    if not paid:
        await callback.message.edit_text(
            texts.PAY_USER_NOT_PAID,
            reply_markup=pay_invoice_kb(
                data.get("pay_url", "https://t.me/"),
                external_id, system,
            ),
            parse_mode="HTML",
        )
        return

    await q.mark_payment_paid(external_id)
    await state.clear()
    await _grant_access(bot, callback.message, callback.from_user.id, plan, data["channel_title"])


@router.callback_query(F.data == "pay_cancel")
async def pay_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(texts.CANCELLED, parse_mode="HTML")
    await callback.answer()


# ── Выдача доступа ────────────────────────────────────────────────────────────

async def _grant_access(bot: Bot, msg, user_id: int, plan: dict, channel_title: str):
    """
    Генерирует одноразовую invite-ссылку (member_limit=1, expire +24ч),
    отправляет пользователю, создаёт запись подписки.
    """
    channel_id = plan["channel_id"]
    duration_days = plan["membership_duration_days"]

    # Одноразовая ссылка — действует 24 часа, только 1 человек
    expire_date = datetime.utcnow() + timedelta(hours=24)
    try:
        link_obj = await bot.create_chat_invite_link(
            chat_id=channel_id,
            expire_date=expire_date,
            member_limit=1,
            name=f"sub_{user_id}",
        )
        one_time_link = link_obj.invite_link
    except Exception as e:
        logger.error(f"Cannot create invite link for channel {channel_id}: {e}")
        await msg.answer(
            "❌ Не удалось создать ссылку. Обратись в поддержку.",
            parse_mode="HTML",
        )
        return

    # Создаём подписку
    sub = await q.create_subscription(user_id, channel_id, plan["id"], duration_days)

    expires_dt = datetime.strptime(sub["expires_at"], "%Y-%m-%d %H:%M:%S")

    success_text = plan.get("success_text") or ""
    success_suffix = f"\n\n{success_text}" if success_text else ""
    await msg.answer(
        texts.PAY_USER_SUCCESS.format(
            channel=channel_title,
            invite_link=one_time_link,
            expires=expires_dt.strftime("%d.%m.%Y"),
        ) + success_suffix,
        parse_mode="HTML",
    )

    # Уведомляем владельца канала
    try:
        ch = await q.get_channel_by_id(channel_id)
        if ch:
            uname = f"@{msg.chat.username}" if hasattr(msg, "chat") and getattr(msg.chat, "username", None) else str(user_id)
            await bot.send_message(
                ch["owner_id"],
                f"✅ <b>Новый подписчик!</b>\n\n"
                f"👤 {uname}\n"
                f"📋 План: <b>{plan['title']}</b>\n"
                f"📅 Подписка до: <b>{expires_dt.strftime('%d.%m.%Y')}</b>",
                parse_mode="HTML",
            )
    except Exception as e:
        logger.warning(f"Cannot notify owner: {e}")

    # Кредитуем реферера
    user = await q.get_user(user_id)
    if user and user.get("referred_by"):
        try:
            await q.credit_pending_referrals(user["referred_by"])
            await bot.send_message(
                user["referred_by"],
                texts.REFERRAL_CREDITED.format(days=7),
                parse_mode="HTML",
            )
        except Exception:
            pass


async def _verify_payment(system: str, external_id: str, plan: dict) -> bool:
    if system == "cryptobot":
        invoice = await cb.get_invoice(plan["cryptobot_token"], int(external_id))
        return bool(invoice and invoice.get("status") == "paid")
    elif system == "yukassa":
        status = await yk.check_payment(
            plan["yukassa_shop_id"], plan["yukassa_secret_key"], external_id
        )
        return status == "succeeded"
    return False


# ── Обработчик кнопки «Продлить подписку» из авторемайндера ──────────────────

@router.callback_query(F.data.startswith("renew:"))
async def renewal_button(callback: CallbackQuery, state: FSMContext):
    """Клиент нажал «Продлить» в сообщении-напоминании."""
    plan_id = int(callback.data.split(":")[1])
    await callback.answer()
    # Повторно запускаем флоу покупки — он сам покажет варианты оплаты
    await start_purchase_flow(callback.message, plan_id, state)
