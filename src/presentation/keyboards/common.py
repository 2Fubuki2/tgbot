from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.domain.value_objects.role import UserRole


# ─── Helper ──────────────────────────────────────
def build_kb(buttons: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    """Build inline keyboard from list of [(text, callback_data), ...] rows."""
    builder = InlineKeyboardBuilder()
    for row in buttons:
        row_buttons = [InlineKeyboardButton(text=btn[0], callback_data=btn[1]) for btn in row]
        builder.row(*row_buttons)
    return builder.as_markup()


# ─── Общие кнопки ───────────────────────────────
MAIN_MENU_BTN = ("🏠 Главное меню", "main_menu")
BACK_BTN = ("🔙 Назад", "back")


def main_menu_keyboard(role: UserRole) -> InlineKeyboardMarkup:
    """Build main menu based on user role."""
    if role == UserRole.ADMIN:
        return _admin_main_menu()
    elif role == UserRole.TREASURER:
        return _treasurer_main_menu()
    else:
        return _member_main_menu()


# ─── Участник ────────────────────────────────────
def _member_main_menu() -> InlineKeyboardMarkup:
    return build_kb([
        [("💰 Мой бюджет", "my_budget")],
    ])


# ─── Казначей ────────────────────────────────────
def _treasurer_main_menu() -> InlineKeyboardMarkup:
    return build_kb([
        [("💰 Мой бюджет", "my_budget")],
        [("💼 Бюджет клуба", "club_budget")],
    ])


# ─── Администратор ──────────────────────────────
def _admin_main_menu() -> InlineKeyboardMarkup:
    return build_kb([
        [("💰 Мой бюджет", "my_budget")],
        [("💼 Бюджет клуба", "club_budget")],
        [("👑 Управление", "admin_management")],
    ])


# ─── Мой бюджет (для всех пользователей) ─────────
def my_budget_keyboard() -> InlineKeyboardMarkup:
    """Личный бюджет: лицевой счёт, платежи, штрафы."""
    return build_kb([
        [("📋 Лицевой счёт", "member_account")],
        [("💰 Мои платежи", "member_payments")],
        [("⚠️ Мои штрафы", "member_fines")],
        [("💳 Реквизиты", "member_details")],
        [("📤 Я оплатил", "member_pay")],
        [BACK_BTN],
    ])


# ─── Бюджет клуба (для казначея/админа) ──────────
def club_budget_keyboard() -> InlineKeyboardMarkup:
    """Бюджет клуба: взносы, платежи, штрафы, расходы."""
    return build_kb([
        [("💰 Начислить взносы", "treasurer_assess_fees")],
        [("⏳ Подтвердить платежи", "treasurer_pending")],
        [("📋 Все участники", "treasurer_members")],
        [("⚠️ Штрафы", "treasurer_fines")],
        [("💸 Расходы клуба", "treasurer_expenses")],
        [("📅 Хронология", "treasurer_timeline")],
        [("📬 Напоминания", "treasurer_remind")],
        [("⏰ Просроченные", "treasurer_overdue")],
        [("📊 Статистика", "treasurer_stats")],
        [BACK_BTN],
    ])


# ─── Управление (только для админа) ───────────────
def admin_management_keyboard() -> InlineKeyboardMarkup:
    """Управление клубом: пользователи, настройки, журнал."""
    return build_kb([
        [("👥 Пользователи", "admin_users")],
        [("⚙️ Настройки", "admin_settings")],
        [("💰 Коррекция казны", "admin_treasury_adjust")],
        [("📋 Журнал", "admin_log")],
        [("📄 Экспорт", "admin_export")],
        [("📣 Рассылка", "admin_broadcast")],
        [BACK_BTN],
    ])


# ─── Общие клавиатуры ─────────────────────────────
def back_keyboard(callback: str = "back") -> InlineKeyboardMarkup:
    return build_kb([
        [("🔙 Назад", callback)],
    ])


def confirm_cancel_keyboard(confirm_cb: str, cancel_cb: str = "cancel_action") -> InlineKeyboardMarkup:
    """Клавиатура подтверждения/отмены действия."""
    return build_kb([
        [("✅ Подтвердить", confirm_cb)],
        [("❌ Отменить", cancel_cb)],
    ])


def assess_fees_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа начисления взносов."""
    return build_kb([
        [("📅 Текущий месяц", "assess_current")],
        [("✏️ Вручную", "assess_manual")],
    ])


def cancel_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура только с кнопкой отмены."""
    return build_kb([
        [("❌ Отменить", "cancel_action")],
    ])


# ─── Пользователи (админ) ─────────────────────────
def admin_users_keyboard() -> InlineKeyboardMarkup:
    return build_kb([
        [("➕ Добавить участника", "admin_user_add")],
        [("⏳ Ожидают входа (инвайты)", "admin_invites_list")],
        [("📋 Все участники", "admin_user_list")],
        [MAIN_MENU_BTN],
    ])


def admin_invites_keyboard(invites: list[tuple[int, str, str, str]]) -> InlineKeyboardMarkup:
    """Invites list with delete buttons: list of (invite_id, username, full_name, role)."""
    rows = []
    for inv_id, username, full_name, role in invites:
        rows.append([
            (f"@{username} • {full_name} ({role})", "noop"),
            ("🗑 Отменить", f"admin_invite_delete:{inv_id}"),
        ])
    rows.append([("🔙 Назад к пользователям", "admin_users")])
    rows.append([MAIN_MENU_BTN])
    return build_kb(rows)



def user_actions_keyboard(user_id: int, status: str | None = None) -> InlineKeyboardMarkup:
    """Build actions keyboard for a user. If `status` is EXPELLED show restore button."""
    if status == "expelled":
        return build_kb([
            [("↩️ Восстановить доступ", f"admin_restore:{user_id}")],
            [MAIN_MENU_BTN],
        ])

    return build_kb([
        [("👑 Назначить админом", f"admin_role_admin:{user_id}")],
        [("🔑 Назначить казначеем", f"admin_role_treasurer:{user_id}")],
        [("👤 Назначить участником", f"admin_role_member:{user_id}")],
        [("✏️ Изменить никнейм", f"admin_rename:{user_id}")],
        [("📦 Архивировать", f"admin_archive:{user_id}")],
        [("🗑 Удалить", f"admin_delete_confirm:{user_id}")],
        [("🔙 Назад к списку", "admin_user_list")],
        [MAIN_MENU_BTN],
    ])


def admin_users_list_keyboard(users: list[tuple[int, str]], page: int = 0, highlight_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Добавить участника", callback_data="admin_user_add"),
        InlineKeyboardButton(text="⏳ Инвайты", callback_data="admin_invites_list"),
    )
    per_page = 8
    start = page * per_page
    chunk = users[start:start + per_page]


    for user_id, name in chunk:
        prefix = "🔷 " if user_id == highlight_id else ""
        builder.row(
            InlineKeyboardButton(text=f"{prefix}{name}", callback_data=f"user_actions:{user_id}")
        )

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_users_page:{page - 1}"))
    if start + per_page < len(users):
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_users_page:{page + 1}"))
    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(InlineKeyboardButton(text=MAIN_MENU_BTN[0], callback_data=MAIN_MENU_BTN[1]))
    return builder.as_markup()


# ─── Настройки ────────────────────────────────────
def admin_settings_keyboard() -> InlineKeyboardMarkup:
    return build_kb([
        [("💰 Размер взноса", "admin_set_fee")],
        [("💳 Реквизиты", "admin_set_details")],
        [("🏷 Название клуба", "admin_set_name")],
        [("📅 Дата начисления", "admin_set_assessment_day")],
        [("⚡ Начислить сейчас", "admin_assess_now")],
        [MAIN_MENU_BTN],
    ])


# ─── Платежи (казначей) ────────────────────────────
def payment_action_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    return build_kb([
        [("✅ Подтвердить", f"payment_confirm:{payment_id}")],
        [("❌ Отклонить", f"payment_reject:{payment_id}")],
        [("📋 Мой бюджет", "my_budget")],
    ])


# ─── Участники (казначей) ──────────────────────────
def members_list_keyboard(users: list[tuple[int, str]], page: int = 0) -> InlineKeyboardMarkup:
    """Paginated member list for treasurer."""
    builder = InlineKeyboardBuilder()
    per_page = 8
    start = page * per_page
    chunk = users[start:start + per_page]

    for user_id, name in chunk:
        builder.row(InlineKeyboardButton(text=name, callback_data=f"member_view:{user_id}"))

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"members_page:{page - 1}"))
    if start + per_page < len(users):
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"members_page:{page + 1}"))
    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(InlineKeyboardButton(text=MAIN_MENU_BTN[0], callback_data=MAIN_MENU_BTN[1]))
    return builder.as_markup()


