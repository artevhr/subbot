import aiosqlite
import logging

logger = logging.getLogger(__name__)
DB_PATH = "subbot.db"

CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id         INTEGER UNIQUE NOT NULL,
    username            TEXT,
    activated_key       TEXT,
    key_expires_at      TEXT,
    referral_bonus_days INTEGER DEFAULT 0,
    referred_by         INTEGER,
    created_at          TEXT DEFAULT (datetime('now'))
)
"""

CREATE_KEYS = """
CREATE TABLE IF NOT EXISTS keys (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    key_code         TEXT UNIQUE NOT NULL,
    duration_days    INTEGER NOT NULL,
    created_by_admin INTEGER NOT NULL,
    used_by          INTEGER,
    used_at          TEXT,
    is_active        INTEGER DEFAULT 1
)
"""

CREATE_CHANNELS = """
CREATE TABLE IF NOT EXISTS channels (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id         INTEGER NOT NULL,
    channel_id       INTEGER UNIQUE NOT NULL,
    channel_username TEXT,
    channel_title    TEXT,
    is_active        INTEGER DEFAULT 1,
    added_at         TEXT DEFAULT (datetime('now'))
)
"""

# ── ПЛАНЫ ПОДПИСКИ ────────────────────────────────────────────────────────────
# Каждый «план» — это настройки для продажи доступа в конкретный канал.
# Владелец получает bot-ссылку вида t.me/bot?start=join_<id>
# и распространяет её вместо прямой invite-ссылки на канал.

CREATE_SUBSCRIPTION_PLANS = """
CREATE TABLE IF NOT EXISTS subscription_plans (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id               INTEGER NOT NULL,
    owner_id                 INTEGER NOT NULL,
    title                    TEXT,
    payment_methods_text     TEXT,
    membership_duration_days INTEGER NOT NULL DEFAULT 30,
    require_key              INTEGER DEFAULT 0,
    payment_mode             TEXT DEFAULT 'manual',
    cryptobot_token          TEXT,
    cryptobot_asset          TEXT DEFAULT 'USDT',
    cryptobot_amount         REAL,
    yukassa_shop_id          TEXT,
    yukassa_secret_key       TEXT,
    yukassa_amount           REAL,
    yukassa_currency         TEXT DEFAULT 'RUB',
    is_active                INTEGER DEFAULT 1,
    created_at               TEXT DEFAULT (datetime('now'))
)
"""

CREATE_PAYMENTS = """
CREATE TABLE IF NOT EXISTS payments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    channel_id     INTEGER NOT NULL,
    plan_id        INTEGER NOT NULL,
    amount         REAL,
    currency       TEXT,
    payment_system TEXT,
    external_id    TEXT UNIQUE,
    status         TEXT DEFAULT 'pending',
    created_at     TEXT DEFAULT (datetime('now')),
    paid_at        TEXT
)
"""

CREATE_SUBSCRIPTIONS = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    channel_id     INTEGER NOT NULL,
    plan_id        INTEGER NOT NULL,
    joined_at      TEXT DEFAULT (datetime('now')),
    expires_at     TEXT NOT NULL,
    is_active      INTEGER DEFAULT 1,
    reminded       INTEGER DEFAULT 0
)
"""

CREATE_REFERRALS = """
CREATE TABLE IF NOT EXISTS referrals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER NOT NULL,
    referred_id INTEGER UNIQUE NOT NULL,
    bonus_days  INTEGER DEFAULT 7,
    credited    INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
)
"""

ALL_TABLES = [
    CREATE_USERS, CREATE_KEYS, CREATE_CHANNELS,
    CREATE_SUBSCRIPTION_PLANS, CREATE_PAYMENTS,
    CREATE_SUBSCRIPTIONS, CREATE_REFERRALS,
]

MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN referral_bonus_days INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN referred_by INTEGER",
]


async def create_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        for stmt in ALL_TABLES:
            await db.execute(stmt)
        for migration in MIGRATIONS:
            try:
                await db.execute(migration)
            except Exception:
                pass
        await db.commit()
    logger.info("Database tables created/verified")

CREATE_BLACKLIST = """
CREATE TABLE IF NOT EXISTS blacklist (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id      INTEGER NOT NULL,
    banned_user_id INTEGER NOT NULL,
    reason        TEXT,
    created_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(owner_id, banned_user_id)
)
"""

CREATE_WHITE_LABEL_BOTS = """
CREATE TABLE IF NOT EXISTS white_label_bots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id     INTEGER NOT NULL UNIQUE,
    bot_token    TEXT NOT NULL UNIQUE,
    bot_username TEXT,
    bot_name     TEXT,
    is_active    INTEGER DEFAULT 1,
    created_at   TEXT DEFAULT (datetime('now'))
)
"""

# Добавляем новые таблицы в ALL_TABLES и новые колонки в MIGRATIONS
ALL_TABLES.extend([CREATE_BLACKLIST, CREATE_WHITE_LABEL_BOTS])

MIGRATIONS.extend([
    "ALTER TABLE subscription_plans ADD COLUMN welcome_text TEXT",
    "ALTER TABLE subscription_plans ADD COLUMN success_text TEXT",
    "ALTER TABLE subscription_plans ADD COLUMN trial_days INTEGER DEFAULT 0",
])
