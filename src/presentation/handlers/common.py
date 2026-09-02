from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio

from src.config.settings import settings
from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.infrastructure.database.session import get_session
from src.infrastructure.repositories.user_repository import UserRepository
from src.presentation.keyboards.common import main_menu_keyboard
from src.presentation.router_utils import register_or_get_user
from src.presentation.utils import safe_edit, record_bot_message
from src.presentation.middleware.persistent_menu import build_reply_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Handle /start — register user and show main menu."""
    async for session in get_session():
        user = await register_or_get_user(message, session, settings.admin_ids)

    if user:
        if user.status != UserStatus.ACTIVE:
            await message.answer(
                "❌ У вас нет доступа к боту. Обратитесь к администратору.",
            )
            return
        role_label = {
            UserRole.ADMIN: "Администратор",
            UserRole.TREASURER: "Казначей",
            UserRole.MEMBER: "Участник",
        }.get(user.role, "Участник")

        sent = await message.answer(
            f"👋 Добро пожаловать, <b>{user.full_name}</b>!\n"
            f"📌 Роль: {role_label}\n\n"
            f"🏠 <b>Главное меню</b>",
            reply_markup=main_menu_keyboard(user.role),
        )
        record_bot_message(sent.chat.id, sent.message_id)
    else:
        sent = await message.answer("❌ Ошибка регистрации. Попробуйте позже.")
        record_bot_message(sent.chat.id, sent.message_id)


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    """Handle /menu — show main menu without re-registration."""
    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)

    if user and user.status != UserStatus.ACTIVE:
        await message.answer(
            "❌ У вас нет доступа к боту. Отправьте /start после решения с администратором.",
        )
        return

    if user:
        role_label = {
            UserRole.ADMIN: "Администратор",
            UserRole.TREASURER: "Казначей",
            UserRole.MEMBER: "Участник",
        }.get(user.role, "Участник")

        sent = await message.answer(
            f"🏠 <b>Главное меню</b>\n"
            f"👤 {user.full_name} ({role_label})\n\n"
            f"Выберите раздел:",
            reply_markup=main_menu_keyboard(user.role),
        )
        record_bot_message(sent.chat.id, sent.message_id)
    else:
        sent = await message.answer(
            "❌ Вы не зарегистрированы. Отправьте /start",
        )
        record_bot_message(sent.chat.id, sent.message_id)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help — show available commands and info."""
    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)

    if not user:
        await message.answer("❌ Вы не зарегистрированы. Отправьте /start")
        return

    if user.status != UserStatus.ACTIVE:
        await message.answer(
            "❌ У вас нет доступа к боту. Обратитесь к администратору.",
        )
        return

    role_text = {
        UserRole.ADMIN: (
            "👑 <b>Администратор</b>\n"
            "• Управление пользователями\n"
            "• Настройки клуба\n"
            "• Статистика и журнал\n"
            "• /stop_bot - остановить бота\n"
            "• /restart_bot - перезапустить бота"
        ),
        UserRole.TREASURER: (
            "🔑 <b>Казначей</b>\n"
            "• Начисление взносов\n"
            "• Подтверждение платежей\n"
            "• Управление штрафами\n"
            "• Расходы клуба"
        ),
        UserRole.MEMBER: (
            "👤 <b>Участник</b>\n"
            "• Лицевой счёт\n"
            "• Мои платежи и штрафы\n"
            "• Отправка подтверждения оплаты"
        ),
    }.get(user.role, "")

    sent = await message.answer(
        f"❓ <b>Помощь</b>\n\n"
        f"<b>Команды:</b>\n"
        f"/start — регистрация и главное меню\n"
        f"/menu — открыть меню\n"
        f"/help — эта справка\n"
        f"/button — показать панель кнопок под полем ввода\n"
        f"/hidebutton — скрыть панель кнопок\n"
        f"{'/stop_bot - остановить бота (админ)' if user.role == UserRole.ADMIN else ''}\n"
        f"{'/restart_bot - перезапустить бота (админ)' if user.role == UserRole.ADMIN else ''}\n\n"
        f"{role_text}\n\n"
        f"💡 Используйте кнопки меню для навигации.",
        reply_markup=main_menu_keyboard(user.role),
    )
    record_bot_message(sent.chat.id, sent.message_id)


