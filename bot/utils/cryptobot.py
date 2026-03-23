"""
Клиент для Crypto Pay API (t.me/CryptoBot).
Документация: https://help.crypt.bot/crypto-pay-api
"""
import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

CRYPTOBOT_API = "https://pay.crypt.bot/api/"
SUPPORTED_ASSETS = ["USDT", "TON", "BTC", "ETH", "LTC", "BNB", "TRX", "USDC"]


async def _request(token: str, method: str, payload: dict) -> Optional[dict]:
    headers = {"Crypto-Pay-API-Token": token}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                CRYPTOBOT_API + method,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    logger.error(f"CryptoBot error [{method}]: {data}")
                    return None
                return data.get("result")
    except Exception as e:
        logger.error(f"CryptoBot request failed [{method}]: {e}")
        return None


async def create_invoice(
    token: str,
    asset: str,
    amount: float,
    description: str,
    payload: str,
    expires_in: int = 3600,
) -> Optional[dict]:
    """
    Создаёт инвойс. Возвращает dict с полями:
    invoice_id, bot_invoice_url, status, amount, asset, payload
    """
    return await _request(token, "createInvoice", {
        "asset": asset,
        "amount": str(amount),
        "description": description,
        "payload": payload,
        "expires_in": expires_in,
        "allow_comments": False,
        "allow_anonymous": False,
    })


async def get_invoice(token: str, invoice_id: int) -> Optional[dict]:
    """Получает статус инвойса по ID. Статус: active / paid / expired / cancelled."""
    result = await _request(token, "getInvoices", {"invoice_ids": str(invoice_id)})
    if result and result.get("items"):
        return result["items"][0]
    return None


async def check_token(token: str) -> bool:
    """Проверяет валидность токена CryptoBot."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                CRYPTOBOT_API + "getMe",
                headers={"Crypto-Pay-API-Token": token},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json()
                return data.get("ok", False)
    except Exception:
        return False
