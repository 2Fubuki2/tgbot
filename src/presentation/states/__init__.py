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


class ExpenseEditStates(StatesGroup):
    """FSM для редактирования расхода."""
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
    waiting_assessment_day = State()


class AddUserStates(StatesGroup):
    """FSM для добавления пользователя (админ)."""
    waiting_telegram_id = State()
    waiting_full_name = State()
    waiting_role = State()


# ─── Начисление взносов (казначей/админ) ──────────
class AssessFeesStates(StatesGroup):
    """FSM для ручного начисления взносов."""
    waiting_period = State()  # month.year
    waiting_amount = State()
    waiting_comment = State()


# ─── Корректировка баланса казны (админ) ──────────
class TreasuryAdjustStates(StatesGroup):
    """FSM для корректировки баланса казны."""
    waiting_adjustment = State()


# ─── Изменение никнейма (админ) ─────────────────
class RenameUserStates(StatesGroup):
    """FSM для изменения никнейма участника."""
    waiting_new_name = State()


# ─── Рассылка (админ) ──────────────────────────
class BroadcastStates(StatesGroup):
    """FSM для рассылки сообщений."""
    waiting_text = State()


# ─── Редактирование истории (админ) ─────────────
class LedgerEditStates(StatesGroup):
    """FSM для редактирования платежей, штрафов и взносов."""
    # Payments
    edit_payment_amount = State()
    edit_payment_month = State()
    edit_payment_comment = State()
    # Fines
    edit_fine_amount = State()
    edit_fine_reason = State()
    edit_fine_comment = State()
    # Fees
    edit_fee_amount = State()
    edit_fee_month = State()
    edit_fee_status = State()
