"""Редактирование и удаление записей в истории лицевого счёта (платежи, штрафы, взносы)."""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import delete

from src.domain.entities.audit_log import AuditLog
from src.domain.entities.fine import Fine
from src.domain.entities.monthly_fee import MonthlyFee
from src.domain.entities.payment import Payment
from src.domain.value_objects.fee_status import FeeStatus
from src.domain.value_objects.fine_status import FineStatus
from src.domain.value_objects.payment_status import PaymentStatus
from src.domain.value_objects.role import UserRole


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
from src.infrastructure.database.models.monthly_fee import MonthlyFeeModel
from src.infrastructure.database.session import get_session
from src.infrastructure.repositories.audit_repository import AuditLogRepository
from src.infrastructure.repositories.fee_repository import FeeRepository
from src.infrastructure.repositories.fine_repository import FineRepository
from src.infrastructure.repositories.payment_repository import PaymentRepository
from src.infrastructure.repositories.user_repository import UserRepository
from src.infrastructure.timezone import now_msk
from src.presentation.keyboards.common import back_keyboard, build_kb, confirm_cancel_keyboard
from src.presentation.utils import require_role

router = Router()
logger = logging.getLogger(__name__)


# ─── Пересчёт баланса пользователя из истории ────────────────────────────

async def _recalculate_balance(session, user_id: int) -> Decimal:
    """Пересчитать balance_credit пользователя из всех подтверждённых fee-платежей и оплаченных взносов."""
    pay_repo = PaymentRepository(session)
    fee_repo = FeeRepository(session)

    user_payments = await pay_repo.list_by_user(user_id)
    user_fees = await fee_repo.list_by_user(user_id)

    balance = Decimal("0")
    for p in user_payments:
        if p.status == PaymentStatus.CONFIRMED and p.payment_type == "fee":
            balance += p.amount

    for f in user_fees:
        if f.status == FeeStatus.PAID:
            balance -= f.amount
        elif f.paid_amount > 0:
            balance -= f.paid_amount

    return max(balance, Decimal("0"))


async def _recalculate_fine_paid_amounts(session, user_id: int) -> None:
    """Пересчитать paid_amount у всех штрафов пользователя из подтверждённых fine-платежей."""
    fine_repo = FineRepository(session)
    pay_repo = PaymentRepository(session)

    # Reset all active fines paid_amount
    fines = await fine_repo.list_by_user(user_id)
    for fine in fines:
        if fine.status == FineStatus.ACTIVE:
            fine.paid_amount = Decimal("0")
            await fine_repo.update(fine)

    # Re-apply confirmed fine payments
    user_payments = await pay_repo.list_by_user(user_id)
    for p in user_payments:
        if p.status == PaymentStatus.CONFIRMED and p.payment_type == "fine":
            remaining = Decimal(p.amount)
            for fine in fines:
                if fine.status != FineStatus.ACTIVE or remaining <= 0:
                    continue
                alloc = min(remaining, fine.remaining_amount)
                if alloc <= 0:
                    continue
                fine.paid_amount = (fine.paid_amount or Decimal("0")) + alloc
                if fine.paid_amount >= fine.amount:
                    fine.status = FineStatus.CANCELLED
                    fine.cancelled_at = now_msk()
                await fine_repo.update(fine)
                remaining -= alloc


# ─── Просмотр и редактирование платежей ─────────────────────────────────

