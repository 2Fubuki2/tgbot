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
    payment_action_keyboard,
    back_keyboard,
    build_kb,
)
from src.presentation.states import SearchUserStates
from src.domain.entities.payment import Payment
from src.presentation.texts import (
    pending_payment_text,
    fee_assessment_result,
    no_fee_needed,
    debt_reminder_text,
    stats_text,
)
from src.presentation.utils import safe_edit, require_role, require_treasurer_or_admin

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

        fees_total = sum((f.amount for f in fees), Decimal("0"))
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

        if not payments:
            text = "📭 У вас пока нет платежей."
        else:
            lines = ["<b>История платежей:</b>\n"]
            for p in payments[:20]:
                status_icon = {"pending": "⏳", "confirmed": "✅", "rejected": "❌"}
                icon = status_icon.get(p.status.value, "❓")
                lines.append(
                    f"{icon} <b>{p.amount:,.2f}₽</b> за {p.month:02d}/{p.year}"
                    f" — {p.status.value}"
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

        if not payments:
            text = f"📭 У пользователя <b>{user.full_name}</b> пока нет платежей."
        else:
            lines = [f"<b>История платежей {user.full_name}:</b>\n"]
            for p in payments[:20]:
                status_icon = {"pending": "⏳", "confirmed": "✅", "rejected": "❌"}
                icon = status_icon.get(p.status.value, "❓")
                lines.append(
                    f"{icon} <b>{p.amount:,.2f}₽</b> за {p.month:02d}/{p.year}"
                    f" — {p.status.value}"
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
                    keyboard_rows.append([("💳 Оплатить штраф", f"pay_fine:{f.id}"), ("❌ Отменить штраф", f"fine_cancel:{f.id}")])
            text = "\n".join(lines)
            keyboard = build_kb(keyboard_rows + [[("🔙 Назад", "back")]]) if keyboard_rows else back_keyboard()

        await safe_edit(callback, text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "member_details")
async def member_details(callback: CallbackQuery) -> None:
    """Show payment details."""
    async for session in get_session():
        settings_repo = ClubSettingsRepository(session)
        club_settings = await settings_repo.get()

        text = (
            f"💳 <b>Реквизиты для оплаты</b>\n\n"
            f"{club_settings.get('payment_details', 'Не указаны')}"
        )
        await safe_edit(callback, text, reply_markup=back_keyboard())
    await callback.answer()


# ─── Казначей: начисление взносов ─────────────────

@router.callback_query(F.data == "treasurer_assess_fees")
async def assess_fees(callback: CallbackQuery) -> None:
    """Assess monthly fees for all active members."""
    if not await require_treasurer_or_admin(callback):
        return
    async for session in get_session():
        user_repo = UserRepository(session)
        fee_repo = FeeRepository(session)
        settings_repo = ClubSettingsRepository(session)
        audit_repo = AuditLogRepository(session)

        last = await fee_repo.get_last_assessment()
        from datetime import datetime
        now = datetime.utcnow()

        if last and last[0] == now.year and last[1] == now.month:
            await safe_edit(
                callback,
                no_fee_needed(),
                reply_markup=back_keyboard(),
            )
            await callback.answer()
            return

        monthly_fee = await settings_repo.get_monthly_fee()
        members = await user_repo.list_active()

        assessed_count = 0
        for member in members:
            existing = await fee_repo.get_by_user_month(member.id, now.month, now.year)
            if existing:
                continue

            fee = MonthlyFee(
                user_id=member.id,
                amount=monthly_fee,
                month=now.month,
                year=now.year,
                status=FeeStatus.PENDING,
            )
            await fee_repo.create(fee)
            assessed_count += 1

        await settings_repo.update(last_fee_assessment=now)

        # Audit log
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if user:
            await audit_repo.create(AuditLog(
                user_id=int(user.id) if user.id is not None else 0,
                action="assess_fees",
                entity_type="monthly_fee",
                details={
                    "count": assessed_count,
                    "month": now.month,
                    "year": now.year,
                    "amount": str(monthly_fee),
                },
            ))

        # Уведомить всех участников о начислении
        for member in members:
            existing = await fee_repo.get_by_user_month(member.id, now.month, now.year)
            if existing:
                try:
                    await callback.bot.send_message(
                        member.telegram_id,
                        f"💰 <b>Начислен взнос</b>\n\n"
                        f"📅 За: {now.month:02d}/{now.year}\n"
                        f"💵 Сумма: <b>{monthly_fee:,.2f}₽</b>\n\n"
                        f"Оплатить можно через меню 💰 Мой бюджет → 📤 Я оплатил",
                    )
                except Exception:
                    logger.exception("Failed to notify member %s about fee assessment", member.telegram_id)

        total = monthly_fee * assessed_count
        await safe_edit(
            callback,
            fee_assessment_result(assessed_count, f"{total:,.2f}₽"),
            reply_markup=back_keyboard(),
        )
    await callback.answer()


# ─── Казначей: ожидающие платежи ─────────────────

@router.callback_query(F.data == "treasurer_user_search")
async def treasurer_user_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_treasurer_or_admin(callback):
        return
    await state.set_state(SearchUserStates.waiting_query)
    await safe_edit(
        callback,
        "🔍 <b>Поиск участника</b>\n\nВведите имя, username или Telegram ID:",
        reply_markup=back_keyboard("treasurer_members"),
    )
    await callback.answer()


@router.message(SearchUserStates.waiting_query)
async def treasurer_user_search_query(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    query = message.text.strip()
    async for session in get_session():
        repo = UserRepository(session)
        users = await repo.search(query)
        if not users:
            await message.answer("❌ Пользователи не найдены. Попробуйте другой запрос.")
            await state.clear()
            return

        lines = ["👥 <b>Результаты поиска</b>:\n"]
        buttons = []
        for u in users[:10]:
            lines.append(f"👤 <b>{u.full_name}</b> — {u.role.value}\n   ID: {u.id} | @{u.username if u.username else '—'}")
            buttons.append([(f"{u.full_name}", f"member_view:{u.id}")])
        await message.answer("\n".join(lines), reply_markup=build_kb(buttons + [[("🔙 Назад", "treasurer_members")]]))
    await state.clear()


@router.callback_query(F.data == "treasurer_pending")
async def list_pending_payments(callback: CallbackQuery) -> None:
    """Show pending payments for treasurer (paginated, one per page)."""
    if not await require_treasurer_or_admin(callback):
        return
    await _show_pending_page(callback, 0)


async def _show_pending_page(callback: CallbackQuery, page: int) -> None:
    """Show one pending payment at a time with navigation."""
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
        name = payer.full_name if payer else f"ID:{p.user_id}"

        text = (
            f"📨 <b>Ожидающие платежи</b> ({page + 1}/{len(payments)})\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 {name}\n"
            f"💰 <b>{p.amount:,.2f}₽</b> за {p.month:02d}/{p.year}\n"
        )
        if p.comment:
            text += f"💬 {p.comment}\n"
        if p.payment_method:
            text += f"💳 {p.payment_method}\n"

        # Build navigation + action buttons
        kb_rows = [[("✅ Подтвердить", f"payment_confirm:{p.id}"),
                     ("❌ Отклонить", f"payment_reject:{p.id}")]]
        nav = []
        if page > 0:
            nav.append(("⬅️", f"pending_page:{page - 1}"))
        if page < len(payments) - 1:
            nav.append(("➡️", f"pending_page:{page + 1}"))
        if nav:
            kb_rows.append(nav)
        kb_rows.append([("🔙 Назад", "back")])

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
            payment.confirmed_at = datetime.utcnow()

            # Update user's balance_credit and apply to fee if exists
            user_model = await user_repo.get_by_id(payment.user_id)
            if user_model:
                logger.info("confirm_payment: user %s balance before=%s", user_model.id, user_model.balance_credit)

                if payment.payment_type == "fine":
                    active_fines = await fine_repo.list_active_by_user(payment.user_id)
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
                            fine.cancelled_at = datetime.utcnow()
                        await fine_repo.update(fine)
                        remaining_to_apply -= alloc
                    if remaining_to_apply > 0:
                        user_model.balance_credit = (user_model.balance_credit or Decimal('0')) + remaining_to_apply
                else:
                    # Increase balance by payment amount for fee payments; then apply to the matching fee if it exists
                    user_model.balance_credit = (user_model.balance_credit or Decimal('0')) + Decimal(payment.amount)
                    fee = await fee_repo.get_by_user_month(payment.user_id, payment.month, payment.year)
                    if fee and fee.status.value == FeeStatus.PENDING.value:
                        if user_model.balance_credit >= fee.amount:
                            fee.status = FeeStatus.PAID
                            fee.paid_at = datetime.utcnow()
                            user_model.balance_credit -= fee.amount
                            await fee_repo.update(fee)

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

            await safe_edit(
                callback,
                f"✅ Платёж {payment_id} подтверждён!",
                reply_markup=back_keyboard(),
            )

            # Notify user
            try:
                bot = callback.bot
                user_model = await user_repo.get_by_id(payment.user_id)
                if user_model:
                    await bot.send_message(
                        user_model.telegram_id,
                        f"✅ Ваш платёж на <b>{payment.amount:,.2f}₽</b> подтверждён казначеем!",
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
            payment.confirmed_at = datetime.utcnow()
            await pay_repo.update(payment)

            await safe_edit(
                callback,
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

        fees_total = sum((f.amount for f in fees), Decimal("0"))
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

        await safe_edit(
            callback,
            text,
            reply_markup=member_detail_keyboard(user_id),
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
        fees_total = sum((f.amount for f in fees), Decimal("0"))
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
        balance = total_revenue - total_expenses
        debtors = await user_repo.count_debtors()
        active = await user_repo.count_active()

        text = stats_text(
            f"{balance:,.2f}₽",
            f"{total_revenue:,.2f}₽",
            f"{total_expenses:,.2f}₽",
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

            fees_total = sum((f.amount for f in fees), Decimal("0"))
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
