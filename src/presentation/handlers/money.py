from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
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
from src.infrastructure.timezone import now_msk, today_msk
from src.presentation.keyboards.common import (
    back_keyboard,
    build_kb,
    confirm_cancel_keyboard,
    main_menu_keyboard,
    payment_action_keyboard,
    payment_type_keyboard,
)
from src.presentation.handlers.common import callback_main_menu
from src.presentation.states import PaymentStates
from src.presentation.utils import safe_edit, require_role, require_treasurer_or_admin

router = Router()
logger = logging.getLogger(__name__)

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
    await safe_edit(
        callback,
        "📤 <b>Я оплатил</b>\n\n"
        "Введите <b>сумму</b> оплаты:",
        reply_markup=payment_type_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_type:"))
async def member_pay_type(callback: CallbackQuery, state: FSMContext) -> None:
    pay_kind = (callback.data or "").split(":", 1)[1]
    await state.update_data(pay_kind=pay_kind)
    await state.set_state(PaymentStates.waiting_amount)
    label = "штраф" if pay_kind == "fine" else "ежемесячный взнос"
    await safe_edit(
        callback,
        f"📤 <b>Оплата {label}</b>\n\n"
        "Введите <b>сумму</b> оплаты:",
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
        await message.answer("❌ Оплата отменена", reply_markup=main_menu_keyboard(UserRole.MEMBER))
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

    now = now_msk()
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
    now = now_msk()
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
        await safe_edit(
            source,
            "💬 Напишите <b>комментарий</b> к платежу (или /skip):",
            reply_markup=confirm_cancel_keyboard("pay_skip_comment", "back"),
        )
    else:
        await source.reply(
            "💬 Напишите <b>комментарий</b> к платежу (или /skip):",
            reply_markup=confirm_cancel_keyboard("pay_skip_comment", "back"),
        )


@router.callback_query(F.data == "pay_skip_comment")
async def pay_skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(pay_comment=None)
    await _pay_finalize(callback.from_user.id, callback.bot, state)


@router.message(PaymentStates.waiting_comment)
async def member_pay_comment(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    if message.text == "/skip":
        await state.update_data(pay_comment=None)
    else:
        await state.update_data(pay_comment=message.text.strip())

    # In aiogram 3.x, get bot from message via message.bot (works in message handlers)
    # message.from_user can be None (e.g. messages sent on behalf of a channel),
    # fall back to chat id in that case to avoid attribute access on None.
    user_id = message.from_user.id if message.from_user is not None else message.chat.id
    await _pay_finalize(user_id, message.bot, state)


async def _pay_finalize(user_id: int, bot, state: FSMContext) -> None:
    """Finalize payment creation and notify treasurers/admins.

    Args:
        user_id: Telegram ID of the payer
        bot: Bot instance (from callback.bot or message.bot)
        state: FSM state with payment data
    """
    data = await state.get_data()

    async for session in get_session():
        user_repo = UserRepository(session)
        pay_repo = PaymentRepository(session)

        target_user_id = data.get("pay_target_user_id")
        if target_user_id is not None:
            user = await user_repo.get_by_id(int(target_user_id))
            payer_name = user.full_name if user else "Участник"
        else:
            user = await user_repo.get_by_telegram_id(user_id)
            payer_name = user.full_name if user else "Участник"
        if not user:
            await bot.send_message(user_id, "❌ Ошибка: пользователь не найден")
            await state.clear()
            return

        treasurers = await user_repo.list_by_role(UserRole.TREASURER)
        admins = await user_repo.list_by_role(UserRole.ADMIN)

        fine_id = data.get("pay_fine_id")
        payment_type = data.get("pay_kind", "fee")
        comment = data.get("pay_comment")
        if fine_id and not comment:
            comment = f"Оплата штрафа #{fine_id}"
        elif fine_id and comment:
            comment = f"{comment} (штраф #{fine_id})"

        payment = Payment(
            user_id=int(user.id) if user and user.id is not None else 0,
            amount=data["pay_amount"],
            month=data["pay_month"],
            year=data["pay_year"],
            payment_type=payment_type,
            comment=comment,
            receipt_photo_id=data.get("pay_receipt"),
            status=PaymentStatus.PENDING,
        )
        created = await pay_repo.create(payment)

        _MONTHS_RU = ["января","февраля","марта","апреля","мая","июня",
                       "июля","августа","сентября","октября","ноября","декабря"]
        pay_dt = today_msk()
        pay_date_str = f"{pay_dt.day} {_MONTHS_RU[pay_dt.month - 1]} {pay_dt.year} года"

        # Build detailed payer info: Name (@username) — Role
        if user:
            role_label = {
                "admin": "Администратор",
                "treasurer": "Казначей",
                "member": "Участник",
            }.get(user.role.value, user.role.value)
            user_tag = f"@{user.username}" if user.username else f"id{user.telegram_id}"
            payer_info = f"{payer_name} ({user_tag}) — {role_label}"
        else:
            payer_info = payer_name

        notify_text = (
            f"📤 <b>Новый платёж</b>\n"
            f"👤 {payer_info}\n"
            f"💰 Сумма: <b>{data['pay_amount']:,.2f}₽</b>\n"
            f"📅 За: {pay_date_str}\n"
        )
        if payment_type == "fine":
            notify_text += f"📌 <b>Тип: Оплата штрафа</b>\n"
        if comment:
            notify_text += f"💬 {comment}\n"
        notify_text += f"\n🆔 Платёж #{created.id}"

        kb = payment_action_keyboard(int(created.id) if created and created.id is not None else 0)

        for t in treasurers + admins:
            try:
                # Send photo with caption and keyboard if receipt exists
                if data.get("pay_receipt"):
                    await bot.send_photo(
                        t.telegram_id,
                        data["pay_receipt"],
                        caption=notify_text,
                        reply_markup=kb,
                    )
                else:
                    await bot.send_message(t.telegram_id, notify_text, reply_markup=kb)
            except Exception:
                logger.exception("Failed to notify treasurer/admin about payment #%s", created.id)

        await bot.send_message(user_id, "✅ Платёж отправлен на подтверждение!\nОжидайте, пока казначей его подтвердит.")
    await state.clear()
    # Return to main menu after payment flow completes
    async for sess in get_session():
        user = await UserRepository(sess).get_by_telegram_id(user_id)
        kb = main_menu_keyboard(user.role if user else UserRole.MEMBER)
        await bot.send_message(user_id, "🏠 Главное меню", reply_markup=kb)


@router.callback_query(F.data.startswith("treasurer_pay:"))
async def treasurer_manual_pay(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_treasurer_or_admin(callback):
        return
    user_id = int((callback.data or "").split(":", 1)[1])
    await state.update_data(pay_target_user_id=user_id, pay_kind="fee")
    await state.set_state(PaymentStates.waiting_amount)
    await safe_edit(
        callback,
        "💳 <b>Принять оплату</b>\n\nВведите сумму оплаты для участника:",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_fine:"))
async def member_pay_fine(callback: CallbackQuery, state: FSMContext) -> None:
    fine_id = int((callback.data or "").split(":", 1)[1])
    async for session in get_session():
        fine_repo = FineRepository(session)
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

        # Save fine_id and payment data to state, then redirect to receipt/comment flow
        now = now_msk()
        await state.update_data(
            pay_kind="fine",
            pay_amount=amount,
            pay_month=now.month,
            pay_year=now.year,
            pay_fine_id=fine.id,
        )
        await state.set_state(PaymentStates.waiting_receipt)
        await safe_edit(
            callback,
            f"📤 <b>Оплата штрафа #{fine.id}</b>\n"
            f"Сумма к оплате: <b>{amount:,.2f}₽</b>\n\n"
            f"📸 Отправьте <b>фото чека</b> (или подтверждения перевода).\n"
            f"Если фото нет — отправьте /skip:",
            reply_markup=confirm_cancel_keyboard("pay_skip_receipt", "back"),
        )
    await callback.answer()
