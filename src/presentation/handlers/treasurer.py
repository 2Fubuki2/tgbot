from __future__ import annotations

from datetime import datetime
import logging
from decimal import Decimal

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.config.settings import settings
from src.domain.value_objects.payment_status import PaymentStatus
from src.domain.value_objects.role import UserRole
from src.domain.value_objects.fee_status import FeeStatus
from src.domain.value_objects.fine_status import FineStatus


# ─── Russian status labels for UI ─────────────────
def _payment_status_ru(status: PaymentStatus) -> str:
    return {
        PaymentStatus.PENDING: "ожидает",
        PaymentStatus.CONFIRMED: "подтверждён",
        PaymentStatus.REJECTED: "отклонён",
    }.get(status, status.value)


def _fee_status_ru(status: FeeStatus) -> str:
    return {
        FeeStatus.PENDING: "ожидает",
        FeeStatus.PAID: "оплачен",
        FeeStatus.WAIVED: "списан",
    }.get(status, status.value)


def _fine_status_ru(status: FineStatus) -> str:
    return {
        FineStatus.ACTIVE: "активен",
        FineStatus.CANCELLED: "оплачен",
    }.get(status, status.value)
from src.infrastructure.database.session import get_session
from src.infrastructure.database.models.user import UserModel
from src.infrastructure.database.models.monthly_fee import MonthlyFeeModel
from src.infrastructure.database.models.fine import FineModel
from src.infrastructure.database.models.payment import PaymentModel
from src.infrastructure.database.models.settings import ClubSettingsModel
from src.infrastructure.repositories.user_repository import UserRepository
from src.infrastructure.repositories.fee_repository import FeeRepository
from src.infrastructure.repositories.fine_repository import FineRepository
from src.infrastructure.repositories.payment_repository import PaymentRepository
from src.infrastructure.repositories.settings_repository import ClubSettingsRepository
from src.infrastructure.repositories.audit_repository import AuditLogRepository
from src.domain.entities.audit_log import AuditLog
from src.domain.entities.monthly_fee import MonthlyFee
from src.presentation.keyboards.common import (
    main_menu_keyboard,
    members_list_keyboard,
    member_detail_keyboard,
    member_detail_admin_keyboard,
    payment_action_keyboard,
    back_keyboard,
    build_kb,
    assess_fees_keyboard,
    fine_allocation_keyboard,
    timeline_user_select_keyboard,
)
from src.presentation.states import AssessFeesStates
from src.domain.entities.payment import Payment
from src.presentation.texts import (
    pending_payment_text,
    fee_assessment_result,
    no_fee_needed,
    debt_reminder_text,
    stats_text,
)
from src.infrastructure.timezone import now_msk
from src.presentation.utils import safe_edit, send_text_replacing_photo, require_role, require_treasurer_or_admin

router = Router()

logger = logging.getLogger(__name__)


# ─── Участник: просмотр себя ──────────────────────

@router.callback_query(F.data == "member_account")
async def member_account(callback: CallbackQuery) -> None:
    """Show member's account statement."""
    async for session in get_session():
        user_repo = UserRepository(session)
        fee_repo = FeeRepository(session)
        fine_repo = FineRepository(session)

        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user or user.id is None or user.id is None:
            await callback.answer("❌ Не найден")
            return

        fees = await fee_repo.list_pending_by_user(user.id)
        fines = await fine_repo.list_active_by_user(user.id)

        fees_total = sum((f.remaining_amount for f in fees), Decimal("0"))
        fines_total = sum((f.remaining_amount for f in fines), Decimal("0"))
        total = fees_total + fines_total

        all_fees = await fee_repo.list_by_user(user.id)
        paid_months = []
        unpaid_months = []
        for f in all_fees:
            label = f"{f.month:02d}/{f.year}"
            if f.status == FeeStatus.PAID:
                paid_months.append(label)
            else:
                unpaid_months.append(label)

        text = (
            f"📋 <b>Лицевой счёт</b>\n"
            f"👤 {user.full_name}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💰 Долг по взносам: <b>{fees_total:,.2f}₽</b>\n"
            f"⚠️ Штрафы: <b>{fines_total:,.2f}₽</b>\n"
            f"💳 <b>Всего к оплате: {total:,.2f}₽</b>\n"
            f"🔄 Переплата: <b>{user.balance_credit:,.2f}₽</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
        )

        if paid_months:
            text += "✅ <b>Оплачено:</b> " + ", ".join(paid_months[:6]) + "\n"
        if unpaid_months:
            text += "❌ <b>Долг:</b> " + ", ".join(unpaid_months[:6])

        await safe_edit(callback, text, reply_markup=back_keyboard())

    await callback.answer()


@router.callback_query(F.data == "member_payments")
async def member_payments(callback: CallbackQuery) -> None:
    """Show member's payment history."""
    async for session in get_session():
        user_repo = UserRepository(session)
        pay_repo = PaymentRepository(session)

        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user or user.id is None:
            await callback.answer("❌ Не найден")
            return

        payments = await pay_repo.list_by_user(user.id)
        fees = await fee_repo.list_by_user(user.id)

        # Корреляция платежей с платежами по period
        fee_by_period: dict[tuple[int, int], MonthlyFee] = {}
        for f in fees:
            fee_by_period[(f.month, f.year)] = f

        if not payments:
            text = "📭 У вас пока нет платежей."
        else:
            lines = ["<b>История платежей:</b>\n"]
            for p in payments[:20]:
                status_icon = {
                PaymentStatus.PENDING: "⏳",
                PaymentStatus.CONFIRMED: "✅",
                PaymentStatus.REJECTED: "❌",
            }
                icon = status_icon.get(p.status, "❓")
                date_str = p.payment_date.strftime("%d.%m.%Y") if p.payment_date else f"{p.month:02d}/{p.year}"
                fee = fee_by_period.get((p.month, p.year))
                if fee and p.amount < fee.amount and p.status == PaymentStatus.CONFIRMED:
                    lines.append(
                        f"{icon} <b>{p.amount:,.2f}₽</b>/{fee.amount:,.2f}₽ "
                        f"{date_str} — {_payment_status_ru(p.status)}"
                    )
                    lines.append(
                        f"   📋 Частичное погашение · "
                        f"взнос {fee.month:02d}/{fee.year}: "
                        f"остаток <b>{fee.remaining_amount:,.2f}₽</b>"
                    )
                else:
                    lines.append(
                        f"{icon} <b>{p.amount:,.2f}₽</b> {date_str}"
                        f" — {_payment_status_ru(p.status)}"
                    )
            text = "\n".join(lines)

        await safe_edit(callback, text, reply_markup=back_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("member_payments:"))
