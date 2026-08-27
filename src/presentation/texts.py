from src.config.settings import settings

# ─── Главное меню ──────────────────────────────────
MENU_MAIN = "🏠 Главное меню"
BACK_TO_MAIN = "🔙 В главное меню"
BACK = "🔙 Назад"


# ─── Тексты для участника ──────────────────────────
def member_profile_text(full_name: str, role: str, debt: str, fines: str, total: str, credit: str) -> str:
    return (
        f"👤 <b>{full_name}</b>\n"
        f"📌 Статус: {role}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 Текущий долг: <b>{debt}</b>\n"
        f"⚠️ Штрафы: <b>{fines}</b>\n"
        f"💳 Всего к оплате: <b>{total}</b>\n"
        f"🔄 Переплата: <b>{credit}</b>"
    )


def account_statement_text(
    full_name: str,
    current_debt: str,
    fines_total: str,
    total_due: str,
    credit: str,
    paid_months: list[str],
    unpaid_months: list[str],
) -> str:
    paid_str = "\n".join(f"✅ {m}" for m in paid_months) if paid_months else "Нет оплаченных месяцев"
    unpaid_str = "\n".join(f"❌ {m}" for m in unpaid_months) if unpaid_months else "Нет долгов"

    return (
        f"╔══════════════════════╗\n"
        f"║  <b>Лицевой счёт</b>      ║\n"
        f"║  {full_name}          \n"
        f"╠══════════════════════╣\n"
        f"║  Текущий долг: {current_debt}  \n"
        f"║  Штрафы: {fines_total}        \n"
        f"║  Итого: {total_due}           \n"
        f"║  Переплата: {credit}          \n"
        f"╠══════════════════════╣\n"
        f"║ <b>Оплаченные месяцы</b>:\n"
        f"{paid_str}\n"
        f"║──────────────────────║\n"
        f"║ <b>Задолженность</b>:\n"
        f"{unpaid_str}\n"
        f"╚══════════════════════╝"
    )


# ─── Тексты для казначея ──────────────────────────
def fee_assessment_result(assessed: int, total_amount: str) -> str:
    return (
        f"✅ <b>Взносы начислены!</b>\n"
        f"Участников: {assessed}\n"
        f"Общая сумма: <b>{total_amount}</b>"
    )


def no_fee_needed() -> str:
    return "ℹ️ Взносы за текущий месяц уже были начислены ранее."


def pending_payment_text(
    user_name: str,
    amount: str,
    month: int,
    year: int,
    comment: str | None,
    payment_method: str | None,
) -> str:
    text = (
        f"💰 <b>Новый платёж</b>\n"
        f"👤 {user_name}\n"
        f"💵 Сумма: <b>{amount}</b>\n"
        f"📅 За: {month}/{year}\n"
    )
    if payment_method:
        text += f"💳 Способ: {payment_method}\n"
    if comment:
        text += f"💬 {comment}"
    return text


def debt_reminder_text(total_debt: str, fees: str, fines: str, payment_details: str) -> str:
    return (
        f"📌 <b>Напоминание о задолженности</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 Взносы: <b>{fees}</b>\n"
        f"⚠️ Штрафы: <b>{fines}</b>\n"
        f"💳 Всего к оплате: <b>{total_debt}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>Реквизиты для оплаты:</b>\n"
        f"{payment_details}\n\n"
        f"После оплаты нажми 📤 <b>Я оплатил</b> в меню"
    )


# ─── Статистика ──────────────────────────────────
def stats_text(
    balance: str,
    revenue: str,
    expenses: str,
    adjustment: str,
    debt: str,
    debtors_count: int,
    active_members: int,
    fines_total: str,
) -> str:
    return (
        f"📊 <b>Статистика казны</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 Баланс казны: <b>{balance}</b>\n"
        f"📈 Поступления: <b>{revenue}</b>\n"
        f"📉 Расходы: <b>{expenses}</b>\n"
        f"🔧 Коррекция казны: <b>{adjustment}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📌 Общий долг: <b>{debt}</b>\n"
        f"👥 Должников: <b>{debtors_count}</b>\n"
        f"👤 Активных: <b>{active_members}</b>\n"
        f"⚠️ Штрафов: <b>{fines_total}</b>"
    )


# ─── Ошибки ──────────────────────────────────
ACCESS_DENIED = "⛔ У вас нет доступа к этой функции."
ERROR_GENERIC = "❌ Произошла ошибка. Попробуйте позже."
ERROR_NOT_FOUND = "❌ Запись не найдена."
