"""
handlers/pay_logs.py

Просмотр логов платежей для владельца канала.
Пагинация по 8 записей, фильтр по каналу.
"""
import logging
import math
from datetime import datetime

from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.db import queries as q
from bot import texts
from bot.keyboards import pay_log_nav_kb, pay_log_channel_filter_kb, back_cabinet_kb

logger = logging.getLogger(__name__)
router = Router()

PAGE_SIZE = 8


def _fmt_payment(p: dict) -> str:
    status = p.get("status", "")
    if status == "paid":
        icon = texts.PAY_LOG_STATUS_PAID
    elif status == "pending":
        icon = texts.PAY_LOG_STATUS_PENDING
    else:
        icon = texts.PAY_LOG_STATUS_OTHER

    username = p.get("buyer_username") or str(p["user_id"])
    if not username.startswith("@"):
        username = f"@{username}"

    # Форматируем дату создания
    try:
        dt = datetime.strptime(p["created_at"], "%Y-%m-%d %H:%M:%S")
        created_str = dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        created_str = p.get("created_at", "—")

    paid_line = ""
    if p.get("paid_at"):
        try:
            dt_paid = datetime.strptime(p["paid_at"], "%Y-%m-%d %H:%M:%S")
            paid_line = texts.PAY_LOG_PAID_LINE.format(
                paid_at=dt_paid.strftime("%d.%m.%Y %H:%M")
            )
        except Exception:
            paid_line = texts.PAY_LOG_PAID_LINE.format(paid_at=p["paid_at"])

    system_labels = {"cryptobot": "CryptoBot", "yukassa": "ЮKassa", "key": "Ключ"}
    system = system_labels.get(p.get("payment_system", ""), p.get("payment_system", "—"))

    return texts.PAY_LOG_ITEM.format(
        status_icon=icon,
        plan_title=p.get("plan_title", "—"),
        username=username,
        channel=p.get("channel_title", str(p.get("channel_id", "—"))),
        amount=p.get("amount", "—"),
        currency=p.get("currency", ""),
        system=system,
        created_at=created_str,
        paid_line=paid_line,
    )


async def _render_logs_page(
    owner_id: int,
    page: int,
    channel_id: int = 0,
) -> tuple[str, object]:
    """Возвращает (текст, клавиатура) для страницы логов."""
    total = await q.count_payments_by_owner(owner_id)

    if total == 0:
        return texts.PAY_LOG_EMPTY, back_cabinet_kb()

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(1, min(page, total_pages))
    offset = (page - 1) * PAGE_SIZE

    if channel_id:
        payments = await q.get_payments_by_owner_and_channel(
            owner_id, channel_id, limit=PAGE_SIZE, offset=offset
        )
    else:
        payments = await q.get_payments_by_owner(
            owner_id, limit=PAGE_SIZE, offset=offset
        )

    header = texts.PAY_LOG_HEADER.format(
        page=page,
        total_pages=total_pages,
        total=total,
    )
    body = "".join(_fmt_payment(p) for p in payments)
    text = header + (body if body else texts.PAY_LOG_EMPTY)
    kb = pay_log_nav_kb(page, total_pages, channel_id or None)
    return text, kb


@router.callback_query(F.data == "pay_logs")
async def pay_logs_entry(callback: CallbackQuery):
    text, kb = await _render_logs_page(callback.from_user.id, page=1)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("plog_page:"))
async def pay_logs_page(callback: CallbackQuery):
    # format: plog_page:<page>:<channel_id>
    parts = callback.data.split(":")
    page = int(parts[1])
    channel_id = int(parts[2]) if len(parts) > 2 else 0

    text, kb = await _render_logs_page(callback.from_user.id, page, channel_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "plog_filter")
async def pay_logs_filter(callback: CallbackQuery):
    channels = await q.get_channels_by_owner(callback.from_user.id)
    if not channels:
        await callback.answer("У тебя нет каналов.", show_alert=True)
        return
    await callback.message.edit_text(
        texts.PAY_LOG_FILTER_HEADER,
        reply_markup=pay_log_channel_filter_kb(channels),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "plog_noop")
async def pay_logs_noop(callback: CallbackQuery):
    # Кнопка «текущая страница» — ничего не делает
    await callback.answer()