async def member_payments_for_user(callback: CallbackQuery) -> None:
    """Show payment history for the selected member from treasurer/admin views."""
    user_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        user_repo = UserRepository(session)
        pay_repo = PaymentRepository(session)

        user = await user_repo.get_by_id(user_id)
        if not user or user.id is None:
            await callback.answer("❌ Пользователь не найден")
            return

        payments = await pay_repo.list_by_user(user.id)
        fees = await fee_repo.list_by_user(user.id)

        fee_by_period: dict[tuple[int, int], MonthlyFee] = {}
        for f in fees:
            fee_by_period[(f.month, f.year)] = f

        if not payments:
            text = f"📭 У пользователя <b>{user.full_name}</b> пока нет платежей."
        else:
            lines = [f"<b>История платежей {user.full_name}:</b>\n"]
            for p in payments[:20]:
                status_icon = {
                PaymentStatus.PENDING: "⏳",
                PaymentStatus.CONFIRMED: "✅",
                PaymentStatus.REJECTED: "❌",
            }
                icon = status_icon.get(p.status, "❓")
                date_str = p.payment_date.strftime("%d.%m.%Y") if p.payment_date else f"{p.month:02d}/{p.year}"
                fee = fee_by_period.get((p.month, p.year))
                if fee and p.amount < fee.amount and p.status == PaymentStatus.CONFIRMED:
                    lines.append(
                        f"{icon} <b>{p.amount:,.2f}₽</b>/{fee.amount:,.2f}₽ "
                        f"{date_str} — {_payment_status_ru(p.status)}"
                    )
                    lines.append(
                        f"   📋 Частичное погашение · "
                        f"взнос {fee.month:02d}/{fee.year}: "
                        f"остаток <b>{fee.remaining_amount:,.2f}₽</b>"
                    )
                else:
                    lines.append(
                        f"{icon} <b>{p.amount:,.2f}₽</b> {date_str}"
                        f" — {_payment_status_ru(p.status)}"
                    )
            text = "\n".join(lines)

        await safe_edit(callback, text, reply_markup=back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "member_fines")
async def member_fines(callback: CallbackQuery) -> None:
    """Show member's fines."""
    async for session in get_session():
        user_repo = UserRepository(session)
        fine_repo = FineRepository(session)

        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user or user.id is None:
            await callback.answer("❌ Не найден")
            return

        fines = await fine_repo.list_by_user(user.id)

        if not fines:
            text = "✅ У вас нет штрафов."
            keyboard = back_keyboard()
        else:
            lines = ["<b>Штрафы:</b>\n"]
            keyboard_rows = []
            for f in fines:
                remaining = f.remaining_amount
                status_icon = "⚠️" if f.status == FineStatus.ACTIVE and remaining > 0 else "✅"
                lines.append(
                    f"{status_icon} <b>{remaining:,.2f}₽</b> / {f.amount:,.2f}₽ — {f.reason}"
                )
                if f.status == FineStatus.ACTIVE and remaining > 0:
                    keyboard_rows.append([("💳 Оплатить штраф", f"pay_fine:{f.id}")])
            text = "\n".join(lines)
            keyboard = build_kb(keyboard_rows + [[("🔙 Назад", "back")]]) if keyboard_rows else back_keyboard()

        await safe_edit(callback, text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "member_fees")
async def member_fees(callback: CallbackQuery) -> None:
    """Show member's fee history."""
    async for session in get_session():
        user_repo = UserRepository(session)
        fee_repo = FeeRepository(session)

        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user or user.id is None:
            await callback.answer("❌ Не найден")
            return

        fees = await fee_repo.list_by_user(user.id)

        if not fees:
            text = "📭 У вас пока нет начислений взносов."
        else:
            lines = ["<b>Взносы:</b>\n"]
            for f in fees:
                status_icon = "✅" if f.status == FeeStatus.PAID else "⏳"
                remaining = f.remaining_amount
                if f.paid_amount > 0:
                    lines.append(
                        f"{status_icon} <b>{f.amount:,.2f}₽</b> "
                        f"({f.paid_amount:,.2f}₽) {f.month:02d}/{f.year} — "
                        f"ост. <b>{remaining:,.2f}₽</b>"
                    )
                else:
                    lines.append(
                        f"{status_icon} <b>{f.amount:,.2f}₽</b> "
                        f"{f.month:02d}/{f.year} — {f.status.value}"
                    )
            text = "\n".join(lines)

        await safe_edit(callback, text, reply_markup=back_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("member_fees:"))
async def member_fees_for_user(callback: CallbackQuery) -> None:
    """Show fee history for the selected member."""
    user_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        user_repo = UserRepository(session)
        fee_repo = FeeRepository(session)

        user = await user_repo.get_by_id(user_id)
        if not user or user.id is None:
            await callback.answer("❌ Пользователь не найден")
            return

        fees = await fee_repo.list_by_user(user.id)

        if not fees:
            text = f"📭 У пользователя <b>{user.full_name}</b> пока нет начислений взносов."
        else:
            lines = [f"<b>Взносы {user.full_name}:</b>\n"]
            for f in fees:
                status_icon = "✅" if f.status == FeeStatus.PAID else "⏳"
                remaining = f.remaining_amount
                if f.paid_amount > 0:
                    lines.append(
                        f"{status_icon} <b>{f.amount:,.2f}₽</b> "
                        f"({f.paid_amount:,.2f}₽) {f.month:02d}/{f.year} — "
                        f"ост. <b>{remaining:,.2f}₽</b>"
                    )
                else:
                    lines.append(
                        f"{status_icon} <b>{f.amount:,.2f}₽</b> "
                        f"{f.month:02d}/{f.year} — {f.status.value}"
                    )
            text = "\n".join(lines)

        await safe_edit(callback, text, reply_markup=back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "member_details")
async def member_details(callback: CallbackQuery) -> None:
    """Show payment details."""
    async for session in get_session():
        settings_repo = ClubSettingsRepository(session)
        club_settings = await settings_repo.get()

        # Use or-fallback since .get() doesn't default on None values
        payment_details = club_settings.get("payment_details") or "Не указаны"
        text = (
            f"💳 <b>Реквизиты для оплаты</b>\n\n"
            f"{payment_details}"
        )
        await safe_edit(callback, text, reply_markup=back_keyboard())
    await callback.answer()


# ─── Казначей: начисление взносов ─────────────────

@router.callback_query(F.data == "treasurer_assess_fees")
async def assess_fees(callback: CallbackQuery) -> None:
    """Show fee assessment options."""
    if not await require_treasurer_or_admin(callback):
        return
    await safe_edit(
        callback,
        "💰 <b>Начисление взносов</b>\n\n"
        "Выберите способ начисления:",
        reply_markup=assess_fees_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "assess_current")
async def assess_current_month(callback: CallbackQuery) -> None:
    """Assess fees for current month (quick mode)."""
    if not await require_treasurer_or_admin(callback):
        return
    await _assess_fees_for_period(
        callback,
        now_msk().month,
        now_msk().year,
        None,  # use default monthly fee
        None,  # no comment
    )


