from aiogram.fsm.state import State, StatesGroup


# ─── Платежи ────────────────────────────────────
class PaymentStates(StatesGroup):
    """FSM для процесса 'Я оплатил'."""
    waiting_amount = State()
    waiting_month = State()
    waiting_receipt = State()
    waiting_comment = State()


class PaymentConfirmStates(StatesGroup):
    """FSM для отклонения платежа (с причиной)."""
    waiting_rejection_reason = State()


# ─── Штрафы ─────────────────────────────────────
class FineStates(StatesGroup):
    """FSM для начисления штрафа."""
    waiting_amount = State()
    waiting_reason = State()
    waiting_comment = State()


class FineCancelStates(StatesGroup):
    """FSM для отмены штрафа."""
    waiting_comment = State()


# ─── Расходы ────────────────────────────────────
class ExpenseStates(StatesGroup):
    """FSM для добавления расхода."""
    waiting_amount = State()
    waiting_category = State()
    waiting_comment = State()
    waiting_date = State()


# ─── Настройки (админ) ──────────────────────────
class SettingsStates(StatesGroup):
    """FSM для изменения настроек."""
    waiting_fee = State()
    waiting_details = State()
    waiting_club_name = State()


class AddUserStates(StatesGroup):
    """FSM для добавления пользователя (админ)."""
    waiting_telegram_id = State()
    waiting_full_name = State()
    waiting_role = State()


class SearchUserStates(StatesGroup):
    """FSM для поиска пользователя (админ)."""
    waiting_query = State()
