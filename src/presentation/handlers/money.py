from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import cast

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.domain.entities.payment import Payment
from src.domain.value_objects.fine_status import FineStatus
from src.domain.value_objects.payment_status import PaymentStatus
from src.domain.value_objects.role import UserRole
from src.infrastructure.database.session import get_session
from src.infrastructure.repositories.fine_repository import FineRepository
from src.infrastructure.repositories.payment_repository import PaymentRepository
from src.infrastructure.repositories.user_repository import UserRepository
from src.presentation.keyboards.common import (
    back_keyboard,
    build_kb,
    confirm_cancel_keyboard,
    payment_action_keyboard,
    payment_type_keyboard,
)
from src.presentation.states import PaymentStates

router = Router()

MONTH_NAMES = {
    "январь": 1, "january": 1, "jan": 1,
    "февраль": 2, "february": 2, "feb": 2,
    "март": 3, "march": 3, "mar": 3,
    "апрель": 4, "april": 4, "apr": 4,
    "май": 5, "may": 5,
    "июнь": 6, "june": 6, "jun": 6,
    "июль": 7, "july": 7, "jul": 7,
    "август": 8, "august": 8, "aug": 8,
    "сентябрь": 9, "september": 9, "sep": 9, "sept": 9,
    "октябрь": 10, "october": 10, "oct": 10,
    "ноябрь": 11, "november": 11, "nov": 11,
    "декабрь": 12, "december": 12, "dec": 12,
}


async def _require_treasurer_or_admin(callback: CallbackQuery) -> bool:
    is_allowed = False
    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(callback.from_user.id)
        if user and (user.role == UserRole.TREASURER or user.role == UserRole.ADMIN):
            is_allowed = True
    if not is_allowed:
        await callback.answer("⛔ Нет доступа", show_alert=True)
    return is_allowed


async def _safe_edit(callback: CallbackQuery, *args, **kwargs) -> None:
    if callback.message is None:
        await callback.answer()
        return
    msg = cast(Message, callback.message)
    await msg.edit_text(*args, **kwargs)


def _parse_payment_amount(text: str) -> Decimal | None:
    value = text.strip()
    if not value:
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", value)
    if not match:
        return None
    try:
        amount = Decimal(match.group(0).replace(",", "."))
        if amount <= 0:
            return None
        return amount
    except InvalidOperation:
        return None


def _parse_payment_month(text: str, default_month: int, default_year: int) -> tuple[int, int]:
    lowered = text.lower()
    for name, month in MONTH_NAMES.items():
        if name in lowered:
            return month, default_year

    for year_text, month_text in re.findall(r"(20\d{2})\s*[./-]?\s*(0?[1-9]|1[0-2])", lowered):
        return int(month_text), int(year_text)
    for month_text, year_text in re.findall(r"(0?[1-9]|1[0-2])\s*[./-]?\s*(20\d{2})", lowered):
        return int(month_text), int(year_text)

    digits = [int(n) for n in re.findall(r"\d+", lowered)]
    for value in digits:
        if 1 <= value <= 12:
            return value, default_year
    return default_month, default_year


def _payment_kind_from_text(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("штраф", "fine", "penalty", "неустой")):
        return "fine"
    if any(word in lowered for word in ("взнос", "сбор", "fee", "monthly", "membership", "член")):
        return "fee"
    return "fee"