@router.callback_query(F.data.startswith("assess_force:"))
async def assess_force_month(callback: CallbackQuery) -> None:
    """Force re-assessment for a month (skip existing check)."""
    if not await require_treasurer_or_admin(callback):
        return
    parts = (callback.data or "").split(":")
    month = int(parts[1])
    year = int(parts[2])
    await _assess_fees_for_period(
        callback,
        month,
        year,
        None,  # use default monthly fee
        "Повторное начисление администратором",
        force=True,
    )


_MONTHS_RU_FULL = {
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}
_MONTHS_RU_SHORT = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "июн": 6, "июл": 7,
    "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}

_MONTHS_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_MONTHS_EN_SHORT = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_period(text: str) -> tuple[int, int] | None:
    """Flexible period parser: accepts '06.2025', '2025.06', 'август 26', '18.08.2026', etc."""
    t = text.strip().lower()
    if not t:
        return None

    # Try Russian month name first
    for name, month in {**_MONTHS_RU_FULL, **_MONTHS_RU_SHORT, **_MONTHS_EN, **_MONTHS_EN_SHORT}.items():
        if name in t:
            # Extract year from remaining text
            year_match = re.search(r"(20\d{2})|(\d{2})", t.replace(name, ""))
            year = int(year_match.group(0)) if year_match else now_msk().year
            if year < 100:
                year += 2000
            return month, year

    # Try DD.MM.YYYY or DD.MM.YY
    m = re.search(r"(\d{1,2})[./](\d{1,2})[./](20\d{2}|\d{2})", t)
    if m:
        day_or_month, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        if 1 <= month <= 12:
            return month, year
        # DD.MM.YYYY case: group(1) is day, group(2) is month
        if 1 <= day_or_month <= 12 and month > 12:
            return day_or_month, year

    # Try YYYY.MM or YYYY-MM or YYYY/MM
    m = re.search(r"(20\d{2})[./-](\d{1,2})", t)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return month, year

    # Try plain MM.YYYY
    m = re.search(r"(\d{1,2})[./](20\d{2})", t)
    if m:
        month, year = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return month, year

    return None


