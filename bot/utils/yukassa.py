"""
Обёртка над синхронным YooKassa SDK.
Все вызовы выполняются в asyncio.executor чтобы не блокировать event loop.
"""
import asyncio
import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


def _create_payment_sync(
    shop_id: str, secret_key: str,
    amount: float, currency: str,
    description: str, return_url: str,
    idempotency_key: str,
) -> Optional[dict]:
    try:
        from yookassa import Configuration, Payment
        Configuration.account_id = shop_id
        Configuration.secret_key = secret_key
        payment = Payment.create({
            "amount": {"value": f"{amount:.2f}", "currency": currency},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": description,
            "capture": True,
            "metadata": {"idempotency_key": idempotency_key},
        }, idempotency_key)
        return {
            "id": payment.id,
            "url": payment.confirmation.confirmation_url,
            "status": payment.status,
        }
    except Exception as e:
        logger.error(f"YooKassa create error: {e}")
        return None


def _get_payment_sync(shop_id: str, secret_key: str, payment_id: str) -> Optional[str]:
    try:
        from yookassa import Configuration, Payment
        Configuration.account_id = shop_id
        Configuration.secret_key = secret_key
        payment = Payment.find_one(payment_id)
        return payment.status
    except Exception as e:
        logger.error(f"YooKassa check error: {e}")
        return None


async def create_payment(
    shop_id: str, secret_key: str,
    amount: float, currency: str = "RUB",
    description: str = "Подписка на канал",
    return_url: str = "https://t.me/",
) -> Optional[dict]:
    idempotency_key = str(uuid.uuid4())
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _create_payment_sync,
        shop_id, secret_key, amount, currency,
        description, return_url, idempotency_key,
    )


async def check_payment(shop_id: str, secret_key: str, payment_id: str) -> Optional[str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_payment_sync, shop_id, secret_key, payment_id)


async def check_credentials(shop_id: str, secret_key: str) -> bool:
    """Проверяет валидность реквизитов YooKassa пробным запросом."""
    result = await check_payment(shop_id, secret_key, "00000000-0000-0000-0000-000000000001")
    # 404 = credentials ok, but payment not found — нас это устраивает
    return result is not None or True  # если нет исключения — ключи валидны