@router.callback_query(F.data.startswith("ledger_payments:"))
async def ledger_view_payments(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    user_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        pay_repo = PaymentRepository(session)
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        payments = await pay_repo.list_by_user(user_id)
        if not payments:
            await callback.message.edit_text(
                f"📋 <b>Платежи {user.full_name}</b>\n\n📭 Нет платежей.",
                reply_markup=back_keyboard(f"member_view:{user_id}"),
            )
            return

        lines = [f"📋 <b>Платежи {user.full_name}</b>:\n"]
        kb_rows = []
        for p in payments[:20]:
            status_icon = {
                PaymentStatus.PENDING: "⏳",
                PaymentStatus.CONFIRMED: "✅",
                PaymentStatus.REJECTED: "❌",
            }.get(p.status, "❓")
            date_str = p.payment_date.strftime('%d.%m.%Y') if p.payment_date else f'{p.month:02d}/{p.year}'
            comment_part = f" | {p.comment}" if p.comment else ""
            ru_status = _payment_status_ru(p.status)
            # Each row is clickable — opens edit/delete menu
            lines.append(
                f"{status_icon} <b>{p.amount:,.2f}₽</b> "
                f"{date_str} [{ru_status}]"
                f"{comment_part}"
            )
            kb_rows.append([
                (f"💳 {p.amount:,.2f}₽  {date_str}  [{ru_status}]{comment_part}", f"ledger_payment_view:{p.id}"),
            ])
        kb_rows.append([("🔙 Назад", f"member_view:{user_id}")])
        await callback.message.edit_text("\n".join(lines), reply_markup=build_kb(kb_rows))
    await callback.answer()


@router.callback_query(F.data.startswith("ledger_payment_view:"))
async def ledger_payment_view(callback: CallbackQuery) -> None:
    """Клик по строке платежа — показать меню редактирования."""
    if not await require_role(callback, UserRole.ADMIN):
        return
    payment_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        pay_repo = PaymentRepository(session)
        payment = await pay_repo.get_by_id(payment_id)
        if not payment:
            await callback.answer("❌ Платёж не найден", show_alert=True)
            return
        date_str = payment.payment_date.strftime('%d.%m.%Y') if payment.payment_date else f'{payment.month:02d}/{payment.year}'
        comment_part = f" | {payment.comment}" if payment.comment else ""
        await callback.message.edit_text(
            f"💳 <b>Платёж #{payment_id}</b>\n"
            f"👤 Пользователь: <code>{payment.user_id}</code>\n"
            f"💰 Сумма: <code>{payment.amount:,.2f}₽</code>\n"
            f"📅 Дата: <code>{date_str}</code>\n"
            f"📌 Статус: <code>{_payment_status_ru(payment.status)}</code>\n"
            f"💬 Комментарий: <code>{payment.comment or '—'}</code>",
            reply_markup=back_keyboard(f"ledger_payments:{payment.user_id}"),
        )
        # Add edit/delete buttons near the bottom so user can act on this row
        edit_kb = build_kb([
            [("✏️ Изменить", f"ledger_edit_payment:{payment_id}")],
            [("🗑 Удалить", f"ledger_delete_payment:{payment_id}")],
            [("🔙 Назад к списку", f"ledger_payments:{payment.user_id}")],
        ])
        await callback.message.edit_reply_markup(reply_markup=edit_kb)
    await callback.answer()


@router.callback_query(F.data.startswith("ledger_edit_payment:"))
async def ledger_edit_payment(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    payment_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        pay_repo = PaymentRepository(session)
        payment = await pay_repo.get_by_id(payment_id)
        if not payment:
            await callback.answer("❌ Платёж не найден", show_alert=True)
            return
        await state.update_data(edit_payment_id=payment_id, edit_payment_old={
            "amount": str(payment.amount),
            "month": payment.month,
            "year": payment.year,
            "comment": payment.comment or "",
            "payment_type": payment.payment_type,
        })
        await state.set_state("ledger_edit_payment_amount")
        await callback.message.edit_text(
            f"✏️ <b>Редактирование платежа #{payment_id}</b>\n"
            f"Сумма: <code>{payment.amount}</code>\n"
            f"Месяц: <code>{payment.month}</code>\n"
            f"Год: <code>{payment.year}</code>\n"
            f"Комментарий: <code>{payment.comment or '—'}</code>\n\n"
            f"Введите <b>новую сумму</b> (или отправьте /skip чтобы оставить текущую):",
            reply_markup=confirm_cancel_keyboard("ledger_save_payment", "ledger_cancel_edit"),
        )
    await callback.answer()


@router.message("ledger_edit_payment_amount")
async def ledger_edit_payment_amount(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    if message.text.strip().lower() in ("/cancel", "отмена"):
        await state.clear()
        await message.answer("❌ Отменено")
        return
    data = await state.get_data()
    if message.text.strip().lower() == "/skip":
        await state.set_state("ledger_edit_payment_month")
        await message.answer("Введите <b>месяц</b> (1-12) или /skip:", reply_markup=confirm_cancel_keyboard("ledger_save_payment", "ledger_cancel_edit"))
        return
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
        await state.update_data(edit_amount=amount)
    except Exception:
        await message.answer("❌ Введите корректную сумму.")
        return
    await state.set_state("ledger_edit_payment_month")
    await message.answer("Введите <b>месяц</b> (1-12) или /skip:", reply_markup=confirm_cancel_keyboard("ledger_save_payment", "ledger_cancel_edit"))


@router.message("ledger_edit_payment_month")
async def ledger_edit_payment_month(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    data = await state.get_data()
    if message.text.strip().lower() == "/skip":
        new_month = int(data.get("edit_payment_old", {}).get("month", 0))
        new_year = int(data.get("edit_payment_old", {}).get("year", 0))
    else:
        try:
            new_month = int(message.text.strip())
            if not (1 <= new_month <= 12):
                raise ValueError
        except Exception:
            await message.answer("❌ Введите месяц (1-12).")
            return
        new_year = int(data.get("edit_payment_old", {}).get("year", 0))
    await state.update_data(edit_month=new_month, edit_year=new_year)
    await state.set_state("ledger_edit_payment_comment")
    old_comment = data.get("edit_payment_old", {}).get("comment", "")
    await message.answer(
        f"Комментарий: <code>{old_comment or '—'}</code>\n\n"
        f"Введите <b>новый комментарий</b> (или /skip):",
        reply_markup=confirm_cancel_keyboard("ledger_save_payment", "ledger_cancel_edit"),
    )


@router.message("ledger_edit_payment_comment")
async def ledger_edit_payment_comment(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    data = await state.get_data()
    new_comment = "" if message.text.strip().lower() == "/skip" else message.text.strip()
    await state.update_data(edit_comment=new_comment)
    await _save_edit_payment(message, state)


async def _save_edit_payment(source, state: FSMContext) -> None:
    data = await state.get_data()
    payment_id = data.get("edit_payment_id")
    if not payment_id:
        await source.answer("❌ Ошибка сессии")
        await state.clear()
        return

    async for session in get_session():
        pay_repo = PaymentRepository(session)
        user_repo = UserRepository(session)
        audit_repo = AuditLogRepository(session)

        payment = await pay_repo.get_by_id(payment_id)
        if not payment:
            await source.answer("❌ Платёж не найден", show_alert=True)
            await state.clear()
            return

        old_amount = payment.amount
        old_month = payment.month
        old_year = payment.year

        payment.amount = Decimal(data.get("edit_amount", old_amount))
        payment.month = int(data.get("edit_month", old_month))
        payment.year = int(data.get("edit_year", old_year))
        payment.comment = data.get("edit_comment")

        await pay_repo.update(payment)

        # Recalculate
        user = await user_repo.get_by_id(payment.user_id)
        if user:
            user.balance_credit = await _recalculate_balance(session, payment.user_id)
            await user_repo.update(user)

        # Audit
        actor = await user_repo.get_by_telegram_id(source.from_user.id if hasattr(source, "from_user") and source.from_user else 0)
        if actor:
            await audit_repo.create(AuditLog(
                user_id=int(actor.id) if actor.id else 0,
                action="edit_payment",
                entity_type="payment",
                entity_id=payment_id,
                details={"old_amount": str(old_amount), "new_amount": str(payment.amount),
                         "old_month": old_month, "new_month": payment.month,
                         "old_year": old_year, "new_year": payment.year},
            ))

    await state.clear()
    await source.answer("✅ Платёж обновлён. Баланс пересчитан.")


@router.callback_query(F.data == "ledger_cancel_edit")
async def ledger_cancel_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("❌ Отменено")


@router.callback_query(F.data.startswith("ledger_save_payment"))
async def ledger_save_payment(callback: CallbackQuery, state: FSMContext) -> None:
    await _save_edit_payment(callback, state)
    await callback.answer("✅ Сохранено")


@router.callback_query(F.data.startswith("ledger_delete_payment:"))
async def ledger_delete_payment(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    payment_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        pay_repo = PaymentRepository(session)
        user_repo = UserRepository(session)
        audit_repo = AuditLogRepository(session)

        payment = await pay_repo.get_by_id(payment_id)
        if not payment:
            await callback.answer("❌ Платёж не найден", show_alert=True)
            return

        user_id = payment.user_id

        # Real deletion from DB
        await pay_repo.delete(payment.id)

        # Recalculate balance
        user = await user_repo.get_by_id(user_id)
        if user:
            user.balance_credit = await _recalculate_balance(session, user_id)
            await user_repo.update(user)

        # Recalculate fines if it was a fine payment
        if payment.payment_type == "fine":
            await _recalculate_fine_paid_amounts(session, user_id)

        # Audit
        actor = await user_repo.get_by_telegram_id(callback.from_user.id)
        if actor:
            await audit_repo.create(AuditLog(
                user_id=int(actor.id) if actor.id else 0,
                action="delete_payment",
                entity_type="payment",
                entity_id=payment_id,
                details={"amount": str(payment.amount), "user_id": user_id},
            ))

        await callback.message.edit_text(
            f"🗑 Платёж #{payment_id} удалён. Баланс пересчитан.",
            reply_markup=back_keyboard(f"member_view:{user_id}"),
        )
    await callback.answer()


# ─── Просмотр и редактирование штрафов ──────────────────────────────────

@router.callback_query(F.data.startswith("ledger_fines:"))
async def ledger_view_fines(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    user_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        fine_repo = FineRepository(session)
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        fines = await fine_repo.list_by_user(user_id)
        if not fines:
            await callback.message.edit_text(
                f"⚠️ <b>Штрафы {user.full_name}</b>\n\n✅ Нет штрафов.",
                reply_markup=back_keyboard(f"member_view:{user_id}"),
            )
            return

        lines = [f"⚠️ <b>Штрафы {user.full_name}</b>:\n"]
        kb_rows = []
        for f in fines:
            remaining = f.remaining_amount
            status_icon = "⚠️" if f.status == FineStatus.ACTIVE and remaining > 0 else "✅"
            ru_status = _fine_status_ru(f.status)
            lines.append(
                f"{status_icon} <b>{remaining:,.2f}₽</b> / {f.amount:,.2f}₽ — {f.reason}"
                f"{' | ' + f.comment if f.comment else ''}"
            )
            kb_rows.append([
                (f"⚠️ {remaining:,.2f}₽ / {f.amount:,.2f}₽  [{ru_status}]", f"ledger_fine_view:{f.id}"),
            ])
        kb_rows.append([("🔙 Назад", f"member_view:{user_id}")])
        await callback.message.edit_text("\n".join(lines), reply_markup=build_kb(kb_rows))
    await callback.answer()


@router.callback_query(F.data.startswith("ledger_fine_view:"))
async def ledger_fine_view(callback: CallbackQuery) -> None:
    """Клик по строке штрафа — показать меню редактирования."""
    if not await require_role(callback, UserRole.ADMIN):
        return
    fine_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        fine_repo = FineRepository(session)
        fine = await fine_repo.get_by_id(fine_id)
        if not fine:
            await callback.answer("❌ Штраф не найден", show_alert=True)
            return
        await callback.message.edit_text(
            f"⚠️ <b>Штраф #{fine_id}</b>\n"
            f"👤 Пользователь: <code>{fine.user_id}</code>\n"
            f"💰 Сумма: <code>{fine.amount:,.2f}₽</code>\n"
            f"Остаток: <code>{fine.remaining_amount:,.2f}₽</code>\n"
            f"📝 Причина: <code>{fine.reason}</code>\n"
            f"💬 Комментарий: <code>{fine.comment or '—'}</code>\n"
            f"📌 Статус: <code>{_fine_status_ru(fine.status)}</code>",
            reply_markup=back_keyboard(f"ledger_fines:{fine.user_id}"),
        )
        edit_kb = build_kb([
            [("✏️ Изменить", f"ledger_edit_fine:{fine_id}")],
            [("🗑 Удалить", f"ledger_delete_fine:{fine_id}")],
            [("🔙 Назад к списку", f"ledger_fines:{fine.user_id}")],
        ])
        await callback.message.edit_reply_markup(reply_markup=edit_kb)
    await callback.answer()


@router.callback_query(F.data.startswith("ledger_edit_fine:"))
async def ledger_edit_fine(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    fine_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        fine_repo = FineRepository(session)
        fine = await fine_repo.get_by_id(fine_id)
        if not fine:
            await callback.answer("❌ Штраф не найден", show_alert=True)
            return
        await state.update_data(edit_fine_id=fine_id, edit_fine_old={
            "amount": str(fine.amount),
            "reason": fine.reason,
            "comment": fine.comment or "",
        })
        await state.set_state("ledger_edit_fine_amount")
        await callback.message.edit_text(
            f"✏️ <b>Редактирование штрафа #{fine_id}</b>\n"
            f"Сумма: <code>{fine.amount}</code>\n"
            f"Причина: <code>{fine.reason}</code>\n"
            f"Комментарий: <code>{fine.comment or '—'}</code>\n\n"
            f"Введите <b>новую сумму</b> (или /skip):",
            reply_markup=confirm_cancel_keyboard("ledger_save_fine", "ledger_cancel_edit"),
        )
    await callback.answer()


@router.message("ledger_edit_fine_amount")
async def ledger_edit_fine_amount(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    if message.text.strip().lower() in ("/cancel", "отмена"):
        await state.clear()
        await message.answer("❌ Отменено")
        return
    data = await state.get_data()
    if message.text.strip().lower() == "/skip":
        await state.set_state("ledger_edit_fine_reason")
        await message.answer("Введите <b>причину</b> (или /skip):", reply_markup=confirm_cancel_keyboard("ledger_save_fine", "ledger_cancel_edit"))
        return
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
        await state.update_data(edit_fine_amount=amount)
    except Exception:
        await message.answer("❌ Введите корректную сумму.")
        return
    await state.set_state("ledger_edit_fine_reason")
    old_reason = data.get("edit_fine_old", {}).get("reason", "")
    await message.answer(f"Причина: <code>{old_reason}</code>\n\nВведите <b>новую причину</b> (или /skip):",
                         reply_markup=confirm_cancel_keyboard("ledger_save_fine", "ledger_cancel_edit"))


@router.message("ledger_edit_fine_reason")
async def ledger_edit_fine_reason(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    data = await state.get_data()
    new_reason = "" if message.text.strip().lower() == "/skip" else message.text.strip()
    await state.update_data(edit_fine_reason=new_reason)
    await state.set_state("ledger_edit_fine_comment")
    old_comment = data.get("edit_fine_old", {}).get("comment", "")
    await message.answer(f"Комментарий: <code>{old_comment or '—'}</code>\n\nВведите <b>новый комментарий</b> (или /skip):",
                         reply_markup=confirm_cancel_keyboard("ledger_save_fine", "ledger_cancel_edit"))


@router.message("ledger_edit_fine_comment")
async def ledger_edit_fine_comment(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    data = await state.get_data()
    new_comment = "" if message.text.strip().lower() == "/skip" else message.text.strip()
    await state.update_data(edit_fine_comment=new_comment)
    await _save_edit_fine(message, state)


async def _save_edit_fine(source, state: FSMContext) -> None:
    data = await state.get_data()
    fine_id = data.get("edit_fine_id")
    if not fine_id:
        await source.answer("❌ Ошибка сессии")
        await state.clear()
        return

    async for session in get_session():
        fine_repo = FineRepository(session)
        user_repo = UserRepository(session)
        audit_repo = AuditLogRepository(session)

        fine = await fine_repo.get_by_id(fine_id)
        if not fine:
            await source.answer("❌ Штраф не найден", show_alert=True)
            await state.clear()
            return

        old_amount = fine.amount
        old_reason = fine.reason

        fine.amount = Decimal(data.get("edit_fine_amount", old_amount))
        fine.reason = data.get("edit_fine_reason", old_reason)
        fine.comment = data.get("edit_fine_comment")

        await fine_repo.update(fine)

        # Recalculate balance (fine payments are independent of balance)
        user = await user_repo.get_by_id(fine.user_id)
        if user:
            user.balance_credit = await _recalculate_balance(session, fine.user_id)
            await user_repo.update(user)

        # Audit
        actor = await user_repo.get_by_telegram_id(source.from_user.id if hasattr(source, "from_user") and source.from_user else 0)
        if actor:
            await audit_repo.create(AuditLog(
                user_id=int(actor.id) if actor.id else 0,
                action="edit_fine",
                entity_type="fine",
                entity_id=fine_id,
                details={"old_amount": str(old_amount), "new_amount": str(fine.amount),
                         "old_reason": old_reason, "new_reason": fine.reason},
            ))

    await state.clear()
    await source.answer("✅ Штраф обновлён.")


@router.callback_query(F.data.startswith("ledger_save_fine"))
async def ledger_save_fine(callback: CallbackQuery, state: FSMContext) -> None:
    await _save_edit_fine(callback, state)
    await callback.answer("✅ Сохранено")


@router.callback_query(F.data.startswith("ledger_delete_fine:"))
async def ledger_delete_fine(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    fine_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        fine_repo = FineRepository(session)
        user_repo = UserRepository(session)
        audit_repo = AuditLogRepository(session)

        fine = await fine_repo.get_by_id(fine_id)
        if not fine:
            await callback.answer("❌ Штраф не найден", show_alert=True)
            return

        user_id = fine.user_id

        # Real deletion (same as fees)
        await fine_repo.delete(fine_id)

        # Recalculate fine paid amounts (in case we're deleting an active fine)
        await _recalculate_fine_paid_amounts(session, user_id)

        # Recalculate balance
        user = await user_repo.get_by_id(user_id)
        if user:
            user.balance_credit = await _recalculate_balance(session, user_id)
            await user_repo.update(user)

        # Audit
        actor = await user_repo.get_by_telegram_id(callback.from_user.id)
        if actor:
            await audit_repo.create(AuditLog(
                user_id=int(actor.id) if actor.id else 0,
                action="delete_fine",
                entity_type="fine",
                entity_id=fine_id,
                details={"amount": str(fine.amount), "user_id": user_id},
            ))

        await callback.message.edit_text(
            f"🗑 Штраф #{fine_id} удалён. Баланс пересчитан.",
            reply_markup=back_keyboard(f"member_view:{user_id}"),
        )
    await callback.answer()


# ─── Просмотр и редактирование взносов ───────────────────────────────────

@router.callback_query(F.data.startswith("ledger_fees:"))
async def ledger_view_fees(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    user_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        fee_repo = FeeRepository(session)
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        fees = await fee_repo.list_by_user(user_id)
        if not fees:
            await callback.message.edit_text(
                f"💰 <b>Взносы {user.full_name}</b>\n\n📭 Нет начислений.",
                reply_markup=back_keyboard(f"member_view:{user_id}"),
            )
            return

        lines = [f"💰 <b>Взносы {user.full_name}</b>:\n"]
        kb_rows = []
        for f in fees:
            if f.status == FeeStatus.PAID:
                status_icon = "✅"
                status_label = "Оплачен"
            elif f.paid_amount > 0:
                status_icon = "🔄"
                status_label = f"Частично ({f.paid_amount:,.0f}₽)"
            else:
                status_icon = "⏳"
                status_label = "Ожидает"
            lines.append(
                f"{status_icon} <b>{f.amount:,.2f}₽</b> {f.month:02d}/{f.year}"
                f"{' | ' + f.comment if f.comment else ''}"
            )
            kb_rows.append([
                (f"{status_icon} {f.amount:,.2f}₽  {f.month:02d}/{f.year}  [{status_label}]", f"ledger_fee_view:{f.id}"),
            ])
        kb_rows.append([("🔙 Назад", f"member_view:{user_id}")])
        await callback.message.edit_text("\n".join(lines), reply_markup=build_kb(kb_rows))
    await callback.answer()


@router.callback_query(F.data.startswith("ledger_fee_view:"))
async def ledger_fee_view(callback: CallbackQuery) -> None:
    """Клик по строке взноса — показать меню редактирования."""
    if not await require_role(callback, UserRole.ADMIN):
        return
    fee_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        fee_repo = FeeRepository(session)
        fee = await fee_repo.get_by_id(fee_id)
        if not fee:
            await callback.answer("❌ Взнос не найден", show_alert=True)
            return
        await callback.message.edit_text(
            f"💰 <b>Взнос #{fee_id}</b>\n"
            f"👤 Пользователь: <code>{fee.user_id}</code>\n"
            f"💰 Сумма: <code>{fee.amount:,.2f}₽</code>\n"
            f"📅 Период: <code>{fee.month:02d}/{fee.year}</code>\n"
            f"📌 Статус: <code>{_fee_status_ru(fee.status)}</code>\n"
            f"💬 Комментарий: <code>{fee.comment or '—'}</code>\n"
            f"📆 Дата оплаты: <code>{fee.paid_at.strftime('%d.%m.%Y') if fee.paid_at else '—'}</code>",
            reply_markup=back_keyboard(f"ledger_fees:{fee.user_id}"),
        )
        edit_kb = build_kb([
            [("✏️ Изменить", f"ledger_edit_fee:{fee_id}")],
            [("🗑 Удалить", f"ledger_delete_fee:{fee_id}")],
            [("🔙 Назад к списку", f"ledger_fees:{fee.user_id}")],
        ])
        await callback.message.edit_reply_markup(reply_markup=edit_kb)
    await callback.answer()


@router.callback_query(F.data.startswith("ledger_edit_fee:"))
async def ledger_edit_fee(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    fee_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        fee_repo = FeeRepository(session)
        fee = await fee_repo.get_by_id(fee_id)
        if not fee:
            await callback.answer("❌ Взнос не найден", show_alert=True)
            return
        await state.update_data(edit_fee_id=fee_id, edit_fee_old={
            "amount": str(fee.amount),
            "month": fee.month,
            "year": fee.year,
            "status": fee.status.value,
        })
        await state.set_state("ledger_edit_fee_amount")
        await callback.message.edit_text(
            f"✏️ <b>Редактирование взноса #{fee_id}</b>\n"
            f"Сумма: <code>{fee.amount}</code>\n"
            f"Период: <code>{fee.month:02d}/{fee.year}</code>\n"
            f"Статус: <code>{_fee_status_ru(fee.status)}</code>\n\n"
            f"Введите <b>новую сумму</b> (или /skip):",
            reply_markup=confirm_cancel_keyboard("ledger_save_fee", "ledger_cancel_edit"),
        )
    await callback.answer()


@router.message("ledger_edit_fee_amount")
async def ledger_edit_fee_amount(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    if message.text.strip().lower() in ("/cancel", "отмена"):
        await state.clear()
        await message.answer("❌ Отменено")
        return
    data = await state.get_data()
    if message.text.strip().lower() == "/skip":
        await state.set_state("ledger_edit_fee_month")
        old = data.get("edit_fee_old", {})
        await message.answer(f"Месяц: <code>{old.get('month', 0)}</code>\n\nВведите <b>месяц</b> (1-12) или /skip:",
                             reply_markup=confirm_cancel_keyboard("ledger_save_fee", "ledger_cancel_edit"))
        return
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
        await state.update_data(edit_fee_amount=amount)
    except Exception:
        await message.answer("❌ Введите корректную сумму.")
        return
    await state.set_state("ledger_edit_fee_month")
    old = data.get("edit_fee_old", {})
    await message.answer(f"Месяц: <code>{old.get('month', 0)}</code>\n\nВведите <b>месяц</b> (1-12) или /skip:",
                         reply_markup=confirm_cancel_keyboard("ledger_save_fee", "ledger_cancel_edit"))


@router.message("ledger_edit_fee_month")
async def ledger_edit_fee_month(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    data = await state.get_data()
    if message.text.strip().lower() == "/skip":
        old = data.get("edit_fee_old", {})
        new_month = int(old.get("month", 0))
        new_year = int(old.get("year", 0))
    else:
        try:
            new_month = int(message.text.strip())
            if not (1 <= new_month <= 12):
                raise ValueError
        except Exception:
            await message.answer("❌ Введите месяц (1-12).")
            return
        new_year = int(data.get("edit_fee_old", {}).get("year", 0))
    await state.update_data(edit_fee_month=new_month, edit_fee_year=new_year)
    await state.set_state("ledger_edit_fee_status")
    old_status = data.get("edit_fee_old", {}).get("status", "pending")
    await message.answer(
        f"Статус: <code>{old_status}</code>\n\n"
        f"Выберите <b>новый статус</b>:\n"
        f"<code>1</code> — ожидает\n"
        f"<code>2</code> — оплачен\n"
        f"<code>3</code> — списан",
        reply_markup=confirm_cancel_keyboard("ledger_save_fee", "ledger_cancel_edit"),
    )


@router.message("ledger_edit_fee_status")
async def ledger_edit_fee_status(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    data = await state.get_data()
    if message.text.strip().lower() in ("/cancel", "отмена"):
        await state.clear()
        await message.answer("❌ Отменено")
        return
    if message.text.strip() == "/skip":
        new_status = data.get("edit_fee_old", {}).get("status", "pending")
    elif message.text.strip() == "1":
        new_status = FeeStatus.PENDING.value
    elif message.text.strip() == "2":
        new_status = FeeStatus.PAID.value
    else:
        await message.answer("❌ Введите 1 или 2.")
        return
    await state.update_data(edit_fee_status=new_status)
    await _save_edit_fee(message, state)


async def _save_edit_fee(source, state: FSMContext) -> None:
    data = await state.get_data()
    fee_id = data.get("edit_fee_id")
    if not fee_id:
        await source.answer("❌ Ошибка сессии")
        await state.clear()
        return

    async for session in get_session():
        fee_repo = FeeRepository(session)
        user_repo = UserRepository(session)
        audit_repo = AuditLogRepository(session)

        fee = await fee_repo.get_by_id(fee_id)
        if not fee:
            await source.answer("❌ Взнос не найден", show_alert=True)
            await state.clear()
            return

        old_amount = fee.amount
        old_status = fee.status.value

        fee.amount = Decimal(data.get("edit_fee_amount", old_amount))
        fee.month = int(data.get("edit_fee_month", fee.month))
        fee.year = int(data.get("edit_fee_year", fee.year))
        fee.status = FeeStatus(data.get("edit_fee_status", old_status))
        if fee.status == FeeStatus.PAID and not fee.paid_at:
            fee.paid_at = now_msk()

        await fee_repo.update(fee)

        # Recalculate balance
        user = await user_repo.get_by_id(fee.user_id)
        if user:
            user.balance_credit = await _recalculate_balance(session, fee.user_id)
            await user_repo.update(user)

        # Audit
        actor = await user_repo.get_by_telegram_id(source.from_user.id if hasattr(source, "from_user") and source.from_user else 0)
        if actor:
            await audit_repo.create(AuditLog(
                user_id=int(actor.id) if actor.id else 0,
                action="edit_fee",
                entity_type="monthly_fee",
                entity_id=fee_id,
                details={"old_amount": str(old_amount), "new_amount": str(fee.amount),
                         "old_status": old_status, "new_status": fee.status.value},
            ))

    await state.clear()
    await source.answer("✅ Взнос обновлён. Баланс пересчитан.")


@router.callback_query(F.data.startswith("ledger_save_fee"))
async def ledger_save_fee(callback: CallbackQuery, state: FSMContext) -> None:
    await _save_edit_fee(callback, state)
    await callback.answer("✅ Сохранено")


@router.callback_query(F.data.startswith("ledger_delete_fee:"))
async def ledger_delete_fee(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    fee_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        fee_repo = FeeRepository(session)
        user_repo = UserRepository(session)
        audit_repo = AuditLogRepository(session)

        fee = await fee_repo.get_by_id(fee_id)
        if not fee:
            await callback.answer("❌ Взнос не найден", show_alert=True)
            return

        user_id = fee.user_id
        await session.execute(delete(MonthlyFeeModel).where(MonthlyFeeModel.id == fee_id))
        await session.flush()

        # Recalculate balance
        user = await user_repo.get_by_id(user_id)
        if user:
            user.balance_credit = await _recalculate_balance(session, user_id)
            await user_repo.update(user)

        # Audit
        actor = await user_repo.get_by_telegram_id(callback.from_user.id)
        if actor:
            await audit_repo.create(AuditLog(
                user_id=int(actor.id) if actor.id else 0,
                action="delete_fee",
                entity_type="monthly_fee",
                entity_id=fee_id,
                details={"amount": str(fee.amount), "user_id": user_id},
            ))

        await callback.message.edit_text(
            f"🗑 Взнос #{fee_id} удалён. Баланс пересчитан.",
            reply_markup=back_keyboard(f"member_view:{user_id}"),
        )
    await callback.answer()
