import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from bot.db import queries as q
from bot import texts
from bot.keyboards import back_cabinet_kb

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "owner_stats")
async def owner_stats(callback: CallbackQuery):
    channels = await q.get_channels_by_owner(callback.from_user.id)
    if not channels:
        await callback.answer(texts.OWNER_STATS_NO_CHANNELS, show_alert=True)
        return

    text = texts.OWNER_STATS_HEADER
    for ch in channels:
        stats = await q.get_channel_owner_stats(ch["channel_id"])
        if stats["revenue"]:
            revenue_str = " | ".join(
                texts.OWNER_STATS_REVENUE_ITEM.format(amount=v, currency=c)
                for c, v in stats["revenue"].items()
            )
        else:
            revenue_str = texts.OWNER_STATS_REVENUE_EMPTY
        text += texts.OWNER_STATS_CHANNEL.format(
            title=ch.get("channel_title", str(ch["channel_id"])),
            active_subs=stats["active_subs"],
            total_subs=stats["total_subs"],
            active_plans=stats["active_plans"],
            total_payments=stats["total_payments"],
            revenue=revenue_str,
        )
    await callback.message.edit_text(text, reply_markup=back_cabinet_kb(), parse_mode="HTML")
    await callback.answer()