@router.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Return to main menu."""
    await state.clear()
    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(callback.from_user.id)

    if user:
        role_label = {
            UserRole.ADMIN: "Администратор",
            UserRole.TREASURER: "Казначей",
            UserRole.MEMBER: "Участник",
        }.get(user.role, "Участник")

        await safe_edit(
            callback,
            f"🏠 <b>Главное меню</b>\n"
            f"👤 {user.full_name} ({role_label})\n\n"
            f"Выберите раздел:",
            reply_markup=main_menu_keyboard(user.role),
        )
    await callback.answer()


@router.callback_query(F.data == "my_budget")
async def callback_my_budget(callback: CallbackQuery, state: FSMContext) -> None:
    """Мой бюджет - личный счёт, платежи, штрафы."""
    await state.clear()
    from src.presentation.keyboards.common import my_budget_keyboard

    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(callback.from_user.id)

    if user:
        await safe_edit(
            callback,
            f"💰 <b>Мой бюджет</b>\n"
            f"👤 {user.full_name}\n\n"
            f"Здесь вы можете посмотреть свой счёт, историю платежей и штрафов.",
            reply_markup=my_budget_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "club_budget")
async def callback_club_budget(callback: CallbackQuery, state: FSMContext) -> None:
    """Бюджет клуба - для казначея и админа."""
    await state.clear()
    from src.presentation.keyboards.common import club_budget_keyboard

    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(callback.from_user.id)

    if user and user.role in (UserRole.TREASURER, UserRole.ADMIN):
        await safe_edit(
            callback,
            f"💼 <b>Бюджет клуба</b>\n\n"
            f"Управление взносами, платежами, штрафами и расходами клуба.",
            reply_markup=club_budget_keyboard(),
        )
    else:
        await callback.answer("⛔ Нет доступа", show_alert=True)


# Message handlers for persistent menu buttons (sent as text when clicked)
@router.message(F.text == "💰 Мой бюджет")
async def msg_my_budget(message: Message, state: FSMContext) -> None:
    """Handle persistent menu button: 💰 Мой бюджет."""
    await state.clear()
    from src.presentation.keyboards.common import my_budget_keyboard

    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)

    if user:
        sent = await message.answer(
            f"💰 <b>Мой бюджет</b>\n"
            f"👤 {user.full_name}\n\n"
            f"Здесь вы можете посмотреть свой счёт, историю платежей и штрафов.",
            reply_markup=my_budget_keyboard(),
        )
        record_bot_message(sent.chat.id, sent.message_id)


@router.message(F.text == "💼 Бюджет клуба")
async def msg_club_budget(message: Message, state: FSMContext) -> None:
    """Handle persistent menu button: 💼 Бюджет клуба."""
    await state.clear()
    from src.presentation.keyboards.common import club_budget_keyboard

    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)

    if user and user.role in (UserRole.TREASURER, UserRole.ADMIN):
        sent = await message.answer(
            f"💼 <b>Бюджет клуба</b>\n\n"
            f"Управление взносами, платежами, штрафами и расходами клуба.",
            reply_markup=club_budget_keyboard(),
        )
        record_bot_message(sent.chat.id, sent.message_id)
    else:
        sent = await message.answer("⛔ Нет доступа")
        record_bot_message(sent.chat.id, sent.message_id)


@router.callback_query(F.data == "admin_management")
async def callback_admin_management(callback: CallbackQuery, state: FSMContext) -> None:
    """Управление - только для админа."""
    await state.clear()
    from src.presentation.keyboards.common import admin_management_keyboard

    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(callback.from_user.id)

    if user and user.role == UserRole.ADMIN:
        await safe_edit(
            callback,
            f"👑 <b>Управление клубом</b>\n\n"
            f"Пользователи, настройки, журнал действий и экспорт данных.",
            reply_markup=admin_management_keyboard(),
        )
    else:
        await callback.answer("⛔ Нет доступа", show_alert=True)


@router.callback_query(F.data == "cancel_action")
async def callback_cancel_action(callback: CallbackQuery, state: FSMContext) -> None:
    """Отмена текущего действия и возврат в главное меню."""
    await state.clear()
    await callback.answer("❌ Действие отменено")
    await callback_main_menu(callback)


@router.callback_query(F.data == "back")
async def callback_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Generic back — navigate to previous screen or main menu."""
    await state.clear()
    from src.presentation.middleware.navigation import push_nav, pop_nav
    from src.presentation.handlers.admin import (
        admin_treasury, admin_users, admin_user_list, admin_settings,
        admin_stats, admin_log, admin_export, expense_menu, expense_list,
        expense_add_start, expense_view,
    )
    from src.presentation.handlers.treasurer import (
        list_pending_payments, list_members, show_stats, send_reminders,
        member_account, member_payments, member_fines, member_fees, member_details,
        member_fees_for_user, treasurer_timeline, timeline_user, timeline_item,
    )
    from src.presentation.handlers.fines import treasurer_fines
    from src.presentation.handlers.ledger_edit import (
        ledger_edit_payment, ledger_edit_fine, ledger_edit_fee,
    )

    previous = pop_nav(callback.from_user.id)

    # Re-push previous screen so middleware doesn't duplicate it when handler runs
    from src.presentation.middleware.navigation import push_nav
    push_nav(callback.from_user.id, previous)

    # Map callback_data to handler functions
    handlers = {
        "main_menu": callback_main_menu,
        "my_budget": callback_my_budget,
        "club_budget": callback_club_budget,
        "admin_management": callback_admin_management,
        "admin_treasury": admin_treasury,
        "admin_users": admin_users,
        "admin_user_list": admin_user_list,
        "admin_settings": admin_settings,
        "admin_stats": admin_stats,
        "admin_log": admin_log,
        "admin_export": admin_export,
        "treasurer_expenses": expense_menu,
        "expense_list": expense_list,
        "treasurer_fines": treasurer_fines,
        "treasurer_pending": list_pending_payments,
        "treasurer_members": list_members,
        "treasurer_stats": show_stats,
        "treasurer_remind": send_reminders,
        "member_account": member_account,
        "member_payments": member_payments,
        "member_fines": member_fines,
        "member_fees": member_fees,
        "member_fees:user_id": member_fees_for_user,
        "member_details": member_details,
    }

    # Handle keyed handlers (need extra args from callback data)
    key = previous
    handler = handlers.get(key)
    if handler:
        # Pass state to handlers that accept it, skip for others
        import inspect
        sig = inspect.signature(handler)
        if "state" in sig.parameters:
            await handler(callback, state)
        else:
            await handler(callback)
    elif key.startswith("ledger_edit_payment:"):
        await ledger_edit_payment(callback, state)
    elif key.startswith("ledger_edit_fine:"):
        await ledger_edit_fine(callback, state)
    elif key.startswith("ledger_edit_fee:"):
        await ledger_edit_fee(callback, state)
    elif key == "expense_add":
        await expense_add_start(callback, state)
    elif key.startswith("expense_view:"):
        await expense_view(callback)
    elif key == "treasurer_timeline":
        await treasurer_timeline(callback)
    elif key.startswith("timeline_user:"):
        await timeline_user(callback)
    elif key.startswith("timeline_item:"):
        await timeline_item(callback)
    else:
        await callback_main_menu(callback, state)


