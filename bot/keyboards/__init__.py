from typing import Optional
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🗂 Личный кабинет", callback_data="cabinet"))
    b.row(InlineKeyboardButton(text="💬 Поддержка", url="https://t.me/dpoov"))
    return b.as_markup()


def cabinet_no_key_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔑 Ввести ключ", callback_data="enter_key"))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_main"))
    return b.as_markup()


def cabinet_active_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Новый план подписки", callback_data="create_plan"))
    b.row(InlineKeyboardButton(text="📋 Мои планы", callback_data="my_plans"))
    b.row(InlineKeyboardButton(text="📡 Мои каналы", callback_data="my_channels"))
    b.row(InlineKeyboardButton(text="⚙️ Настроить оплату", callback_data="pay_setup"))
    b.row(InlineKeyboardButton(text="📊 Статистика", callback_data="owner_stats"))
    b.row(InlineKeyboardButton(text="💳 Логи платежей", callback_data="pay_logs"))
    b.row(InlineKeyboardButton(text="🔗 Реферальная ссылка", callback_data="referral_stats"))
    b.row(InlineKeyboardButton(text="✏️ Тексты планов", callback_data="plan_custom_texts"))
    b.row(InlineKeyboardButton(text="🚫 Чёрный список", callback_data="blacklist"))
    b.row(InlineKeyboardButton(text="🤖 Мой бот (white-label)", callback_data="wl_bot"))
    b.row(InlineKeyboardButton(text="🔑 Создать ключ участника", callback_data="create_user_key"))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_main"))
    return b.as_markup()


def back_cabinet_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 В кабинет", callback_data="cabinet"))
    return b.as_markup()


# ── PLAN BUILDER ──────────────────────────────────────────────────────────────

def membership_duration_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for label, v in [("7 дней", 7), ("14 дней", 14), ("30 дней", 30), ("90 дней", 90)]:
        b.button(text=label, callback_data=f"membership:{v}")
    b.button(text="✏️ Своё", callback_data="membership:custom")
    b.button(text="❌ Отмена", callback_data="cancel_fsm")
    b.adjust(2, 2, 1, 1)
    return b.as_markup()


def require_key_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Да", callback_data="require_key:yes"),
        InlineKeyboardButton(text="❌ Нет", callback_data="require_key:no"),
    )
    b.row(InlineKeyboardButton(text="↩️ Отмена", callback_data="cancel_fsm"))
    return b.as_markup()


# ── PAYMENT SETUP ─────────────────────────────────────────────────────────────

def plan_select_kb(plans: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in plans:
        b.row(InlineKeyboardButton(
            text=f"📋 {p['title']} ({p['membership_duration_days']} дн.)",
            callback_data=f"plan_sel:{p['id']}",
        ))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_fsm"))
    return b.as_markup()


def pay_mode_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🤖 CryptoBot", callback_data="pmode:cryptobot"))
    b.row(InlineKeyboardButton(text="🏦 YooKassa", callback_data="pmode:yukassa"))
    b.row(InlineKeyboardButton(text="🔀 Оба на выбор", callback_data="pmode:both"))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_fsm"))
    return b.as_markup()


def crypto_asset_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for asset in ["USDT", "TON", "BTC", "ETH", "LTC", "USDC"]:
        b.button(text=asset, callback_data=f"asset:{asset}")
    b.button(text="❌ Отмена", callback_data="cancel_fsm")
    b.adjust(3)
    return b.as_markup()


# ── USER PAYMENT FLOW ─────────────────────────────────────────────────────────

def pay_method_kb(has_crypto: bool, has_yukassa: bool, require_key: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if has_crypto:
        b.row(InlineKeyboardButton(text="🤖 CryptoBot (крипта)", callback_data="pay_with:cryptobot"))
    if has_yukassa:
        b.row(InlineKeyboardButton(text="🏦 ЮKassa (карта)", callback_data="pay_with:yukassa"))
    if require_key:
        b.row(InlineKeyboardButton(text="🔑 Ввести ключ доступа", callback_data="pay_with:key"))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="pay_cancel"))
    return b.as_markup()


def pay_invoice_kb(pay_url: str, external_id: str, system: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💳 Оплатить", url=pay_url))
    b.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"pay_check:{system}:{external_id}"))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="pay_cancel"))
    return b.as_markup()


# ── KEY DURATION ──────────────────────────────────────────────────────────────

def key_duration_kb(admin: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    days = [7, 14, 30, 90, 180, 365] if admin else [7, 14, 30, 90]
    for d in days:
        b.button(text=f"{d} дней", callback_data=f"key_dur:{d}")
    b.button(text="✏️ Своё", callback_data="key_dur:custom")
    b.button(text="❌ Отмена", callback_data="cancel_fsm")
    b.adjust(2)
    return b.as_markup()


# ── ADMIN ─────────────────────────────────────────────────────────────────────

def admin_main_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))
    b.row(InlineKeyboardButton(text="📋 Каналы", callback_data="admin_channels"))
    b.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    b.row(InlineKeyboardButton(text="🔑 Создать ключ", callback_data="admin_create_key"))
    b.row(InlineKeyboardButton(text="🤖 WL-боты", callback_data="admin_wl"))
    return b.as_markup()