def payment_type_keyboard() -> InlineKeyboardMarkup:
    return build_kb([
        [("💰 Ежемесячный взнос", "pay_type:fee")],
        [("⚠️ Штраф", "pay_type:fine")],
        [("❌ Отменить", "cancel_action")],
    ])


def member_detail_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return build_kb([
        [("💰 История платежей", f"member_payments:{user_id}")],
        [("⚠️ Штрафы", f"member_fines:{user_id}")],
        [("💰 Взносы", f"member_fees:{user_id}")],
        [("🔙 Назад", "back")],
    ])


def member_detail_admin_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Member detail view for admins — with ledger edit buttons."""
    return build_kb([
        [("📋 История платежей", f"ledger_payments:{user_id}")],
        [("⚠️ История штрафов", f"ledger_fines:{user_id}")],
        [("💰 История взносов", f"ledger_fees:{user_id}")],
        [("💳 Принять оплату", f"treasurer_pay:{user_id}")],
        [("⚠️ Начислить штраф", f"fine_issue:{user_id}")],
        [("📬 Отправить напоминание", f"remind_user:{user_id}")],
        [("🔙 Назад", "back")],
    ])


# ─── Штрафы ────────────────────────────────────────
def fine_actions_keyboard(fine_id: int) -> InlineKeyboardMarkup:
    return build_kb([
        [("💳 Оплатить штраф", f"pay_fine:{fine_id}")],
        [("❌ Отменить штраф", f"fine_cancel:{fine_id}")],
        [BACK_BTN],
    ])


# ─── Расходы ──────────────────────────────────────
def expense_categories_keyboard() -> InlineKeyboardMarkup:
    return build_kb([
        [("🔧 Запчасти", "expense_cat:parts")],
        [("⛽ Топливо", "expense_cat:fuel")],
        [("🎉 Мероприятия", "expense_cat:events")],
        [("🏠 Аренда", "expense_cat:rent")],
        [("🛡 Экипировка", "expense_cat:equipment")],
        [("🍕 Питание", "expense_cat:food")],
        [("🚚 Транспорт", "expense_cat:transport")],
        [("📦 Прочее", "expense_cat:other")],
        [BACK_BTN],
    ])


def expense_edit_keyboard(expense_id: int) -> InlineKeyboardMarkup:
    """Keyboard for editing/deleting an expense."""
    return build_kb([
        [("✏️ Изменить", f"expense_edit:{expense_id}")],
        [("🗑 Удалить", f"expense_delete_confirm:{expense_id}")],
        [BACK_BTN],
    ])


# ─── Подтверждение ─────────────────────────────────
def confirm_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    return build_kb([
        [("✅ Да", callback_data)],
        [("❌ Нет", "back")],
    ])


# ─── Распределение платежа по штрафам ──────────────
def fine_allocation_keyboard(payment_id: int, fines: list) -> InlineKeyboardMarkup:
    """Keyboard to allocate a fine-type payment to a specific active fine."""
    rows = []
    for fine in fines:
        rows.append((f"⚠️ {fine.reason} — {fine.remaining_amount:,.2f}₽", f"fine_allocate:{payment_id}:{fine.id}"))
    rows.append(("⏩ Прочие остаток → баланс", f"fine_overflow:{payment_id}"))
    rows.append(("🔙 Назад", f"payment_confirm:{payment_id}"))
    return build_kb(rows)


# ─── Хронология ──────────────────────────────────────
def timeline_user_select_keyboard(users: list[tuple[int, str]], page: int = 0) -> InlineKeyboardMarkup:
    """Paginated member selector for timeline."""
    per_page = 8
    total_pages = (len(users) + per_page - 1) // per_page if users else 1
    start = page * per_page
    end = start + per_page
    page_users = users[start:end]

    rows: list[list[tuple[str, str]]] = []
    for user_id, name in page_users:
        rows.append((name, f"timeline_user:{user_id}"))

    # Pagination buttons
    nav_parts = []
    if page > 0:
        nav_parts.append(("⬅️ Назад", f"timeline_page:{page - 1}"))
    if page < total_pages - 1:
        nav_parts.append(("Далее ➡️", f"timeline_page:{page + 1}"))
    if nav_parts:
        rows.append(nav_parts[0])
        if len(nav_parts) > 1:
            rows.append(nav_parts[1])
    rows.append((MAIN_MENU_BTN[0], MAIN_MENU_BTN[1]))

    return build_kb(rows)


def timeline_item_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return build_kb([
        [BACK_BTN],
    ])


# ─── Выбор месяца (для оплаты) ───────────────────
_MONTH_NAMES = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]
_MONTH_SHORT = ["янв", "фев", "мар", "апр", "май", "июн",
                "июл", "авг", "сен", "окт", "ноя", "дек"]


def persistent_menu_keyboard(role, nav_history):
    """Построить контекстную панель быстрых кнопок внизу экрана."""

    current = nav_history[-1] if nav_history else "main_menu"

    # Наборы кнопок по экранам
    _SCREEN_BUTTONS = {
        "main_menu": [],
        "my_budget": [("🏠 Меню", "main_menu")],
        "member_account": [("💰 Платежи", "member_payments"), ("⚠️ Штрафы", "member_fines")],
        "member_payments": [("📋 Лицевой счёт", "member_account")],
        "member_fines": [("💰 Платежи", "member_payments")],
        "member_details": [],
        "club_budget": [("🏠 Меню", "main_menu")],
        "treasurer_pending": [("📋 Участники", "treasurer_members")],
        "treasurer_members": [("⏳ Платежи", "treasurer_pending")],
        "treasurer_fines": [("💸 Расходы", "treasurer_expenses")],
        "treasurer_expenses": [("📋 Участники", "treasurer_members")],
        "treasurer_timeline": [],
        "admin_management": [],
    }

    quick = _SCREEN_BUTTONS.get(current, [])

    # Кнопки по роли
    role_buttons = []
    if role in (UserRole.MEMBER,):
        role_buttons = [("💰 Мой бюджет", "my_budget")]
    elif role in (UserRole.TREASURER,):
        role_buttons = [("🏠 Меню", "main_menu"), ("💰 Мой бюджет", "my_budget")]
    elif role == UserRole.ADMIN:
        role_buttons = [("🏠 Меню", "main_menu"), ("💰 Мой бюджет", "my_budget"),
                         ("💼 Бюджет клуба", "club_budget")]

    buttons = quick + role_buttons
    # Не более 6 кнопок, по 3 в ряд
    buttons = buttons[:6]

    builder = InlineKeyboardBuilder()
    for i in range(0, len(buttons), 3):
        chunk = buttons[i:i + 3]
        row = [InlineKeyboardButton(text=b[0], callback_data=b[1]) for b in chunk]
        builder.row(*row)

    # Кнопка «назад» если есть история
    if len(nav_history) > 1 and current != "main_menu":
        prev = nav_history[-2]
        builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=prev))

    return builder.as_markup()


def payment_month_keyboard(current_year: int, current_month: int) -> InlineKeyboardMarkup:
    """Inline keyboard with 12 months for payment flow. Shows current year with prev/next year buttons."""
    rows: list[list[tuple[str, str]]] = []

    # Year selector row
    rows.append([
        (f"⬅️ {current_year - 1}", f"pay_month_year:{current_year - 1}"),
        (f"📅 {current_year}", "pay_month_current"),
        (f"{current_year + 1} ➡️", f"pay_month_year:{current_year + 1}"),
    ])

    # 12 months in 4 rows of 3
    for i in range(0, 12, 3):
        row = []
        for j in range(3):
            idx = i + j
            name = _MONTH_SHORT[idx]
            mb = f"pay_month:{idx + 1}"
            if idx + 1 == current_month:
                row.append((f"🔹 {name}", mb))
            else:
                row.append((name, mb))
        rows.append(row)

    rows.append([("🔙 Назад", "back")])
    return build_kb(rows)
