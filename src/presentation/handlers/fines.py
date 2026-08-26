from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.domain.entities.audit_log import AuditLog
from src.domain.entities.fine import Fine
from src.domain.value_objects.fine_status import FineStatus
from src.domain.value_objects.role import UserRole
from src.infrastructure.database.session import get_session
from src.infrastructure.repositories.audit_repository import AuditLogRepository
from src.infrastructure.repositories.fine_repository import FineRepository
from src.infrastructure.repositories.user_repository import UserRepository
from src.presentation.keyboards.common import back_keyboard, build_kb, confirm_cancel_keyboard
from src.presentation.utils import safe_edit, require_role
from src.presentation.states import FineStates

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("fine_issue:"))
async def fine_issue_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_role(callback, UserRole.TREASURER):
        return
    user_id = int((callback.data or "").split(":", 1)[1])
    await state.update_data(fine_user_id=user_id)
    await state.set_state(FineStates.waiting_amount)
    await safe_edit(
        callback,
        "⚠️ <b>Начисление штрафа</b>\n\nВведите сумму штрафа:",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.message(FineStates.waiting_amount)
async def fine_issuer_amount(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return

    # Проверка на отмену
    if message.text.strip().lower() in ("/cancel", "отмена"):
        await state.clear()
        await message.answer("❌ Начисление штрафа отменено")
        return

    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
        await state.update_data(fine_amount=amount)
        await state.set_state(FineStates.waiting_reason)
        await message.answer("Введите <b>причину</b> штрафа:\n\n💡 Или /cancel для отмены")
    except (ValueError, InvalidOperation):
        await message.answer("❌ Введите положительное число.")


@router.message(FineStates.waiting_reason)
async def fine_issue_reason(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    await state.update_data(fine_reason=message.text.strip())
    await state.set_state(FineStates.waiting_comment)
    await message.answer(
        "Введите <b>комментарий</b> (или отправьте /skip):",
        reply_markup=confirm_cancel_keyboard("fine_skip_comment", "back"),
    )


@router.callback_query(F.data == "fine_skip_comment")
async def fine_skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(fine_comment=None)
    await _fine_finalize(callback, state)


@router.message(FineStates.waiting_comment)
async def fine_issue_comment(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    if message.text == "/skip":
        await state.update_data(fine_comment=None)
    else:
        await state.update_data(fine_comment=message.text.strip())

    class FakeCallback:
        def __init__(self, msg):
            self.message = msg
            self.from_user = msg.from_user
            self.bot = msg.bot

        async def answer(self):
            pass

    await _fine_finalize(FakeCallback(message), state)


async def _fine_finalize(callback, state: FSMContext) -> None:
    data = await state.get_data()
    async for session in get_session():
        user_repo = UserRepository(session)
        fine_repo = FineRepository(session)
        audit_repo = AuditLogRepository(session)

        issuer = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not issuer:
            await callback.message.answer("❌ Ошибка")
            await state.clear()
            return

        user = await user_repo.get_by_id(data["fine_user_id"])
        fine = Fine(
            user_id=data["fine_user_id"],
            amount=data["fine_amount"],
            reason=data["fine_reason"],
            comment=data.get("fine_comment"),
            issued_by=int(issuer.id) if issuer and issuer.id is not None else 0,
            status=FineStatus.ACTIVE,
        )
        created = await fine_repo.create(fine)

        await audit_repo.create(AuditLog(
            user_id=int(issuer.id) if issuer and issuer.id is not None else 0,
            action="issue_fine",
            entity_type="fine",
            entity_id=created.id,
            details={
                "user_id": data["fine_user_id"],
                "amount": str(data["fine_amount"]),
                "reason": data["fine_reason"],
            },
        ))

        await callback.message.answer(
            f"✅ Штраф начислен!\n"
            f"👤 {user.full_name if user else '?'}\n"
            f"💰 Сумма: <b>{data['fine_amount']:,.2f}₽</b>\n"
            f"📌 Причина: {data['fine_reason']}",
        )

        try:
            if user:
                await callback.bot.send_message(
                    user.telegram_id,
                    f"⚠️ Вам начислен штраф!\n"
                    f"💰 Сумма: <b>{data['fine_amount']:,.2f}₽</b>\n"
                    f"📌 Причина: {data['fine_reason']}",
                )
        except Exception:
            logger.exception("Failed to notify user %s about fine", data["fine_user_id"])

    await state.clear()


@router.callback_query(F.data.startswith("fine_cancel:"))
async def fine_cancel(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.TREASURER):
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
        if fine.status != FineStatus.ACTIVE:
            await callback.answer("❌ Штраф уже отменён.", show_alert=True)
            return

        fine.status = FineStatus.CANCELLED
        canceller = await user_repo.get_by_telegram_id(callback.from_user.id)
        fine.cancelled_by = int(canceller.id) if canceller and canceller.id is not None else None
        fine.cancelled_at = datetime.utcnow()
        await fine_repo.update(fine)

        await audit_repo.create(AuditLog(
            user_id=int(fine.cancelled_by) if fine.cancelled_by is not None else 0,
            action="cancel_fine",
            entity_type="fine",
            entity_id=fine.id,
            details={"user_id": fine.user_id, "fine_id": fine.id},
        ))

        await safe_edit(
            callback,
            f"✅ Штраф #{fine.id} отменён.",
            reply_markup=back_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "treasurer_fines")
async def treasurer_fines(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.TREASURER):
        return
    async for session in get_session():
        repo = FineRepository(session)
        fines = await repo.list_active()
        if not fines:
            await safe_edit(callback, "✅ Активных штрафов нет.", reply_markup=back_keyboard())
            await callback.answer()
            return

        lines = ["⚠️ <b>Активные штрафы</b>:\n"]
        keyboard_rows = []
        for f in fines[:20]:
            lines.append(f"ID#{f.id} — {f.amount:,.2f}₽ — {f.reason}")
            keyboard_rows.append([("💳 Оплатить", f"pay_fine:{f.id}"), ("❌ Отменить", f"fine_cancel:{f.id}")])
        await safe_edit(callback, "\n".join(lines), reply_markup=build_kb(keyboard_rows + [[("🔙 Назад", "back")]]))
    await callback.answer()
