import aiosqlite
import json
from datetime import datetime, timedelta
from typing import Optional

from bot.db.models import DB_PATH


# ══════════════════════════════════════════════════════════════════════════════
# USERS
# ══════════════════════════════════════════════════════════════════════════════

async def get_or_create_user(telegram_id: int, username: Optional[str]) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)) as c:
            row = await c.fetchone()
        if row:
            return dict(row)
        await db.execute(
            "INSERT INTO users (telegram_id, username) VALUES (?,?)", (telegram_id, username)
        )
        await db.commit()
        async with db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)) as c:
            row = await c.fetchone()
        return dict(row)


async def get_user(telegram_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)) as c:
            row = await c.fetchone()
        return dict(row) if row else None


async def update_username(telegram_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET username=? WHERE telegram_id=?", (username, telegram_id))
        await db.commit()


async def set_referred_by(referred_id: int, referrer_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET referred_by=? WHERE telegram_id=? AND referred_by IS NULL",
            (referrer_id, referred_id),
        )
        await db.commit()


async def activate_key_for_user(telegram_id: int, key_code: str, duration_days: int) -> int:
    user = await get_user(telegram_id)
    bonus = user.get("referral_bonus_days", 0) if user else 0
    total_days = duration_days + bonus
    expires_at = (datetime.utcnow() + timedelta(days=total_days)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET activated_key=?, key_expires_at=?, referral_bonus_days=0 WHERE telegram_id=?",
            (key_code, expires_at, telegram_id),
        )
        await db.execute(
            "UPDATE keys SET is_active=0, used_by=?, used_at=datetime('now') WHERE key_code=?",
            (telegram_id, key_code),
        )
        await db.commit()
    return total_days


async def add_bonus_days_to_user(telegram_id: int, days: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)) as c:
            user = await c.fetchone()
        if not user:
            return
        user = dict(user)
        if user.get("key_expires_at"):
            try:
                current = datetime.strptime(user["key_expires_at"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                current = datetime.utcnow()
            new_exp = (current + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            await db.execute(
                "UPDATE users SET key_expires_at=? WHERE telegram_id=?", (new_exp, telegram_id)
            )
        else:
            new_bonus = (user.get("referral_bonus_days") or 0) + days
            await db.execute(
                "UPDATE users SET referral_bonus_days=? WHERE telegram_id=?", (new_bonus, telegram_id)
            )
        await db.commit()


async def get_all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT telegram_id FROM users") as c:
            return [r[0] for r in await c.fetchall()]


async def count_users() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            return (await c.fetchone())[0]


async def is_key_valid_for_user(telegram_id: int) -> bool:
    user = await get_user(telegram_id)
    if not user or not user.get("key_expires_at"):
        return False
    return datetime.strptime(user["key_expires_at"], "%Y-%m-%d %H:%M:%S") > datetime.utcnow()


async def deactivate_expired_user_keys():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET activated_key=NULL, key_expires_at=NULL "
            "WHERE key_expires_at IS NOT NULL AND key_expires_at <= datetime('now')"
        )
        await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# KEYS
# ══════════════════════════════════════════════════════════════════════════════

async def create_key(key_code: str, duration_days: int, created_by: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT INTO keys (key_code, duration_days, created_by_admin) VALUES (?,?,?)",
            (key_code, duration_days, created_by),
        )
        await db.commit()
        async with db.execute("SELECT * FROM keys WHERE key_code=?", (key_code,)) as c:
            return dict(await c.fetchone())


async def get_key(key_code: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM keys WHERE key_code=? AND is_active=1 AND used_by IS NULL", (key_code,)
        ) as c:
            row = await c.fetchone()
        return dict(row) if row else None


async def count_active_keys() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM keys WHERE is_active=1 AND used_by IS NULL") as c:
            return (await c.fetchone())[0]


# ══════════════════════════════════════════════════════════════════════════════
# CHANNELS
# ══════════════════════════════════════════════════════════════════════════════

async def get_or_create_channel(owner_id: int, channel_id: int, username: Optional[str], title: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels WHERE channel_id=?", (channel_id,)) as c:
            row = await c.fetchone()
        if row:
            return dict(row)
        await db.execute(
            "INSERT INTO channels (owner_id, channel_id, channel_username, channel_title) VALUES (?,?,?,?)",
            (owner_id, channel_id, username, title),
        )
        await db.commit()
        async with db.execute("SELECT * FROM channels WHERE channel_id=?", (channel_id,)) as c:
            return dict(await c.fetchone())


async def get_channel_by_id(channel_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels WHERE channel_id=?", (channel_id,)) as c:
            row = await c.fetchone()
        return dict(row) if row else None


async def get_channels_by_owner(owner_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels WHERE owner_id=?", (owner_id,)) as c:
            return [dict(r) for r in await c.fetchall()]


async def get_all_channels() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels") as c:
            return [dict(r) for r in await c.fetchall()]


async def toggle_channel_status(channel_id: int, is_active: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE channels SET is_active=? WHERE channel_id=?", (is_active, channel_id))
        await db.commit()


async def count_channels() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM channels WHERE is_active=1") as c:
            return (await c.fetchone())[0]


# ══════════════════════════════════════════════════════════════════════════════
# SUBSCRIPTION PLANS
# ══════════════════════════════════════════════════════════════════════════════

async def create_plan(
    channel_id: int,
    owner_id: int,
    title: str,
    payment_methods_text: str,
    membership_duration_days: int,
    require_key: bool,
) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT INTO subscription_plans "
            "(channel_id, owner_id, title, payment_methods_text, membership_duration_days, require_key) "
            "VALUES (?,?,?,?,?,?)",
            (channel_id, owner_id, title, payment_methods_text,
             membership_duration_days, int(require_key)),
        )
        await db.commit()
        async with db.execute(
            "SELECT * FROM subscription_plans WHERE owner_id=? ORDER BY id DESC LIMIT 1", (owner_id,)
        ) as c:
            return dict(await c.fetchone())


async def get_plan(plan_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscription_plans WHERE id=? AND is_active=1", (plan_id,)
        ) as c:
            row = await c.fetchone()
        return dict(row) if row else None


async def get_plans_by_owner(owner_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscription_plans WHERE owner_id=? ORDER BY id DESC", (owner_id,)
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def get_plans_by_channel(channel_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscription_plans WHERE channel_id=? AND is_active=1", (channel_id,)
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def update_plan_payment(
    plan_id: int,
    payment_mode: str,
    cryptobot_token: Optional[str] = None,
    cryptobot_asset: Optional[str] = None,
    cryptobot_amount: Optional[float] = None,
    yukassa_shop_id: Optional[str] = None,
    yukassa_secret_key: Optional[str] = None,
    yukassa_amount: Optional[float] = None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE subscription_plans SET "
            "payment_mode=?, cryptobot_token=?, cryptobot_asset=?, cryptobot_amount=?, "
            "yukassa_shop_id=?, yukassa_secret_key=?, yukassa_amount=? "
            "WHERE id=?",
            (payment_mode, cryptobot_token, cryptobot_asset, cryptobot_amount,
             yukassa_shop_id, yukassa_secret_key, yukassa_amount, plan_id),
        )
        await db.commit()


async def count_plans_by_owner(owner_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM subscription_plans WHERE owner_id=?", (owner_id,)
        ) as c:
            return (await c.fetchone())[0]


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENTS
# ══════════════════════════════════════════════════════════════════════════════

async def create_payment(
    user_id: int, channel_id: int, plan_id: int,
    amount: float, currency: str, payment_system: str, external_id: str,
) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT INTO payments (user_id, channel_id, plan_id, amount, currency, payment_system, external_id) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, channel_id, plan_id, amount, currency, payment_system, external_id),
        )
        await db.commit()
        async with db.execute("SELECT * FROM payments WHERE external_id=?", (external_id,)) as c:
            return dict(await c.fetchone())


async def get_payment_by_external_id(external_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM payments WHERE external_id=? ORDER BY id DESC LIMIT 1", (external_id,)
        ) as c:
            row = await c.fetchone()
        return dict(row) if row else None


async def mark_payment_paid(external_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET status='paid', paid_at=datetime('now') WHERE external_id=?",
            (external_id,),
        )
        await db.commit()


async def get_pending_payments_all() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM payments WHERE status='pending' "
            "AND created_at <= datetime('now', '-2 minutes')"
        ) as c:
            return [dict(r) for r in await c.fetchall()]


# ══════════════════════════════════════════════════════════════════════════════
# SUBSCRIPTIONS
# ══════════════════════════════════════════════════════════════════════════════

async def create_subscription(user_id: int, channel_id: int, plan_id: int, duration_days: int) -> dict:
    expires_at = (datetime.utcnow() + timedelta(days=duration_days)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT INTO subscriptions (user_id, channel_id, plan_id, expires_at) VALUES (?,?,?,?)",
            (user_id, channel_id, plan_id, expires_at),
        )
        await db.commit()
        async with db.execute(
            "SELECT * FROM subscriptions WHERE user_id=? AND channel_id=? ORDER BY id DESC LIMIT 1",
            (user_id, channel_id),
        ) as c:
            return dict(await c.fetchone())


async def get_expired_subscriptions() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT s.*, c.channel_title, c.owner_id, u.username "
            "FROM subscriptions s "
            "JOIN channels c ON s.channel_id=c.channel_id "
            "JOIN users u ON s.user_id=u.telegram_id "
            "WHERE s.expires_at <= datetime('now') AND s.is_active=1"
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def get_expiring_soon_subscriptions(days_before: int = 3) -> list[dict]:
    threshold = (datetime.utcnow() + timedelta(days=days_before)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT s.*, c.channel_title, u.username "
            "FROM subscriptions s "
            "JOIN channels c ON s.channel_id=c.channel_id "
            "JOIN users u ON s.user_id=u.telegram_id "
            "WHERE s.expires_at<=? AND s.expires_at>datetime('now') "
            "AND s.is_active=1 AND s.reminded=0",
            (threshold,),
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def mark_subscription_reminded(sub_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE subscriptions SET reminded=1 WHERE id=?", (sub_id,))
        await db.commit()


async def deactivate_subscription(sub_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE subscriptions SET is_active=0 WHERE id=?", (sub_id,))
        await db.commit()


async def count_active_subscriptions() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM subscriptions WHERE is_active=1") as c:
            return (await c.fetchone())[0]


async def count_active_subs_for_channel(channel_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE channel_id=? AND is_active=1", (channel_id,)
        ) as c:
            return (await c.fetchone())[0]


async def get_channel_owner_stats(channel_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE channel_id=? AND is_active=1", (channel_id,)
        ) as c:
            active_subs = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE channel_id=?", (channel_id,)
        ) as c:
            total_subs = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM payments WHERE channel_id=? AND status='paid'", (channel_id,)
        ) as c:
            total_payments = (await c.fetchone())[0]
        async with db.execute(
            "SELECT SUM(amount), currency FROM payments WHERE channel_id=? AND status='paid' GROUP BY currency",
            (channel_id,),
        ) as c:
            revenue_rows = await c.fetchall()
        async with db.execute(
            "SELECT COUNT(*) FROM subscription_plans WHERE channel_id=? AND is_active=1", (channel_id,)
        ) as c:
            active_plans = (await c.fetchone())[0]
    return {
        "active_subs": active_subs,
        "total_subs": total_subs,
        "total_payments": total_payments,
        "revenue": {r[1]: round(r[0], 2) for r in revenue_rows if r[0]},
        "active_plans": active_plans,
    }


# ══════════════════════════════════════════════════════════════════════════════
# REFERRALS
# ══════════════════════════════════════════════════════════════════════════════

async def create_referral(referrer_id: int, referred_id: int, bonus_days: int = 7) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            await db.execute(
                "INSERT INTO referrals (referrer_id, referred_id, bonus_days) VALUES (?,?,?)",
                (referrer_id, referred_id, bonus_days),
            )
            await db.commit()
        except Exception:
            return None
        async with db.execute("SELECT * FROM referrals WHERE referred_id=?", (referred_id,)) as c:
            row = await c.fetchone()
        return dict(row) if row else None


async def get_referral_stats(referrer_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (referrer_id,)) as c:
            total = (await c.fetchone())[0]
        async with db.execute(
            "SELECT SUM(bonus_days) FROM referrals WHERE referrer_id=? AND credited=1", (referrer_id,)
        ) as c:
            earned = (await c.fetchone())[0] or 0
        async with db.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND credited=0", (referrer_id,)
        ) as c:
            pending = (await c.fetchone())[0]
    return {"total": total, "earned_days": earned, "pending": pending}


async def credit_pending_referrals(referrer_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM referrals WHERE referrer_id=? AND credited=0", (referrer_id,)
        ) as c:
            rows = [dict(r) for r in await c.fetchall()]
    for ref in rows:
        await add_bonus_days_to_user(referrer_id, ref["bonus_days"])
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE referrals SET credited=1 WHERE id=?", (ref["id"],))
            await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENT LOGS (для владельца канала)
# ══════════════════════════════════════════════════════════════════════════════

async def get_payments_by_owner(owner_id: int, limit: int = 20, offset: int = 0) -> list[dict]:
    """Все платежи по каналам владельца, от новых к старым."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT p.*, c.channel_title, u.username as buyer_username, "
            "sp.title as plan_title "
            "FROM payments p "
            "JOIN channels c ON p.channel_id = c.channel_id "
            "JOIN users u ON p.user_id = u.telegram_id "
            "JOIN subscription_plans sp ON p.plan_id = sp.id "
            "WHERE c.owner_id = ? "
            "ORDER BY p.created_at DESC "
            "LIMIT ? OFFSET ?",
            (owner_id, limit, offset),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def count_payments_by_owner(owner_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM payments p "
            "JOIN channels c ON p.channel_id = c.channel_id "
            "WHERE c.owner_id = ?",
            (owner_id,),
        ) as cur:
            return (await cur.fetchone())[0]


async def get_payments_by_owner_and_channel(
    owner_id: int, channel_id: int, limit: int = 20, offset: int = 0
) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT p.*, u.username as buyer_username, sp.title as plan_title "
            "FROM payments p "
            "JOIN users u ON p.user_id = u.telegram_id "
            "JOIN subscription_plans sp ON p.plan_id = sp.id "
            "JOIN channels c ON p.channel_id = c.channel_id "
            "WHERE p.channel_id = ? AND c.owner_id = ? "
            "ORDER BY p.created_at DESC "
            "LIMIT ? OFFSET ?",
            (channel_id, owner_id, limit, offset),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# BLACKLIST
# ══════════════════════════════════════════════════════════════════════════════

async def add_to_blacklist(owner_id: int, banned_user_id: int, reason: str = "") -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO blacklist (owner_id, banned_user_id, reason) VALUES (?,?,?)",
                (owner_id, banned_user_id, reason),
            )
            await db.commit()
            return True
        except Exception:
            return False  # уже в списке


async def remove_from_blacklist(owner_id: int, banned_user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM blacklist WHERE owner_id=? AND banned_user_id=?",
            (owner_id, banned_user_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def is_blacklisted(owner_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM blacklist WHERE owner_id=? AND banned_user_id=?",
            (owner_id, user_id),
        ) as c:
            return (await c.fetchone()) is not None


async def get_blacklist_by_owner(owner_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT b.*, u.username FROM blacklist b "
            "LEFT JOIN users u ON b.banned_user_id=u.telegram_id "
            "WHERE b.owner_id=? ORDER BY b.created_at DESC",
            (owner_id,),
        ) as c:
            return [dict(r) for r in await c.fetchall()]


# ══════════════════════════════════════════════════════════════════════════════
# WHITE-LABEL BOTS
# ══════════════════════════════════════════════════════════════════════════════

async def create_wl_bot(owner_id: int, bot_token: str, bot_username: str, bot_name: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            await db.execute(
                "INSERT INTO white_label_bots (owner_id, bot_token, bot_username, bot_name) "
                "VALUES (?,?,?,?)",
                (owner_id, bot_token, bot_username, bot_name),
            )
            await db.commit()
        except Exception:
            return None  # уже есть
        async with db.execute(
            "SELECT * FROM white_label_bots WHERE owner_id=?", (owner_id,)
        ) as c:
            row = await c.fetchone()
        return dict(row) if row else None


async def get_wl_bot_by_owner(owner_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM white_label_bots WHERE owner_id=?", (owner_id,)
        ) as c:
            row = await c.fetchone()
        return dict(row) if row else None


async def get_all_active_wl_bots() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM white_label_bots WHERE is_active=1"
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def get_all_wl_bots() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT w.*, u.username as owner_username, u.key_expires_at "
            "FROM white_label_bots w "
            "LEFT JOIN users u ON w.owner_id=u.telegram_id "
            "ORDER BY w.created_at DESC"
        ) as c:
            return [dict(r) for r in await c.fetchall()]


async def toggle_wl_bot(owner_id: int, is_active: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE white_label_bots SET is_active=? WHERE owner_id=?",
            (is_active, owner_id),
        )
        await db.commit()


async def delete_wl_bot(owner_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM white_label_bots WHERE owner_id=?", (owner_id,)
        )
        await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# PLAN CUSTOM TEXTS + RENEWAL
# ══════════════════════════════════════════════════════════════════════════════

async def update_plan_texts(plan_id: int, welcome_text: Optional[str], success_text: Optional[str]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE subscription_plans SET welcome_text=?, success_text=? WHERE id=?",
            (welcome_text, success_text, plan_id),
        )
        await db.commit()


async def get_subscriptions_expiring_in(hours: int) -> list[dict]:
    """Подписки истекающие ровно через ~hours часов (±30 мин). Для авторемайндера."""
    from datetime import timedelta
    now = datetime.utcnow()
    window_start = (now + timedelta(hours=hours - 1)).strftime("%Y-%m-%d %H:%M:%S")
    window_end   = (now + timedelta(hours=hours + 1)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT s.*, c.channel_title, c.owner_id, u.username, sp.id as plan_id_val "
            "FROM subscriptions s "
            "JOIN channels c ON s.channel_id=c.channel_id "
            "JOIN users u ON s.user_id=u.telegram_id "
            "JOIN subscription_plans sp ON s.plan_id=sp.id "
            "WHERE s.expires_at BETWEEN ? AND ? AND s.is_active=1 AND s.reminded=0",
            (window_start, window_end),
        ) as c:
            return [dict(r) for r in await c.fetchall()]