@router.message(Command("stop_bot"))
async def cmd_stop_bot(message: Message) -> None:
    """Остановить бота (только для админа)."""
    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)

    if not user or user.role != UserRole.ADMIN:
        await message.answer("⛔ Команда доступна только администраторам.")
        return

    # Получаем middleware и останавливаем бота
    from src.presentation.bot import get_bot_status_middleware
    status_middleware = get_bot_status_middleware()

    if status_middleware:
        status_middleware.stop_bot()

    await message.answer(
        "🛑 <b>Бот остановлен!</b>\n\n"
        "Бот перестанет отвечать на команды.\n\n"
        "Чтобы запустить бота снова:\n"
        "1. Отправьте команду /restart_bot\n"
        "2. Или Railway → Deployments → Restart\n\n"
        "⚠️ Все пользователи увидят сообщение о том, что бот остановлен."
    )

    # Логируем остановку
    print(f"⚠️ Бот остановлен администратором {user.full_name} (ID: {user.telegram_id})")


@router.message(Command("restart_bot"))
async def cmd_restart_bot(message: Message) -> None:
    """Перезапустить бота (только для админа)."""
    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)

    if not user or user.role != UserRole.ADMIN:
        await message.answer("⛔ Команда доступна только администраторам.")
        return

    # Получаем middleware и запускаем бота
    from src.presentation.bot import get_bot_status_middleware
    status_middleware = get_bot_status_middleware()

    if status_middleware:
        status_middleware.start_bot()

    await message.answer(
        "🔄 <b>Бот перезапущен!</b>\n\n"
        "Бот снова отвечает на команды.\n\n"
        "Отправьте /start для продолжения работы.\n\n"
        "✅ Все пользователи могут использовать бота."
    )

    # Логируем перезапуск
    print(f"✅ Бот перезапущен администратором {user.full_name} (ID: {user.telegram_id})")


@router.message(Command("button"))
async def cmd_show_button(message: Message) -> None:
    """Показать persistent-панель кнопок под полем ввода."""
    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(message.from_user.id)

    if not user or user.status != UserStatus.ACTIVE:
        await message.answer("❌ Вы не зарегистрированы. Отправьте /start")
        return

    kb = build_reply_keyboard(user.role)
    await message.answer("👇 Панель управления", reply_markup=kb)


@router.message(Command("hidebutton"))
async def cmd_hide_button(message: Message, state: FSMContext) -> None:
    """Скрыть persistent-панель кнопок под полем ввода."""
    await state.clear()
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

    kb = ReplyKeyboardMarkup(
        keyboard=[],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )
    await message.answer("", reply_markup=kb)