@router.callback_query(F.data == "member_pay")
async def member_pay_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(pay_kind="fee")
    await state.set_state(PaymentStates.waiting_amount)
    await _safe_edit(
        callback,
        "📤 <b>Я оплатил</b>\n\n"
        "Что именно оплатили?\n\n"
        "Введите <b>сумму</b> и, при необходимости, месяц или описание.\n"
        "Например: <b>350</b>, <b>350 за июнь</b>, <b>штраф 200</b>",
        reply_markup=payment_type_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_action")
async def cancel_payment(callback: CallbackQuery, state: FSMContext) -> None:
    """Отмена процесса оплаты."""
    await state.clear()
    await callback.answer("❌ Оплата отменена")
    from src.presentation.handlers.common import callback_main_menu
    await callback_main_menu(callback)


@router.callback_query(F.data.startswith("pay_type:"))
async def member_pay_type(callback: CallbackQuery, state: FSMContext) -> None:
    pay_kind = (callback.data or "").split(":", 1)[1]
    await state.update_data(pay_kind=pay_kind)
    await state.set_state(PaymentStates.waiting_amount)
    label = "штраф" if pay_kind == "fine" else "ежемесячный взнос"
    await _safe_edit(
        callback,
        f"📤 <b>Оплата {label}</b>\n\n"
        "Введите <b>сумму</b> и, при необходимости, месяц или описание.\n"
        "Например: <b>350</b>, <b>350 за июнь</b>, <b>штраф 200</b>",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.message(PaymentStates.waiting_amount)
async def member_pay_amount(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return

    # Проверка на отмену
    if message.text.strip().lower() in ("/cancel", "отмена"):
        await state.clear()
        await message.answer("❌ Оплата отменена")
        return

    text = message.text.strip()
    amount = _parse_payment_amount(text)
    if amount is None:
        await message.answer("❌ Не удалось определить сумму. Введите число, например: 350 или 350 за июнь.")
        return

    data = await state.get_data()
    pay_kind = data.get("pay_kind", "fee")
    text_kind = _payment_kind_from_text(text)
    if text_kind == "fine":
        pay_kind = "fine"
    await state.update_data(pay_amount=amount, pay_kind=pay_kind)

    now = datetime.utcnow()
    month, year = _parse_payment_month(text, now.month, now.year)
    if any(token in text.lower() for token in ("для", "за", "месяц", "month", "шин")) or "".join(re.findall(r"\d+", text)):
        await state.update_data(pay_month=month, pay_year=year)
        await state.set_state(PaymentStates.waiting_receipt)
        await message.answer(
            "📸 Отправьте <b>фото чека</b> (или подтверждения перевода).\n"
            "Если фото нет — отправьте /skip:",
            reply_markup=confirm_cancel_keyboard("pay_skip_receipt", "back"),
        )
        return

    await state.set_state(PaymentStates.waiting_month)
    await message.answer(
        f"За какой <b>месяц</b> платите?\n"
        f"(например: {now.month})\n"
        f"Или год.месяц (например: {now.year}.{now.month})\n"
        f"Можно написать месяц текстом: июнь, september, 2025.06",
    )


@router.message(PaymentStates.waiting_month)
async def member_pay_month(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    text = message.text.strip()
    now = datetime.utcnow()
    month, year = _parse_payment_month(text, now.month, now.year)

    if month < 1 or month > 12:
        await message.answer("❌ Месяц должен быть от 1 до 12 или название месяца.")
        return

    await state.update_data(pay_month=month, pay_year=year)
    await state.set_state(PaymentStates.waiting_receipt)
    await message.answer(
        "📸 Отправьте <b>фото чека</b> (или подтверждения перевода).\n"
        "Если фото нет — отправьте /skip:",
        reply_markup=confirm_cancel_keyboard("pay_skip_receipt", "back"),
    )


@router.callback_query(F.data == "pay_skip_receipt")
async def pay_skip_receipt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(pay_receipt=None)
    await _pay_ask_comment(callback, state)


@router.message(PaymentStates.waiting_receipt)
async def member_pay_receipt(message: Message, state: FSMContext) -> None:
    if message.text == "/skip":
        await state.update_data(pay_receipt=None)
    elif message.photo:
        await state.update_data(pay_receipt=message.photo[-1].file_id)
    else:
        await message.answer("❌ Отправьте фото или /skip.")
        return

    await _pay_ask_comment(message, state)


async def _pay_ask_comment(source, state: FSMContext) -> None:
    from aiogram.types import CallbackQuery

    await state.set_state(PaymentStates.waiting_comment)
    if isinstance(source, CallbackQuery):
        await _safe_edit(
            source,
            "💬 Напишите <b>комментарий</b> к платежу (или /skip):",
            reply_markup=confirm_cancel_keyboard("pay_skip_comment", "back"),
        )
    else:
        await source.answer(
            "💬 Напишите <b>комментарий</b> к платежу (или /skip):",
            reply_markup=confirm_cancel_keyboard("pay_skip_comment", "back"),
        )


@router.callback_query(F.data == "pay_skip_comment")
async def pay_skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(pay_comment=None)
    await _pay_finalize(callback, state)


@router.message(PaymentStates.waiting_comment)
async def member_pay_comment(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    if message.text == "/skip":
        await state.update_data(pay_comment=None)
    else:
        await state.update_data(pay_comment=message.text.strip())

    class FakeCallback:
        def __init__(self, msg):
            self.message = msg
            self.from_user = msg.from_user
            self.bot = msg.bot

        async def answer(self):
            pass

    await _pay_finalize(FakeCallback(message), state)


async def _pay_finalize(callback, state: FSMContext) -> None:
    data = await state.get_data()

    async for session in get_session():
        user_repo = UserRepository(session)
        pay_repo = PaymentRepository(session)

        target_user_id = data.get("pay_target_user_id")
        if target_user_id is not None:
            user = await user_repo.get_by_id(int(target_user_id))
            payer_name = user.full_name if user else "Участник"
        else:
            user = await user_repo.get_by_telegram_id(callback.from_user.id)
            payer_name = user.full_name if user else "Участник"
        if not user:
            await callback.message.answer("❌ Ошибка: пользователь не найден")
            await state.clear()
            return

        treasurers = await user_repo.list_by_role(UserRole.TREASURER)
        admins = await user_repo.list_by_role(UserRole.ADMIN)

        payment = Payment(
            user_id=int(user.id) if user and user.id is not None else 0,
            amount=data["pay_amount"],
            month=data["pay_month"],
            year=data["pay_year"],
            payment_type=data.get("pay_kind", "fee"),
            comment=data.get("pay_comment"),
            receipt_photo_id=data.get("pay_receipt"),
            status=PaymentStatus.PENDING,
        )
        created = await pay_repo.create(payment)

        notify_text = (
            f"📤 <b>Новый платёж</b>\n"
            f"👤 {payer_name}\n"
            f"💰 Сумма: <b>{data['pay_amount']:,.2f}₽</b>\n"
            f"📅 За: {data['pay_month']:02d}/{data['pay_year']}\n"
        )
        if data.get("pay_comment"):
            notify_text += f"💬 {data['pay_comment']}\n"
        notify_text += f"\n🆔 Платёж #{created.id}"

        for t in treasurers + admins:
            try:
                kb = payment_action_keyboard(int(created.id) if created and created.id is not None else 0)
                msg = await callback.bot.send_message(t.telegram_id, notify_text)
                if data.get("pay_receipt"):
                    try:
                        await callback.bot.send_photo(t.telegram_id, data["pay_receipt"], caption=f"Чек к платежу #{created.id}")
                    except Exception:
                        pass
                await callback.bot.edit_message_reply_markup(t.telegram_id, msg.message_id, reply_markup=kb)
            except Exception:
                pass

        await callback.message.answer("✅ Платёж отправлен на подтверждение!\nОжидайте, пока казначей его подтвердит.")
    await state.clear()


@router.callback_query(F.data.startswith("treasurer_pay:"))
async def treasurer_manual_pay(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _require_treasurer_or_admin(callback):
        return
    user_id = int((callback.data or "").split(":", 1)[1])
    await state.update_data(pay_target_user_id=user_id, pay_kind="fee")
    await state.set_state(PaymentStates.waiting_amount)
    await _safe_edit(
        callback,
        "💳 <b>Принять оплату</b>\n\nВведите сумму оплаты для участника:",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_fine:"))
async def member_pay_fine(callback: CallbackQuery) -> None:
    fine_id = int((callback.data or "").split(":", 1)[1])
    async for session in get_session():
        fine_repo = FineRepository(session)
        pay_repo = PaymentRepository(session)
        user_repo = UserRepository(session)
        fine = await fine_repo.get_by_id(fine_id)
        if not fine or fine.status != FineStatus.ACTIVE:
            await callback.answer("❌ Штраф не найден или уже закрыт.", show_alert=True)
            return

        amount = fine.remaining_amount
        if amount <= 0:
            await callback.answer("❌ Этот штраф уже полностью оплачен.", show_alert=True)
            return

        payer = await user_repo.get_by_id(fine.user_id)
        if not payer:
            await callback.answer("❌ Пользователь не найден.", show_alert=True)
            return

        payment = Payment(
            user_id=fine.user_id,
            amount=amount,
            month=datetime.utcnow().month,
            year=datetime.utcnow().year,
            payment_type="fine",
            comment=f"Оплата штрафа #{fine.id}",
            status=PaymentStatus.PENDING,
        )
        created = await pay_repo.create(payment)
        await _safe_edit(
            callback,
            f"✅ Запрос на оплату штрафа #{fine.id} отправлен на подтверждение.\nСумма: <b>{amount:,.2f}₽</b>",
            reply_markup=back_keyboard(),
        )

        treasurers = await user_repo.list_by_role(UserRole.TREASURER)
        admins = await user_repo.list_by_role(UserRole.ADMIN)
        for t in treasurers + admins:
            try:
                msg = await callback.bot.send_message(
                    t.telegram_id,
                    f"📤 <b>Новый платёж по штрафу</b>\n👤 {payer.full_name}\n💰 Сумма: <b>{amount:,.2f}₽</b>\n📌 Штраф #{fine.id}",
                )
                await callback.bot.edit_message_reply_markup(
                    t.telegram_id,
                    msg.message_id,
                    reply_markup=payment_action_keyboard(int(created.id) if created and created.id is not None else 0),
                )
            except Exception:
                pass

    await callback.answer()
