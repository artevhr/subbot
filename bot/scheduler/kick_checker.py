import logging
from datetime import datetime
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot.db import queries as q
from bot import texts

logger = logging.getLogger(__name__)


async def check_expired_subscriptions(bot: Bot):
    """Каждые 10 минут: кик участников с истёкшей подпиской."""
    expired = await q.get_expired_subscriptions()
    if not expired:
        return
    logger.info(f"Processing {len(expired)} expired subscriptions...")

    for sub in expired:
        user_id = sub["user_id"]
        channel_id = sub["channel_id"]
        channel_title = sub.get("channel_title", str(channel_id))
        owner_id = sub["owner_id"]
        username = sub.get("username") or str(user_id)

        try:
            await bot.ban_chat_member(chat_id=channel_id, user_id=user_id)
            await bot.unban_chat_member(chat_id=channel_id, user_id=user_id, only_if_banned=True)
            logger.info(f"Kicked {user_id} from {channel_id}")
        except Exception as e:
            logger.error(texts.KICK_ERROR.format(user_id=user_id, channel_id=channel_id, error=e))

        await q.deactivate_subscription(sub["id"])

        for uid, tmpl, kwargs in [
            (user_id,  texts.SUB_EXPIRED_USER,  {"channel_title": channel_title}),
            (owner_id, texts.SUB_EXPIRED_OWNER, {
                "username": f"@{username}" if not username.startswith("@") else username,
                "user_id": user_id,
                "channel_title": channel_title,
            }),
        ]:
            try:
                await bot.send_message(uid, tmpl.format(**kwargs), parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Notify {uid} failed: {e}")


async def check_expiry_reminders(bot: Bot):
    """Каждые 6 часов: предупреждение за 3 дня до конца подписки."""
    expiring = await q.get_expiring_soon_subscriptions(days_before=3)
    for sub in expiring:
        try:
            expires_dt = datetime.strptime(sub["expires_at"], "%Y-%m-%d %H:%M:%S")
            await bot.send_message(
                sub["user_id"],
                texts.SUB_EXPIRY_REMINDER.format(
                    channel_title=sub.get("channel_title", "—"),
                    expires_date=expires_dt.strftime("%d.%m.%Y"),
                ),
                parse_mode="HTML",
            )
            await q.mark_subscription_reminded(sub["id"])
        except Exception as e:
            logger.warning(f"Reminder to {sub['user_id']} failed: {e}")


async def check_expired_keys():
    """Каждый час: деактивация просроченных ключей."""
    await q.deactivate_expired_user_keys()
    logger.info("Expired keys deactivated")


async def check_pending_payments(bot: Bot):
    """Каждые 5 минут: автопроверка pending платежей."""
    from bot.utils import cryptobot as cb
    from bot.utils import yukassa as yk

    pending = await q.get_pending_payments_all()
    if not pending:
        return

    for payment in pending:
        plan = await q.get_plan(payment["plan_id"])
        if not plan:
            continue

        paid = False
        try:
            if payment["payment_system"] == "cryptobot" and plan.get("cryptobot_token"):
                inv = await cb.get_invoice(plan["cryptobot_token"], int(payment["external_id"]))
                paid = bool(inv and inv.get("status") == "paid")
            elif payment["payment_system"] == "yukassa" and plan.get("yukassa_shop_id"):
                status = await yk.check_payment(
                    plan["yukassa_shop_id"], plan["yukassa_secret_key"], payment["external_id"]
                )
                paid = status == "succeeded"
        except Exception as e:
            logger.warning(f"Payment check {payment['external_id']}: {e}")
            continue

        if paid:
            await q.mark_payment_paid(payment["external_id"])
            ch = await q.get_channel_by_id(payment["channel_id"])
            channel_title = ch.get("channel_title", str(payment["channel_id"])) if ch else ""
            # Генерируем одноразовую ссылку
            from bot.handlers.user_payment import _grant_access
            class _FakeMsg:
                async def answer(self, text, **kw):
                    await bot.send_message(payment["user_id"], text, **kw)
                chat = None
            await _grant_access(bot, _FakeMsg(), payment["user_id"], plan, channel_title)
            logger.info(f"Auto-confirmed payment {payment['external_id']}")


async def check_renewal_offers(bot: Bot):
    """
    Каждый час: за 24 часа до кика отправляет клиенту
    предложение продлить подписку с кнопкой оплаты прямо в сообщении.
    """
    from bot.keyboards import renewal_kb
    expiring = await q.get_subscriptions_expiring_in(hours=24)
    if not expiring:
        return
    logger.info(f"Sending {len(expiring)} renewal offers...")

    for sub in expiring:
        try:
            from datetime import datetime as _dt
            expires_dt = _dt.strptime(sub["expires_at"], "%Y-%m-%d %H:%M:%S")
            await bot.send_message(
                sub["user_id"],
                texts.RENEWAL_OFFER.format(
                    channel=sub.get("channel_title", "—"),
                    expires=expires_dt.strftime("%d.%m.%Y %H:%M"),
                ),
                reply_markup=renewal_kb(sub["plan_id_val"]),
                parse_mode="HTML",
            )
            await q.mark_subscription_reminded(sub["id"])
        except Exception as e:
            logger.warning(f"Renewal offer to {sub['user_id']} failed: {e}")