@router.callback_query(F.data == "assess_manual")
async def assess_manual_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Start manual fee assessment FSM."""
    if not await require_treasurer_or_admin(callback):
        return
    await state.set_state(AssessFeesStates.waiting_period)
    await safe_edit(
        callback,
        "✏️ <b>Ручное начисление взносов</b>\n\n"
        "Введите период в формате <b>месяц.год</b> (например: 06.2025):",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.message(AssessFeesStates.waiting_period)
async def assess_fees_period(message: Message, state: FSMContext) -> None:
    """Handle period input for manual fee assessment."""
    if message.text is None:
        return
    text = message.text.strip()
    try:
        # Parse month.year
        parts = text.split(".")
        if len(parts) != 2:
            raise ValueError
        month = int(parts[0])
        year = int(parts[1])
        if not (1 <= month <= 12 and 2000 <= year <= 2100):
            raise ValueError
        await state.update_data(assess_month=month, assess_year=year)
        await state.set_state(AssessFeesStates.waiting_amount)
        await message.answer(
            "💰 Введите <b>сумму взноса</b> на человека (число):",
            reply_markup=back_keyboard(),
        )
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте месяц.год (например: 06.2025)")


@router.message(AssessFeesStates.waiting_amount)
async def assess_fees_amount(message: Message, state: FSMContext) -> None:
    """Handle amount input for manual fee assessment."""
    if message.text is None:
        return
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
        await state.update_data(assess_amount=amount)
        await state.set_state(AssessFeesStates.waiting_comment)
        await message.answer(
            "💬 Введите <b>комментарий</b> к начислению (или /skip):",
            reply_markup=confirm_cancel_keyboard("assess_skip_comment", "back"),
        )
    except (ValueError, InvalidOperation):
        await message.answer("❌ Введите положительное число.")


@router.callback_query(AssessFeesStates.waiting_comment, F.data == "assess_skip_comment")
async def assess_skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
    """Skip comment and proceed with assessment."""
    await state.update_data(assess_comment=None)
    data = await state.get_data()
    custom_amount = data.get("assess_amount")
    await _assess_fees_for_period(
        callback,
        data["assess_month"],
        data["assess_year"],
        custom_amount,
        data.get("assess_comment"),
        force=bool(custom_amount),
    )
    await state.clear()


@router.message(AssessFeesStates.waiting_comment)
async def assess_fees_comment(message: Message, state: FSMContext) -> None:
    """Handle comment input for manual fee assessment."""
    if message.text is None:
        return
    if message.text == "/skip":
        await state.update_data(assess_comment=None)
    else:
        await state.update_data(assess_comment=message.text.strip())
    data = await state.get_data()
    custom_amount = data.get("assess_amount")
    await _assess_fees_for_period(
        message,
        data["assess_month"],
        data["assess_year"],
        custom_amount,
        data.get("assess_comment"),
        force=bool(custom_amount),
    )
    await state.clear()


async def _assess_fees_for_period(
    source,
    month: int,
    year: int,
    custom_amount: Decimal | None,
    comment: str | None,
    force: bool = False,
) -> None:
    """Assess fees for a specific month/year with optional custom amount and comment."""
    from aiogram.types import CallbackQuery, Message
    from datetime import datetime

    is_callback = isinstance(source, CallbackQuery)
    bot = source.bot if is_callback else source.bot
    user_id = source.from_user.id

    async for session in get_session():
        user_repo = UserRepository(session)
        fee_repo = FeeRepository(session)
        settings_repo = ClubSettingsRepository(session)
        audit_repo = AuditLogRepository(session)

        # Check if already assessed for this period (unless forced)
        existing_fees = await fee_repo.list_by_month(month, year)
<<<<<<< HEAD
        if existing_fees:
            text = f"ℹ️ Взносы за {month:02d}/{year} уже начислены ранее ({len(existing_fees)} участников)."
=======
        if existing_fees and not force:
            # Allow re-assessment for manual trigger, just warn
            text = (
                f"⚠️ Взносы за {month:02d}/{year} уже начислены ({len(existing_fees)} участников).\n"
                f"Начислить повторно? Будут созданы взносы только для участников без взноса за этот период."
            )
            kb = build_kb([
                [("✅ Да, начислить повторно", f"assess_force:{month}:{year}")],
                [("❌ Отмена", "back")],
            ])
            if is_callback:
                await safe_edit(source, text, reply_markup=back_keyboard())
            else:
                await source.reply(text, reply_markup=back_keyboard())
            if is_callback:
                await source.answer()
            return

        monthly_fee = custom_amount or await settings_repo.get_monthly_fee()
        members = await user_repo.list_active()

        assessed_count = 0
        for member in members:
            existing = await fee_repo.get_by_user_month(member.id, month, year)
            if existing:
                continue

            fee = MonthlyFee(
                user_id=member.id,
                amount=monthly_fee,
                month=month,
                year=year,
                status=FeeStatus.PENDING,
                comment=comment,
            )
            await fee_repo.create(fee)
            assessed_count += 1

        await settings_repo.update(last_fee_assessment=datetime(year, month, 1))

        # Audit log
        user = await user_repo.get_by_telegram_id(user_id)
        if user:
            await audit_repo.create(AuditLog(
                user_id=int(user.id) if user.id is not None else 0,
                action="assess_fees",
                entity_type="monthly_fee",
                details={
                    "count": assessed_count,
                    "month": month,
                    "year": year,
                    "amount": str(monthly_fee),
                    "comment": comment,
                },
            ))

        payment_details = await settings_repo.get_payment_details()

        # Уведомить всех участников о начислении
        for member in members:
            existing = await fee_repo.get_by_user_month(member.id, month, year)
            if existing:
                try:
                    notify_text = (
                        f"💰 <b>Начислен взнос</b>\n\n"
                        f"📅 За: {month:02d}/{year}\n"
                        f"💵 Сумма: <b>{monthly_fee:,.2f}₽</b>\n"
                    )
                    if comment:
                        notify_text += f"💬 {comment}\n"
                    notify_text += f"\n📋 <b>Реквизиты для оплаты:</b>\n{payment_details}\n\n"
                    notify_text += f"Оплатить можно через меню 💰 Мой бюджет → 📤 Я оплатил"
                    await bot.send_message(member.telegram_id, notify_text)
                except Exception:
                    logger.exception("Failed to notify member %s about fee assessment", member.telegram_id)

        total = monthly_fee * assessed_count
        result_text = fee_assessment_result(assessed_count, f"{total:,.2f}₽")
        if comment:
            result_text += f"\n💬 Комментарий: {comment}"

        if is_callback:
            await safe_edit(source, result_text, reply_markup=back_keyboard())
            await source.answer()
        else:
            await source.reply(result_text, reply_markup=back_keyboard())


# ─── Казначей: ожидающие платежи ─────────────────

@router.callback_query(F.data == "treasurer_pending")
async def list_pending_payments(callback: CallbackQuery) -> None:
    """Show pending payments for treasurer (paginated, one per page)."""
    if not await require_treasurer_or_admin(callback):
        return
    await _show_pending_page(callback, 0)


async def _show_pending_page(callback: CallbackQuery, page: int) -> None:
    """Show one pending payment at a time with navigation (including receipt photo)."""
    async for session in get_session():
        pay_repo = PaymentRepository(session)
        user_repo = UserRepository(session)

        payments = await pay_repo.list_pending()

        if not payments:
            try:
                await safe_edit(
                    callback,
                    "✅ Нет ожидающих платежей.",
                    reply_markup=back_keyboard(),
                )
            except Exception:
                await callback.message.answer(
                    "✅ Нет ожидающих платежей.",
                    reply_markup=back_keyboard(),
                )
            break

        if page < 0 or page >= len(payments):
            page = 0

        p = payments[page]
        payer = await user_repo.get_by_id(p.user_id)

        # Build detailed user info: Name (@username) — Role
        if payer:
            role_label = {
                "admin": "Администратор",
                "treasurer": "Казначей",
                "member": "Участник",
            }.get(payer.role.value, payer.role.value)
            user_tag = f"@{payer.username}" if payer.username else f"id{payer.telegram_id}"
            name = f"{payer.full_name} ({user_tag}) — {role_label}"
        else:
            name = f"ID:{p.user_id}"

        date_str = p.payment_date.strftime("%d.%m.%Y") if p.payment_date else f"{p.month:02d}/{p.year}"
        text = (
            f"📨 <b>Ожидающие платежи</b> ({page + 1}/{len(payments)})\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 {name}\n"
            f"💰 <b>{p.amount:,.2f}₽</b> {date_str}\n"
        )
        if p.comment:
            text += f"💬 {p.comment}\n"
        if p.payment_method:
            text += f"💳 {p.payment_method}\n"

        # Build navigation + action buttons (include "Мой бюджет")
        kb_rows = [[("✅ Подтвердить", f"payment_confirm:{p.id}"),
                     ("❌ Отклонить", f"payment_reject:{p.id}")]]
        nav = []
        if page > 0:
            nav.append(("⬅️", f"pending_page:{page - 1}"))
        if page < len(payments) - 1:
            nav.append(("➡️", f"pending_page:{page + 1}"))
        if nav:
            kb_rows.append(nav)
        kb_rows.append([("📋 Мой бюджет", "my_budget"), ("🔙 Назад", "back")])

        # If receipt photo exists, send as photo. To keep the chat clean, replace
        # the previously shown photo message instead of stacking new ones.
        if p.receipt_photo_id:
            current_photo_id = None
            if callback.message and callback.message.photo:
                current_photo_id = callback.message.photo[-1].file_id  # largest size

            # Same receipt already on screen -> just update the caption
            if current_photo_id == p.receipt_photo_id:
                try:
                    await callback.message.edit_caption(
                        caption=text,
                        reply_markup=build_kb(kb_rows),
                    )
                except Exception:
                    await callback.message.answer_photo(
                        p.receipt_photo_id,
                        caption=text,
                        reply_markup=build_kb(kb_rows),
                    )
            else:
                # Different payment/receipt -> delete old photo message, send the correct one.
                # The old message may be a text menu (first navigation) or another payment's photo.
                old_msg = callback.message
                new_msg = await old_msg.answer_photo(
                    p.receipt_photo_id,
                    caption=text,
                    reply_markup=build_kb(kb_rows),
                )
                # Delete the stale message only if it is a photo we replaced,
                # to avoid deleting the original "club budget" menu message.
                if old_msg and old_msg.photo:
                    try:
                        await old_msg.delete()
                    except Exception:
                        logger.exception("Failed to delete stale pending photo message")
        else:
            try:
                await safe_edit(callback, text, reply_markup=build_kb(kb_rows))
            except Exception:
                await callback.message.answer(text, reply_markup=build_kb(kb_rows))

    await callback.answer()


@router.callback_query(F.data.startswith("pending_page:"))
async def pending_page(callback: CallbackQuery) -> None:
    """Navigate between pending payment pages."""
    if not await require_treasurer_or_admin(callback):
        return
    page = int((callback.data or "").split(":")[1])
    await _show_pending_page(callback, page)


# ─── Подтверждение/отклонение платежа (коллбэки) ─

@router.callback_query(F.data.startswith("payment_confirm:"))
async def confirm_payment(callback: CallbackQuery) -> None:
    if not await require_treasurer_or_admin(callback):
        return
    payment_id = int((callback.data or "").split(":")[1])
    succeeded = False
    affected_fee_ids: list[int] = []
    try:
        async for session in get_session():
            pay_repo = PaymentRepository(session)
            fee_repo = FeeRepository(session)
            audit_repo = AuditLogRepository(session)
            user_repo = UserRepository(session)

            logger.info("confirm_payment: processing payment_id=%s by user=%s", payment_id, callback.from_user.id)
            payment = await pay_repo.get_by_id(payment_id)
            if not payment:
                await callback.answer("❌ Платёж не найден")
                break

            fine_repo = FineRepository(session)
            admin = await user_repo.get_by_telegram_id(callback.from_user.id)
            payment.status = PaymentStatus.CONFIRMED
            payment.confirmed_by = admin.id if admin else None
            payment.confirmed_at = now_msk()

            # Update user's balance_credit and apply to fee if exists
            user_model = await user_repo.get_by_id(payment.user_id)
            if user_model:
                logger.info("confirm_payment: user %s balance before=%s", user_model.id, user_model.balance_credit)

                if payment.payment_type == "fine":
                    active_fines = await fine_repo.list_active_by_user(payment.user_id)
                    # If multiple active fines, defer allocation to fine_allocate handler
                    if len(active_fines) > 1:
                        # Save payment as confirmed but not yet allocated
                        # We'll hold the amount in a pending state — but simpler: just keep PENDING
                        # Actually, let's keep PENDING and show allocation keyboard
                        payment.status = PaymentStatus.PENDING
                        await pay_repo.update(payment)
                        await callback.message.edit_text(
                            f"⚠️ <b>У участника {len(active_fines)} активных штрафов.</b>\n"
                            f"Выберите, на какой штраф направить платёж <b>{payment.amount:,.2f}₽</b>:",
                            reply_markup=fine_allocation_keyboard(payment_id, active_fines),
                            parse_mode="HTML",
                        )
                        await callback.answer()
                        return
                    # Single or no active fine — apply directly
                    remaining_to_apply = Decimal(payment.amount)
                    for fine in active_fines:
                        if remaining_to_apply <= 0:
                            break
                        alloc = min(remaining_to_apply, fine.remaining_amount)
                        if alloc <= 0:
                            continue
                        fine.paid_amount = (fine.paid_amount or Decimal('0')) + alloc
                        if fine.paid_amount >= fine.amount:
                            fine.status = FineStatus.CANCELLED
                            fine.cancelled_at = now_msk()
                        await fine_repo.update(fine)
                        remaining_to_apply -= alloc
                    if remaining_to_apply > 0:
                        user_model.balance_credit = (user_model.balance_credit or Decimal('0')) + remaining_to_apply
                else:
                    # Fee payment: add to balance, then apply to ALL fees with remaining amount
                    user_model.balance_credit = (user_model.balance_credit or Decimal('0')) + Decimal(payment.amount)
                    # Get unpaid fees sorted oldest first (FIFO)
                    all_fees = await fee_repo.list_pending_by_user(payment.user_id)
                    for fee in all_fees:
                        if user_model.balance_credit <= 0:
                            break
                        remaining = fee.remaining_amount
                        if remaining <= 0:
                            continue
                        apply = min(user_model.balance_credit, remaining)
                        if apply > 0:
                            user_model.balance_credit -= apply
                            fee.paid_amount = (fee.paid_amount or Decimal('0')) + apply
                            if fee.paid_amount >= fee.amount:
                                fee.status = FeeStatus.PAID
                                fee.paid_at = now_msk()
                            await fee_repo.update(fee)
                            affected_fee_ids.append(fee.id)

                await user_repo.update(user_model)

            await pay_repo.update(payment)

            # Audit
            if admin:
                await audit_repo.create(AuditLog(
                    user_id=int(admin.id) if admin.id is not None else 0,
                    action="confirm_payment",
                    entity_type="payment",
                    entity_id=payment.id,
                    details={"user_id": payment.user_id, "amount": str(payment.amount)},
                ))

            try:
                await send_text_replacing_photo(
                    callback,
                    f"✅ Платёж {payment_id} подтверждён!",
                    reply_markup=back_keyboard(),
                )
            except Exception:
                await callback.message.answer(
                    f"✅ Платёж {payment_id} подтверждён!",
                    reply_markup=back_keyboard(),
                )

            # Build detailed notification for the user
            try:
                bot = callback.bot
                user_model = await user_repo.get_by_id(payment.user_id)
                if user_model and payment.payment_type == "fee":
                    # Re-fetch affected fees to get updated paid_amount and status
                    if affected_fee_ids:
                        fee_details = []
                        total_remaining = Decimal("0")
                        for fid in affected_fee_ids:
                            f = await fee_repo.get_by_id(fid)
                            if f:
                                rem = f.remaining_amount
                                total_remaining += rem
                                period = f"{f.month:02d}/{f.year}" if f.month and f.year else "?"
                                if f.status == FeeStatus.PAID:
                                    fee_details.append(f"📅 {period} — <b>погашен</b>")
                                else:
                                    fee_details.append(f"📅 {period} — оплачено <b>{f.paid_amount:,.2f}₽</b> из <b>{f.amount:,.2f}₽</b> (ост. {rem:,.2f}₽)")
                        if total_remaining > 0:
                            detail_text = (
                                f"\n\n💳 <b>Частично погашен:</b>\n"
                                + "\n".join(fee_details)
                                + f"\n\n📊 Остаток долга: <b>{total_remaining:,.2f}₽</b>"
                            )
                        else:
                            detail_text = (
                                f"\n\n🎉 <b>Долг полностью погашен!</b>\n"
                                + "\n".join(fee_details)
                            )
                    else:
                        detail_text = ""
                else:
                    detail_text = ""

                await bot.send_message(
                    user_model.telegram_id,
                    f"✅ Ваш платёж на <b>{payment.amount:,.2f}₽</b> подтверждён казначеем!{detail_text}",
                )
            except Exception as exc:
                logger.exception("confirm_payment: failed to notify user %s: %s", payment.user_id, exc)

            succeeded = True

        if succeeded:
            await callback.answer()
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


@router.callback_query(F.data.startswith("payment_reject:"))
async def reject_payment(callback: CallbackQuery) -> None:
    if not await require_treasurer_or_admin(callback):
        return
    payment_id = int((callback.data or "").split(":")[1])
    # Получаем причину отказа из callback data, если она есть
    # Формат: payment_reject:payment_id:reason
    parts = (callback.data or "").split(":")
    reject_reason = parts[2] if len(parts) > 2 else None
    succeeded = False
    try:
        logger.info("reject_payment: processing payment_id=%s by user=%s", payment_id, callback.from_user.id)
        async for session in get_session():
            pay_repo = PaymentRepository(session)
            user_repo = UserRepository(session)

            payment = await pay_repo.get_by_id(payment_id)
            if not payment:
                await callback.answer("❌ Платёж не найден")
                break

            admin = await user_repo.get_by_telegram_id(callback.from_user.id)
            payment.status = PaymentStatus.REJECTED
            payment.rejection_reason = reject_reason
            payment.confirmed_by = admin.id if admin else None
            payment.confirmed_at = now_msk()
            await pay_repo.update(payment)

            try:
                await send_text_replacing_photo(
                    callback,
                    f"❌ Платёж {payment_id} отклонён.",
                    reply_markup=back_keyboard(),
                )
            except Exception:
                await callback.message.answer(
                    f"❌ Платёж {payment_id} отклонён.",
                    reply_markup=back_keyboard(),
                )
            logger.info("reject_payment: payment %s marked rejected", payment_id)

            # Уведомить пользователя об отклонении
            try:
                user_model = await user_repo.get_by_id(payment.user_id)
                if user_model:
                    reason_text = f"\n📝 Причина: {reject_reason}" if reject_reason else ""
                    await callback.bot.send_message(
                        user_model.telegram_id,
                        f"❌ <b>Платёж отклонён</b>\n\n"
                        f"💰 Сумма: <b>{payment.amount:,.2f}₽</b>\n"
                        f"📅 За: {payment.month:02d}/{payment.year}{reason_text}\n\n"
                        f"Пожалуйста, свяжитесь с казначеем для уточнения.",
                    )
            except Exception:
                logger.exception("Failed to notify user %s about rejected payment", payment.user_id)

            succeeded = True
        if succeeded:
            await callback.answer()
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


# ─── Казначей: список участников ─────────────────

@router.callback_query(F.data == "treasurer_members")
async def list_members(callback: CallbackQuery) -> None:
    if not await require_treasurer_or_admin(callback):
        return
    async for session in get_session():
        user_repo = UserRepository(session)
        members = await user_repo.list_active()

        if not members:
            await safe_edit(
                callback,
                "📭 Нет активных участников.",
                reply_markup=back_keyboard(),
            )
            await callback.answer()
            return

        users_list = [(int(m.id) if m.id is not None else 0, f"{m.full_name}") for m in members]
        await safe_edit(
            callback,
            f"👥 <b>Участники клуба</b> ({len(members)}):",
            reply_markup=members_list_keyboard(users_list),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("members_page:"))
async def members_page(callback: CallbackQuery) -> None:
    page = int((callback.data or "").split(":")[1])
    async for session in get_session():
        user_repo = UserRepository(session)
        members = await user_repo.list_active()
        users_list = [(int(m.id) if m.id is not None else 0, f"{m.full_name}") for m in members]
        await safe_edit(
            callback,
            f"👥 <b>Участники клуба</b> ({len(members)}):",
            reply_markup=members_list_keyboard(users_list, page),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("member_view:"))
async def view_member(callback: CallbackQuery) -> None:
    user_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        user_repo = UserRepository(session)
        fee_repo = FeeRepository(session)
        fine_repo = FineRepository(session)

        member = await user_repo.get_by_id(user_id)
        if not member or member.id is None:
            await callback.answer("❌ Не найден")
            return

        fees = await fee_repo.list_pending_by_user(user_id)
        fines = await fine_repo.list_active_by_user(user_id)

        fees_total = sum((f.remaining_amount for f in fees), Decimal("0"))
        fines_total = sum((f.remaining_amount for f in fines), Decimal("0"))

        text = (
            f"👤 <b>{member.full_name}</b>\n"
            f"📌 Статус: {member.status.value}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💰 Долг: <b>{fees_total:,.2f}₽</b>\n"
            f"⚠️ Штрафы: <b>{fines_total:,.2f}₽</b>\n"
            f"🔄 Переплата: <b>{member.balance_credit:,.2f}₽</b>\n"
            f"📅 В клубе с: {member.joined_at.strftime('%d.%m.%Y') if member.joined_at else '?'}"
        )

        # Use admin keyboard if the caller is an admin
        caller = await user_repo.get_by_telegram_id(callback.from_user.id)
        use_admin_kb = caller and caller.role == UserRole.ADMIN
        await safe_edit(
            callback,
            text,
            reply_markup=member_detail_admin_keyboard(user_id) if use_admin_kb else member_detail_keyboard(user_id),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("remind_user:"))
async def remind_user(callback: CallbackQuery) -> None:
    """Send a debt reminder to one selected member."""
    user_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        user_repo = UserRepository(session)
        fee_repo = FeeRepository(session)
        fine_repo = FineRepository(session)
        settings_repo = ClubSettingsRepository(session)

        user = await user_repo.get_by_id(user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        fees = await fee_repo.list_pending_by_user(user.id)
        fines = await fine_repo.list_active_by_user(user.id)
        fees_total = sum((f.remaining_amount for f in fees), Decimal("0"))
        fines_total = sum((f.amount for f in fines), Decimal("0"))
        total = fees_total + fines_total

        if total <= 0:
            await safe_edit(
                callback,
                f"✅ У {user.full_name} нет задолженности.",
                reply_markup=back_keyboard(),
            )
            await callback.answer()
            return

        payment_details = await settings_repo.get_payment_details()
        try:
            await callback.bot.send_message(
                user.telegram_id,
                debt_reminder_text(
                    f"{total:,.2f}₽",
                    f"{fees_total:,.2f}₽",
                    f"{fines_total:,.2f}₽",
                    payment_details,
                ),
            )
            await safe_edit(
                callback,
                f"📬 Напоминание отправлено <b>{user.full_name}</b>.",
                reply_markup=back_keyboard(),
            )
        except Exception:
            await safe_edit(
                callback,
                f"⚠️ Не удалось отправить напоминание <b>{user.full_name}</b>.",
                reply_markup=back_keyboard(),
            )
    await callback.answer()


# ─── Казначей: статистика ────────────────────────

@router.callback_query(F.data == "treasurer_stats")
async def show_stats(callback: CallbackQuery) -> None:
    if not await require_treasurer_or_admin(callback):
        return
    async for session in get_session():
        pay_repo = PaymentRepository(session)
        fee_repo = FeeRepository(session)
        fine_repo = FineRepository(session)
        exp_repo = __import__("src.infrastructure.repositories.expense_repository", fromlist=["ExpenseRepository"])
        from src.infrastructure.repositories.expense_repository import ExpenseRepository
        exp_repo = ExpenseRepository(session)
        user_repo = UserRepository(session)

        total_revenue = await pay_repo.total_confirmed_amount()
        total_expenses = await exp_repo.total_amount()
        total_pending_fees = await fee_repo.total_pending_amount()
        total_active_fines = await fine_repo.total_active_amount()
        total_debt = total_pending_fees + total_active_fines
        settings_repo = ClubSettingsRepository(session)
        adjustment = await settings_repo.get_treasury_adjustment()
        balance = total_revenue - total_expenses + adjustment
        debtors = await user_repo.count_debtors()
        active = await user_repo.count_active()

        text = stats_text(
            f"{balance:,.2f}₽",
            f"{total_revenue:,.2f}₽",
            f"{total_expenses:,.2f}₽",
            f"{adjustment:,.2f}₽",
            f"{total_debt:,.2f}₽",
            debtors,
            active,
            f"{total_active_fines:,.2f}₽",
        )
        await safe_edit(callback, text, reply_markup=back_keyboard())
    await callback.answer()


# ─── Казначей: напоминания ───────────────────────

@router.callback_query(F.data == "treasurer_remind")
async def send_reminders(callback: CallbackQuery) -> None:
    """Send debt reminders to all debtors."""
    if not await require_treasurer_or_admin(callback):
        return
    async for session in get_session():
        user_repo = UserRepository(session)
        fee_repo = FeeRepository(session)
        fine_repo = FineRepository(session)
        settings_repo = ClubSettingsRepository(session)

        members = await user_repo.list_active()
        payment_details = await settings_repo.get_payment_details()
        sent = 0

        for member in members:
            fees = await fee_repo.list_pending_by_user(member.id)
            fines = await fine_repo.list_active_by_user(member.id)

            fees_total = sum((f.remaining_amount for f in fees), Decimal("0"))
            fines_total = sum((f.remaining_amount for f in fines), Decimal("0"))
            total = fees_total + fines_total

            if total <= 0:
                continue

            try:
                await callback.bot.send_message(
                    member.telegram_id,
                    debt_reminder_text(
                        f"{total:,.2f}₽",
                        f"{fees_total:,.2f}₽",
                        f"{fines_total:,.2f}₽",
                        payment_details,
                    ),
                )
                sent += 1
            except Exception:
                logger.exception("Failed to send reminder to member %s", member.telegram_id)

        await safe_edit(
            callback,
            f"📬 Напоминания отправлены <b>{sent}</b> должникам.",
            reply_markup=back_keyboard(),
        )
    await callback.answer()


# ─── Распределение платежа по штрафам ──────────

@router.callback_query(F.data.startswith("fine_allocate:"))
async def fine_allocate(callback: CallbackQuery) -> None:
    """Allocate a fine-type payment to a specific fine."""
    if not await require_treasurer_or_admin(callback):
        return
    parts = (callback.data or "").split(":")
    payment_id = int(parts[1])
    fine_id = int(parts[2])
    succeeded = False
    try:
        async for session in get_session():
            pay_repo = PaymentRepository(session)
            fine_repo = FineRepository(session)
            user_repo = UserRepository(session)
            audit_repo = AuditLogRepository(session)

            payment = await pay_repo.get_by_id(payment_id)
            if not payment:
                await callback.answer("❌ Платёж не найден", show_alert=True)
                break

            fine = await fine_repo.get_by_id(fine_id)
            if not fine or fine.status != FineStatus.ACTIVE:
                await callback.answer("❌ Штраф не найден или уже оплачен", show_alert=True)
                break

            if payment.user_id != fine.user_id:
                await callback.answer("❌ Платёж и штраф — разные участники", show_alert=True)
                break

            alloc = min(Decimal(payment.amount), fine.remaining_amount)
            fine.paid_amount = (fine.paid_amount or Decimal('0')) + alloc
            if fine.paid_amount >= fine.amount:
                fine.status = FineStatus.CANCELLED
                fine.cancelled_at = now_msk()
            await fine_repo.update(fine)

            remaining = Decimal(payment.amount) - alloc
            user_model = await user_repo.get_by_id(payment.user_id)
            if user_model and remaining > 0:
                user_model.balance_credit = (user_model.balance_credit or Decimal('0')) + remaining
                await user_repo.update(user_model)

            payment.status = PaymentStatus.CONFIRMED
            payment.confirmed_at = now_msk()
            admin = await user_repo.get_by_telegram_id(callback.from_user.id)
            if admin:
                payment.confirmed_by = int(admin.id) if admin.id else None
            await pay_repo.update(payment)

            if admin:
                await audit_repo.create(AuditLog(
                    user_id=int(admin.id) if admin.id is not None else 0,
                    action="confirm_payment",
                    entity_type="payment",
                    entity_id=payment.id,
                    details={"user_id": payment.user_id, "amount": str(payment.amount), "fine_id": fine_id, "allocated": str(alloc)},
                ))

            try:
                bot = callback.bot
                if user_model:
                    await bot.send_message(
                        user_model.telegram_id,
                        f"✅ Ваш платёж на <b>{payment.amount:,.2f}₽</b> подтверждён и распределён на штраф #{fine_id}.",
                    )
            except Exception as exc:
                logger.exception("fine_allocate: failed to notify user %s", payment.user_id)

            succeeded = True
            await safe_edit(callback,
                f"✅ Платёж #{payment_id} подтверждён.\n"
                f"💰 На штраф #{fine_id} направлено <b>{alloc:,.2f}₽</b>\n"
                f"💳 Платёж: <b>{payment.amount:,.2f}₽</b>",
                reply_markup=back_keyboard(),
            )
        if succeeded:
            await callback.answer()
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


@router.callback_query(F.data.startswith("fine_overflow:"))
async def fine_overflow(callback: CallbackQuery) -> None:
    """Apply fine payment with overflow to balance (no specific fine selected)."""
    if not await require_treasurer_or_admin(callback):
        return
    payment_id = int((callback.data or "").split(":")[1])
    succeeded = False
    try:
        async for session in get_session():
            pay_repo = PaymentRepository(session)
            user_repo = UserRepository(session)
            audit_repo = AuditLogRepository(session)

            payment = await pay_repo.get_by_id(payment_id)
            if not payment:
                await callback.answer("❌ Платёж не найден", show_alert=True)
                break

            user_model = await user_repo.get_by_id(payment.user_id)
            if user_model:
                user_model.balance_credit = (user_model.balance_credit or Decimal('0')) + Decimal(payment.amount)
                await user_repo.update(user_model)

            payment.status = PaymentStatus.CONFIRMED
            payment.confirmed_at = now_msk()
            admin = await user_repo.get_by_telegram_id(callback.from_user.id)
            if admin:
                payment.confirmed_by = int(admin.id) if admin.id else None
            await pay_repo.update(payment)

            if admin:
                await audit_repo.create(AuditLog(
                    user_id=int(admin.id) if admin.id is not None else 0,
                    action="confirm_payment",
                    entity_type="payment",
                    entity_id=payment.id,
                    details={"user_id": payment.user_id, "amount": str(payment.amount), "overflow": True},
                ))

            try:
                bot = callback.bot
                if user_model:
                    await bot.send_message(
                        user_model.telegram_id,
                        f"✅ Ваш платёж на <b>{payment.amount:,.2f}₽</b> подтверждён и зачислен на баланс.",
                    )
            except Exception as exc:
                logger.exception("fine_overflow: failed to notify user %s", payment.user_id)

            succeeded = True
            await safe_edit(callback,
                f"✅ Платёж #{payment_id} подтверждён.\n"
                f"💳 Сумма <b>{payment.amount:,.2f}₽</b> зачислена на баланс участника.",
                reply_markup=back_keyboard(),
            )
        if succeeded:
            await callback.answer()
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


# ─── Хронология ──────────────────────────────────

@router.callback_query(F.data == "treasurer_timeline")
async def treasurer_timeline(callback: CallbackQuery) -> None:
    """Show member selector for timeline view."""
    if not await require_treasurer_or_admin(callback):
        return
    async for session in get_session():
        user_repo = UserRepository(session)
        members = await user_repo.list_active()
        users = [(m.id, m.full_name) for m in members]
        await safe_edit(
            callback,
            "📅 <b>Хронология</b>\n\nВыберите участника для просмотра истории операций:",
            reply_markup=timeline_user_select_keyboard(users, page=0),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("timeline_page:"))
async def timeline_page(callback: CallbackQuery) -> None:
    """Paginate member selector for timeline."""
    if not await require_treasurer_or_admin(callback):
        return
    page = int((callback.data or "").split(":")[1])
    async for session in get_session():
        user_repo = UserRepository(session)
        members = await user_repo.list_active()
        users = [(m.id, m.full_name) for m in members]
    await safe_edit(
        callback,
        "📅 <b>Хронология</b>\n\nВыберите участника для просмотра истории операций:",
        reply_markup=timeline_user_select_keyboard(users, page=page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("timeline_user:"))
async def timeline_user(callback: CallbackQuery) -> None:
    """Show merged chronological feed for a specific member."""
    if not await require_treasurer_or_admin(callback):
        return
    user_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        fee_repo = FeeRepository(session)
        fine_repo = FineRepository(session)
        pay_repo = PaymentRepository(session)
        user_repo = UserRepository(session)

        user = await user_repo.get_by_id(user_id)
        if not user:
            await callback.answer("❌ Участник не найден", show_alert=True)
            break

        items = []

        payments = await pay_repo.list_by_user(user_id)
        for p in payments:
            items.append({
                "date": p.confirmed_at or p.created_at or p.payment_date,
                "type": "payment",
                "id": p.id,
                "text": f"💰 Платёж · {p.amount:,.2f}₽ · {p.payment_type}",
            })

        fees = await fee_repo.list_by_user(user_id)
        for f in fees:
            items.append({
                "date": f.assessed_at or f.paid_at,
                "type": "fee",
                "id": f.id,
                "text": f"📅 Взнос · {f.amount:,.2f}₽ · {f.month:02d}/{f.year}",
            })

        fines = await fine_repo.list_by_user(user_id)
        for f in fines:
            status_label = "оплачен" if f.status != FineStatus.ACTIVE else "активен"
            items.append({
                "date": f.created_at or f.cancelled_at,
                "type": "fine",
                "id": f.id,
                "text": f"⚠️ Штраф · {f.amount:,.2f}₽ · {status_label}",
            })

        items.sort(key=lambda x: x["date"] or datetime.min, reverse=True)

        if not items:
            text = f"📅 <b>Хронология: {user.full_name}</b>\n\nОпераций пока нет."
        else:
            lines = [f"📅 <b>Хронология: {user.full_name}</b>"]
            for item in items[:10]:
                date_str = (item["date"] or datetime.min).strftime("%d.%m.%Y") if item["date"] else "—"
                lines.append(f"<b>{date_str}</b> — {item['text']}")
            if len(items) > 10:
                lines.append(f"\n... и ещё {len(items) - 10} записей")
            text = "\n".join(lines)

        kb_rows = [[(item["text"], f"timeline_item:{item['type']}:{item['id']}:{user_id}")] for item in items[:10]]
        kb_rows.append([("🔙 Назад", "treasurer_timeline")])
        kb = build_kb(kb_rows)

        await safe_edit(callback, text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("timeline_item:"))
async def timeline_item(callback: CallbackQuery) -> None:
    """Show detail for a timeline item."""
    if not await require_treasurer_or_admin(callback):
        return
    parts = (callback.data or "").split(":")
    item_type = parts[1]
    item_id = int(parts[2])
    user_id = int(parts[3]) if len(parts) > 3 else 0
    async for session in get_session():
        fee_repo = FeeRepository(session)
        fine_repo = FineRepository(session)
        pay_repo = PaymentRepository(session)

        if item_type == "payment":
            pay = await pay_repo.get_by_id(item_id)
            if not pay:
                await callback.answer("❌ Не найдено", show_alert=True)
                break
            dt = pay.confirmed_at or pay.created_at or pay.payment_date
            date_str = dt.strftime("%d.%m.%Y %H:%M") if dt else "—"
            text = (
                f"💰 <b>Платёж #{item_id}</b>\n\n"
                f"Сумма: <b>{pay.amount:,.2f}₽</b>\n"
                f"Тип: {pay.payment_type}\n"
                f"Статус: {pay.status.value}\n"
                f"Дата: {date_str}"
            )
        elif item_type == "fee":
            fee = await fee_repo.get_by_id(item_id)
            if not fee:
                await callback.answer("❌ Не найдено", show_alert=True)
                break
            text = (
                f"📅 <b>Взнос #{item_id}</b>\n\n"
                f"Период: {fee.month:02d}/{fee.year}\n"
                f"Сумма: <b>{fee.amount:,.2f}₽</b>\n"
                f"Оплачено: {fee.paid_amount or 0:,.2f}₽\n"
                f"Остаток: {fee.remaining_amount:,.2f}₽\n"
                f"Статус: {fee.status.value}"
            )
        elif item_type == "fine":
            fine = await fine_repo.get_by_id(item_id)
            if not fine:
                await callback.answer("❌ Не найдено", show_alert=True)
                break
            text = (
                f"⚠️ <b>Штраф #{item_id}</b>\n\n"
                f"Сумма: <b>{fine.amount:,.2f}₽</b>\n"
                f"Оплачено: {fine.paid_amount or 0:,.2f}₽\n"
                f"Остаток: {fine.remaining_amount:,.2f}₽\n"
                f"Причина: {fine.reason or '—'}\n"
                f"Статус: {fine.status.value}"
            )
        else:
            await callback.answer("❌ Неизвестный тип", show_alert=True)
            break
        await safe_edit(callback, text, reply_markup=back_keyboard(f"timeline_user:{user_id}"))
    await callback.answer()
