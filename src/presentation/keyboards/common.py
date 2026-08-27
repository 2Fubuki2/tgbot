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
        [("📬 Напоминания", "treasurer_remind")],
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
        [("📋 Все участники", "admin_user_list")],
        [("🔍 Поиск", "admin_user_search")],
        [MAIN_MENU_BTN],
    ])


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
        [("💳 Принять оплату", f"treasurer_pay:{user_id}")],
        [("⚠️ Начислить штраф", f"fine_issue:{user_id}")],
        [("📬 Отправить напоминание", f"remind_user:{user_id}")],
        [BACK_BTN],
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


# ─── Подтверждение ─────────────────────────────────
def confirm_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    return build_kb([
        [("✅ Да", callback_data)],
        [("❌ Нет", "back")],
    ])