def admin_back_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back"))
    return b.as_markup()


def admin_channel_toggle_kb(channel_id: int, is_active: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    label = "⛔ Отключить" if is_active else "✅ Включить"
    b.button(text=label, callback_data=f"toggle_ch:{channel_id}:{0 if is_active else 1}")
    return b.as_markup()


def broadcast_confirm_kb(count: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text=f"✅ Разослать ({count})", callback_data="bc_confirm"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="bc_cancel"),
    )
    return b.as_markup()


# ── PAYMENT LOGS ──────────────────────────────────────────────────────────────

def pay_log_nav_kb(
    page: int,
    total_pages: int,
    channel_id: Optional[int] = None,
) -> InlineKeyboardMarkup:
    """Навигация по страницам логов + кнопка фильтра."""
    from typing import Optional  # noqa — уже импортирован выше в реальном файле
    b = InlineKeyboardBuilder()
    nav_row = []
    ch_suffix = f":{channel_id}" if channel_id else ":0"

    if page > 1:
        nav_row.append(
            InlineKeyboardButton(text="◀️", callback_data=f"plog_page:{page-1}{ch_suffix}")
        )
    nav_row.append(
        InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="plog_noop")
    )
    if page < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="▶️", callback_data=f"plog_page:{page+1}{ch_suffix}")
        )
    if nav_row:
        b.row(*nav_row)

    b.row(InlineKeyboardButton(text="📡 Фильтр по каналу", callback_data="plog_filter"))
    if channel_id:
        b.row(InlineKeyboardButton(text="✖️ Сбросить фильтр", callback_data="plog_page:1:0"))
    b.row(InlineKeyboardButton(text="🔙 В кабинет", callback_data="cabinet"))
    return b.as_markup()


def pay_log_channel_filter_kb(channels: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📋 Все каналы", callback_data="plog_page:1:0"))
    for ch in channels:
        title = ch.get("channel_title") or str(ch["channel_id"])
        b.row(InlineKeyboardButton(
            text=f"📡 {title}",
            callback_data=f"plog_page:1:{ch['channel_id']}",
        ))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="pay_logs"))
    return b.as_markup()


# ── PLAN CUSTOMIZATION ────────────────────────────────────────────────────────

def plan_custom_texts_kb(plan_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ Приветствие", callback_data=f"pct_welcome:{plan_id}"))
    b.row(InlineKeyboardButton(text="✏️ После оплаты", callback_data=f"pct_success:{plan_id}"))
    b.row(InlineKeyboardButton(text="🔙 В кабинет", callback_data="cabinet"))
    return b.as_markup()


# ── BLACKLIST ─────────────────────────────────────────────────────────────────

def blacklist_kb(entries: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for e in entries:
        uname = f"@{e['username']}" if e.get("username") else str(e["banned_user_id"])
        b.row(InlineKeyboardButton(
            text=f"❌ Разбанить {uname}",
            callback_data=f"bl_unban:{e['banned_user_id']}",
        ))
    b.row(InlineKeyboardButton(text="➕ Добавить", callback_data="bl_add"))
    b.row(InlineKeyboardButton(text="🔙 В кабинет", callback_data="cabinet"))
    return b.as_markup()


# ── WHITE-LABEL ───────────────────────────────────────────────────────────────

def wl_choose_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🤖 Подключить свой бот", callback_data="wl_connect"))
    b.row(InlineKeyboardButton(text="✅ Остаться на общем", callback_data="cabinet"))
    return b.as_markup()


def wl_manage_kb(is_active: int, owner_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if is_active:
        b.row(InlineKeyboardButton(text="⛔ Остановить", callback_data=f"wl_stop:{owner_id}"))
    else:
        b.row(InlineKeyboardButton(text="▶️ Запустить", callback_data=f"wl_start:{owner_id}"))
    b.row(InlineKeyboardButton(text="🔄 Заменить токен", callback_data="wl_connect"))
    b.row(InlineKeyboardButton(text="🗑 Удалить бота", callback_data=f"wl_delete:{owner_id}"))
    b.row(InlineKeyboardButton(text="🔙 В кабинет", callback_data="cabinet"))
    return b.as_markup()


def wl_replace_confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Заменить", callback_data="wl_replace_yes"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="wl_my_bot"),
    )
    return b.as_markup()


# ── RENEWAL ───────────────────────────────────────────────────────────────────

def renewal_kb(plan_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔄 Продлить подписку", callback_data=f"renew:{plan_id}"))
    return b.as_markup()


# ── ADMIN WL ──────────────────────────────────────────────────────────────────

def admin_wl_toggle_kb(owner_id: int, is_active: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    label = "⛔ Отключить" if is_active else "✅ Включить"
    b.button(text=label, callback_data=f"adm_wl_toggle:{owner_id}:{0 if is_active else 1}")
    return b.as_markup()
