from __future__ import annotations

import io
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html import escape

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputFile, Message

from src.domain.entities.audit_log import AuditLog
from src.domain.entities.expense import Expense
from src.domain.entities.fine import Fine
from src.domain.entities.payment import Payment
from src.domain.entities.user import User
from src.domain.value_objects.expense_category import ExpenseCategory
from src.domain.value_objects.fine_status import FineStatus
from src.domain.value_objects.payment_status import PaymentStatus
from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.infrastructure.database.session import get_session
from src.infrastructure.repositories.audit_repository import AuditLogRepository
from src.infrastructure.database.models.audit_log import AuditLogModel
from sqlalchemy import select
from src.infrastructure.repositories.expense_repository import ExpenseRepository
from src.infrastructure.repositories.fine_repository import FineRepository
from src.infrastructure.repositories.payment_repository import PaymentRepository
from src.infrastructure.repositories.settings_repository import ClubSettingsRepository
from src.infrastructure.repositories.user_repository import UserRepository
from src.presentation.keyboards.common import (
    admin_settings_keyboard,
    admin_users_keyboard,
    admin_users_list_keyboard,
    back_keyboard,
    build_kb,
    confirm_cancel_keyboard,
    confirm_keyboard,
    expense_categories_keyboard,
    main_menu_keyboard,
    user_actions_keyboard,
)
from src.presentation.texts import (
    ACCESS_DENIED,
    stats_text,
)
from src.presentation.states import (
    AddUserStates,
    ExpenseStates,
    FineStates,
    PaymentStates,
    SearchUserStates,
    SettingsStates,
)

router = Router()


async def _safe_edit(callback: CallbackQuery, *args, **kwargs) -> None:
    """Safely edit callback message if present, otherwise answer the callback."""
    if callback.message is None:
        await callback.answer()
        return
    await callback.message.edit_text(*args, **kwargs)


# ─── Фильтр для проверки прав ────────────────────

async def _require_role(callback: CallbackQuery, role: UserRole) -> bool:
    """Check if user has required role. Returns True if allowed."""
    is_allowed = False
    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(callback.from_user.id)
        if user and user.status == UserStatus.ACTIVE and (user.role == role or user.role == UserRole.ADMIN):
            is_allowed = True
    if not is_allowed:
        await callback.answer(ACCESS_DENIED, show_alert=True)
    return is_allowed


# ─── Админ: казна (доступ к функциям казначея) ────

@router.callback_query(F.data == "admin_treasury")
async def admin_treasury(callback: CallbackQuery) -> None:
    if not await _require_role(callback, UserRole.ADMIN):
        return
    if callback.message is None:
        await callback.answer()
        return
    msg = callback.message
    await msg.edit_text(
        "💰 <b>Казна клуба</b>\nВыберите действие:",
        reply_markup=main_menu_keyboard(UserRole.TREASURER),
    )
    await callback.answer()
@router.callback_query(F.data == "admin_user_add")
async def admin_user_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _require_role(callback, UserRole.ADMIN):
        return
    await state.set_state(AddUserStates.waiting_telegram_id)
    if callback.message is None:
        await callback.answer()
        return
    msg = callback.message
    await msg.edit_text(
        "➕ <b>Добавление участника</b>\n\n"
        "Введите <b>Telegram ID</b> или <b>@username</b> пользователя:\n"
        "• ID: число из @userinfobot\n"
        "• @username: если пользователь уже запускал бота",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.message(AddUserStates.waiting_telegram_id)
async def admin_user_add_tgid(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    text = message.text.strip()

    # @username — resolve via Telegram API
    if text.startswith("@"):
        try:
            chat = await message.bot.get_chat(text)
            tg_id = chat.id
            resolved_name = chat.full_name or chat.first_name or text
            resolved_username = chat.username
            await state.update_data(
                telegram_id=tg_id,
                resolved_name=resolved_name,
                resolved_username=resolved_username,
            )
        except Exception:
            await message.answer(
                "❌ Не удалось найти пользователя по этому username.\n"
                "Убедитесь, что пользователь уже запускал бота.\n"
                "Попробуйте числовой ID из @userinfobot."
            )
            return
        await state.set_state(AddUserStates.waiting_full_name)
        await message.answer(
            f"Введите <b>имя</b> участника (найдено: {resolved_name}):\n"
            f"или отправьте /skip чтобы оставить «{resolved_name}»"
        )
        return

    # Числовой ID
    try:
        tg_id = int(text)
        await state.update_data(telegram_id=tg_id)
    except ValueError:
        await message.answer("❌ Введите Telegram ID (число) или @username.")
        return
    await state.set_state(AddUserStates.waiting_full_name)
    await message.answer("Введите <b>имя</b> участника:")


@router.message(AddUserStates.waiting_full_name)
async def admin_user_add_name(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if message.text is None:
        return
    if message.text.strip() == "/skip" and "resolved_name" in data:
        await state.update_data(full_name=data["resolved_name"])
    else:
        await state.update_data(full_name=message.text.strip())
    kb = build_kb([
        [("👤 Участник", "adduser_role:member")],
        [("🔑 Казначей", "adduser_role:treasurer")],
        [("👑 Админ", "adduser_role:admin")],
        [("🔙 Отмена", "back")],
    ])
    await state.set_state(AddUserStates.waiting_role)
    await message.answer("Выберите <b>роль</b>:", reply_markup=kb)


@router.callback_query(AddUserStates.waiting_role, F.data.startswith("adduser_role:"))
async def admin_user_add_role(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data:
        await callback.answer()
        return
    role_str = callback.data.split(":")[1]
    role = UserRole(role_str)
    data = await state.get_data()

    async for session in get_session():
        repo = UserRepository(session)
        existing = await repo.get_by_telegram_id(data["telegram_id"])
        if existing:
            await _safe_edit(
                callback,
                f"❌ Пользователь с ID {data['telegram_id']} уже существует!",
                reply_markup=back_keyboard(),
            )
            break

        user = User(
            telegram_id=data["telegram_id"],
            full_name=data["full_name"],
            username=data.get("resolved_username"),
            role=role,
            status=UserStatus.ACTIVE,
        )
        created = await repo.create(user)

        # Audit
        admin = await repo.get_by_telegram_id(callback.from_user.id)
        if admin:
            ar = AuditLogRepository(session)
            await ar.create(AuditLog(
                user_id=int(admin.id) if admin.id is not None else 0,
                action="add_user",
                entity_type="user",
                entity_id=int(created.id) if created.id is not None else 0,
                details={"telegram_id": data["telegram_id"], "role": role_str},
            ))

        users = await repo.list_all()
        users_list = [
            (int(u.id) if u.id is not None else 0, f"{u.full_name} @{u.username}" if u.username else u.full_name)
            for u in users if u.status != UserStatus.EXPELLED
        ]
        profile_line = (
            f"<a href=\"https://t.me/{escape(created.username)}\">@{escape(created.username)}</a>"
            if created.username
            else str(created.telegram_id)
        )
        await _safe_edit(
            callback,
            f"✅ Пользователь <b>{escape(created.full_name)}</b> добавлен!\n"
            f"Роль: {role_str}\n"
            f"Telegram: {profile_line}\n\n"
            f"👥 <b>Список участников</b> (выделен новый пользователь):",
            reply_markup=admin_users_list_keyboard(users_list, highlight_id=int(created.id) if created.id is not None else None),
        )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "admin_user_list")
async def admin_user_list(callback: CallbackQuery) -> None:
    if not await _require_role(callback, UserRole.ADMIN):
        return
    await _show_admin_user_page(callback, 0)


@router.callback_query(F.data.startswith("admin_users_page:"))
async def admin_users_page(callback: CallbackQuery) -> None:
    if not await _require_role(callback, UserRole.ADMIN):
        return
    page = int(callback.data.split(":")[1])
    await _show_admin_user_page(callback, page)


async def _show_admin_user_page(callback: CallbackQuery, page: int) -> None:
    async for session in get_session():
        repo = UserRepository(session)
        users = await repo.list_all()
        text = "👥 <b>Все пользователи</b>:\n\n"
        for u in users:
            role_icon = {"admin": "👑", "treasurer": "🔑", "member": "👤"}
            icon = role_icon.get(u.role.value, "👤")
            status_icon = {
                UserStatus.ACTIVE: "🟢",
                UserStatus.ARCHIVED: "🟡",
                UserStatus.EXPELLED: "🔴",
            }.get(u.status, "🔴")
            username_link = (
                f"<a href=\"https://t.me/{escape(u.username)}\">@{escape(u.username)}</a>"
                if u.username
                else "—"
            )
            text += f"{icon} <b>{escape(u.full_name)}</b> {status_icon} — {username_link}\n"
            text += f"   ID: {u.id} | {escape(u.role.value)}\n"
        users_list = [
            (int(u.id) if u.id is not None else 0, f"{u.full_name} @{u.username}" if u.username else u.full_name)
            for u in users
        ]
        await _safe_edit(
            callback,
            text,
            reply_markup=admin_users_list_keyboard(users_list, page),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_role_"))
async def admin_change_role(callback: CallbackQuery) -> None:
    if not await _require_role(callback, UserRole.ADMIN):
        return
    # Format: admin_role_admin:user_id or admin_role_treasurer:user_id or admin_role_member:user_id
    if not callback.data:
        await callback.answer()
        return
    parts = callback.data.split(":")
    role_str = parts[0].replace("admin_role_", "")
    user_id = int(parts[1])

    role_map = {"admin": UserRole.ADMIN, "treasurer": UserRole.TREASURER, "member": UserRole.MEMBER}
    new_role = role_map.get(role_str)
    if not new_role:
        await callback.answer("❌ Неверная роль")
        return

    async for session in get_session():
        repo = UserRepository(session)
        audit_repo = AuditLogRepository(session)

        user = await repo.get_by_id(user_id)
        if not user:
            await _safe_edit(
                callback,
                "❌ Пользователь не найден",
                reply_markup=back_keyboard(),
            )
            break
        user.role = new_role
        await repo.update(user)

        admin = await repo.get_by_telegram_id(callback.from_user.id)
        if admin:
            await audit_repo.create(AuditLog(
                user_id=int(admin.id) if admin.id is not None else 0,
                action="change_role",
                entity_type="user",
                entity_id=user.id,
                details={"new_role": role_str, "user_id": user.id},
            ))

        await _safe_edit(
            callback,
            f"✅ Роль обновлена: <b>{user.full_name}</b> → {role_str}",
            reply_markup=back_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_archive:"))
async def admin_archive_user(callback: CallbackQuery) -> None:
    if not await _require_role(callback, UserRole.ADMIN):
        return
    user_id = int(callback.data.split(":")[1])

    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if not user:
            await callback.message.edit_text(
                "❌ Пользователь не найден",
                reply_markup=back_keyboard(),
            )
            break

        user.status = UserStatus.ARCHIVED
        await repo.update(user)

        await callback.message.edit_text(
            f"📦 Пользователь <b>{user.full_name}</b> архивирован.",
            reply_markup=back_keyboard(),
        )
    await callback.answer()


# ─── Админ: удаление пользователя ───────────────────

@router.callback_query(F.data.startswith("admin_delete_confirm:"))
async def admin_delete_confirm(callback: CallbackQuery) -> None:
    """Ask for confirmation before deleting a user."""
    if not await _require_role(callback, UserRole.ADMIN):
        return
    user_id = int(callback.data.split(":")[1])

    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if not user:
            await callback.message.edit_text(
                "❌ Пользователь не найден",
                reply_markup=back_keyboard(),
            )
            break

        await callback.message.edit_text(
            f"⚠️ <b>Вы уверены?</b>\n\n"
            f"Пользователь <b>{user.full_name}</b> "
            f"(ID: {user.telegram_id}) будет удалён.",
            reply_markup=build_kb([
                [("🗑 Удалить (soft)", f"admin_delete_execute:{user_id}")],
                [("🧨 Удалить навсегда", f"admin_hard_delete_execute:{user_id}")],
                [("❌ Отмена", f"user_actions:{user_id}")],
            ]),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_execute:"))
async def admin_delete_execute(callback: CallbackQuery) -> None:
    """Soft-delete a user after confirmation."""
    if not await _require_role(callback, UserRole.ADMIN):
        return
    if not callback.data:
        await callback.answer()
        return
    user_id = int(callback.data.split(":")[1])

    async for session in get_session():
        repo = UserRepository(session)
        audit_repo = AuditLogRepository(session)

        user = await repo.get_by_id(user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        name = user.full_name
        previous_role = user.role.value if user.role else None
        await repo.delete(user_id)

        admin = await repo.get_by_telegram_id(callback.from_user.id)
        if admin:
            await audit_repo.create(AuditLog(
                user_id=admin.id,
                action="delete_user",
                entity_type="user",
                entity_id=user_id,
                details={
                    "deleted_user": name,
                    "telegram_id": user.telegram_id,
                    "previous_role": previous_role,
                },
            ))

        await callback.message.edit_text(
            f"🗑 Пользователь <b>{name}</b> удалён.",
            reply_markup=back_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hard_delete_execute:"))
async def admin_hard_delete_execute(callback: CallbackQuery) -> None:
    """Physically remove the user from DB."""
    if not await _require_role(callback, UserRole.ADMIN):
        return
    if not callback.data:
        await callback.answer()
        return
    user_id = int(callback.data.split(":")[1])

    async for session in get_session():
        repo = UserRepository(session)
        audit_repo = AuditLogRepository(session)

        user = await repo.get_by_id(user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        name = user.full_name
        tg_id = user.telegram_id
        await repo.hard_delete(user_id)

        admin = await repo.get_by_telegram_id(callback.from_user.id)
        if admin:
            await audit_repo.create(AuditLog(
                user_id=int(admin.id) if admin.id is not None else 0,
                action="hard_delete_user",
                entity_type="user",
                entity_id=user_id,
                details={"deleted_user": name, "telegram_id": tg_id},
            ))

        if callback.message is None:
            await callback.answer()
        else:
            await callback.message.edit_text(
                f"🧨 Пользователь <b>{name}</b> удалён навсегда.",
                reply_markup=back_keyboard(),
            )
    await callback.answer()


@router.callback_query(F.data.startswith("user_actions:"))
async def callback_user_actions(callback: CallbackQuery) -> None:
    """Show user actions keyboard."""
    if not await _require_role(callback, UserRole.ADMIN):
        return
    user_id = int(callback.data.split(":")[1])

    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        await callback.message.edit_text(
            f"👤 <b>{user.full_name}</b> — управление:",
            reply_markup=user_actions_keyboard(user_id, status=user.status.value if user.status else None),
        )
    await callback.answer()


@router.callback_query(F.data == "admin_user_search")
async def admin_user_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _require_role(callback, UserRole.ADMIN):
        return
    await state.set_state(SearchUserStates.waiting_query)
    await callback.message.edit_text(
        "🔍 <b>Поиск пользователя</b>\n\nВведите имя, username или Telegram ID:",
        reply_markup=back_keyboard("admin_users"),
    )
    await callback.answer()


@router.message(SearchUserStates.waiting_query)
async def admin_user_search_query(message: Message, state: FSMContext) -> None:
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
            lines.append(
                f"👤 <b>{escape(u.full_name)}</b> — {escape(u.role.value)}\n"
                f"   ID: {u.id} | @{escape(u.username) if u.username else '—'}\n"
            )
            buttons.append([(f"{u.full_name}", f"user_actions:{u.id}")])

        await message.answer(
            "\n".join(lines),
            reply_markup=build_kb(buttons + [[("🔙 Назад", "admin_users")]]),
        )
    await state.clear()


@router.callback_query(F.data.startswith("fine_cancel:"))
async def fine_cancel(callback: CallbackQuery) -> None:
    if not await _require_role(callback, UserRole.TREASURER):
        return
    fine_id = int(callback.data.split(":")[1])
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
        fine.cancelled_by = (await user_repo.get_by_telegram_id(callback.from_user.id)).id if await user_repo.get_by_telegram_id(callback.from_user.id) else None
        fine.cancelled_at = datetime.utcnow()
        await fine_repo.update(fine)

        await audit_repo.create(AuditLog(
            user_id=fine.cancelled_by or 0,
            action="cancel_fine",
            entity_type="fine",
            entity_id=fine.id,
            details={"user_id": fine.user_id, "fine_id": fine.id},
        ))

        await callback.message.edit_text(
            f"✅ Штраф #{fine.id} отменён.",
            reply_markup=back_keyboard(),
        )
    await callback.answer()


# ─── Админ: восстановление доступа пользователя ───────────────────
@router.callback_query(F.data.startswith("admin_restore:"))
async def admin_restore(callback: CallbackQuery) -> None:
    if not await _require_role(callback, UserRole.ADMIN):
        return
    user_id = int(callback.data.split(":")[1])

    async for session in get_session():
        repo = UserRepository(session)
        audit_repo = AuditLogRepository(session)

        user = await repo.get_by_id(user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        # Try to restore previous role from latest delete audit log
        stmt = select(AuditLogModel).where(
            AuditLogModel.entity_type == "user",
            AuditLogModel.entity_id == user.id,
            AuditLogModel.action == "delete_user",
        ).order_by(AuditLogModel.created_at.desc()).limit(1)
        res = await session.execute(stmt)
        last_log = res.scalar_one_or_none()

        restored_role = None
        if last_log and last_log.details:
            try:
                details = json.loads(last_log.details)
                restored_role = details.get("previous_role") or details.get("role")
            except Exception:
                restored_role = None

        user.status = UserStatus.ACTIVE
        try:
            user.role = UserRole(restored_role) if restored_role else UserRole.MEMBER
        except Exception:
            user.role = UserRole.MEMBER
        await repo.update(user)

        admin = await repo.get_by_telegram_id(callback.from_user.id)
        if admin:
            await audit_repo.create(AuditLog(
                user_id=admin.id,
                action="restore_user",
                entity_type="user",
                entity_id=user.id,
                details={"restored_user": user.full_name, "user_id": user.id},
            ))

        await callback.message.edit_text(
            f"✅ Пользователь <b>{user.full_name}</b> восстановлен и получил доступ.",
            reply_markup=back_keyboard(),
        )
    await callback.answer()


# ─── Админ: настройки ────────────────────────────

@router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery) -> None:
    if not await _require_role(callback, UserRole.ADMIN):
        return
    await callback.message.edit_text(
        "⚙️ <b>Настройки клуба</b>",
        reply_markup=admin_settings_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_set_fee")
async def admin_set_fee(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _require_role(callback, UserRole.ADMIN):
        return
    async for session in get_session():
        repo = ClubSettingsRepository(session)
        fee = await repo.get_monthly_fee()
        await callback.message.edit_text(
            f"💰 Текущий размер взноса: <b>{fee:,.2f}₽</b>\n\n"
            f"Введите новую сумму (только число):",
            reply_markup=back_keyboard(),
        )
    await state.set_state(SettingsStates.waiting_fee)
    await callback.answer()


@router.message(SettingsStates.waiting_fee)
async def admin_set_fee_value(message: Message, state: FSMContext) -> None:
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
    except (ValueError, Decimal.InvalidOperation):
        await message.answer("❌ Введите положительное число.")
        return

    async for session in get_session():
        repo = ClubSettingsRepository(session)
        await repo.update(monthly_fee=amount)
        await message.answer(f"✅ Размер взноса изменён: <b>{amount:,.2f}₽</b>")
    await state.clear()


@router.callback_query(F.data == "admin_set_details")
async def admin_set_details(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _require_role(callback, UserRole.ADMIN):
        return
    await callback.message.edit_text(
        "💳 Введите новые <b>реквизиты для оплаты</b>:\n"
        "(номер карты, телефон, или любые инструкции)",
        reply_markup=back_keyboard(),
    )
    await state.set_state(SettingsStates.waiting_details)
    await callback.answer()


@router.message(SettingsStates.waiting_details)
async def admin_set_details_value(message: Message, state: FSMContext) -> None:
    async for session in get_session():
        repo = ClubSettingsRepository(session)
        await repo.update(payment_details=message.text)
        await message.answer("✅ Реквизиты обновлены!")
    await state.clear()


@router.callback_query(F.data == "admin_set_name")
async def admin_set_name(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _require_role(callback, UserRole.ADMIN):
        return
    await callback.message.edit_text(
        "🏷 Введите новое <b>название клуба</b>:",
        reply_markup=back_keyboard(),
    )
    await state.set_state(SettingsStates.waiting_club_name)
    await callback.answer()


@router.message(SettingsStates.waiting_club_name)
async def admin_set_name_value(message: Message, state: FSMContext) -> None:
    async for session in get_session():
        repo = ClubSettingsRepository(session)
        await repo.update(club_name=message.text)
        await message.answer(f"✅ Название клуба: <b>{message.text}</b>")
    await state.clear()


# ─── Казначей: штрафы ────────────────────────────

@router.callback_query(F.data.startswith("fine_issue:"))
async def fine_issue_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _require_role(callback, UserRole.TREASURER):
        return
    user_id = int(callback.data.split(":")[1])
    await state.update_data(fine_user_id=user_id)
    await state.set_state(FineStates.waiting_amount)
    await callback.message.edit_text(
        "⚠️ <b>Начисление штрафа</b>\n\nВведите сумму штрафа:",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.message(FineStates.waiting_amount)
async def fine_issuer_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
        await state.update_data(fine_amount=amount)
        await state.set_state(FineStates.waiting_reason)
        await message.answer("Введите <b>причину</b> штрафа:")
    except (ValueError, Decimal.InvalidOperation):
        await message.answer("❌ Введите положительное число.")


@router.message(FineStates.waiting_reason)
async def fine_issue_reason(message: Message, state: FSMContext) -> None:
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
    if message.text == "/skip":
        await state.update_data(fine_comment=None)
    else:
        await state.update_data(fine_comment=message.text.strip())

    # Simulate callback to reuse finalize
    class FakeCallback:
        def __init__(self, msg):
            self.message = msg
            self.from_user = message.from_user
            self.bot = message.bot
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
            issued_by=issuer.id,
            status=FineStatus.ACTIVE,
        )
        created = await fine_repo.create(fine)

        await audit_repo.create(AuditLog(
            user_id=issuer.id,
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

        # Notify user
        try:
            if user:
                await callback.bot.send_message(
                    user.telegram_id,
                    f"⚠️ Вам начислен штраф!\n"
                    f"💰 Сумма: <b>{data['fine_amount']:,.2f}₽</b>\n"
                    f"📌 Причина: {data['fine_reason']}",
                )
        except Exception:
            pass

    await state.clear()


# ─── Казначей: расходы ───────────────────────────

@router.callback_query(F.data == "treasurer_expenses")
async def expense_menu(callback: CallbackQuery) -> None:
    if not await _require_role(callback, UserRole.TREASURER):
        return
    await callback.message.edit_text(
        "💸 <b>Расходы клуба</b>\n\n"
        "Выберите действие:",
        reply_markup=build_kb([
            [("➕ Добавить расход", "expense_add")],
            [("📋 История расходов", "expense_list")],
            [("🔙 Назад", "back")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "expense_add")
async def expense_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _require_role(callback, UserRole.TREASURER):
        return
    await state.set_state(ExpenseStates.waiting_amount)
    await callback.message.edit_text(
        "💸 <b>Добавление расхода</b>\n\nВведите сумму:",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.message(ExpenseStates.waiting_amount)
async def expense_add_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
        await state.update_data(expense_amount=amount)
        await state.set_state(ExpenseStates.waiting_category)
        await message.answer(
            "Выберите <b>категорию</b> расхода:",
            reply_markup=expense_categories_keyboard(),
        )
    except ValueError:
        await message.answer(
            "❌ Введите корректную сумму (числом, через точку или запятую):",
            reply_markup=back_keyboard(),
        )

@router.callback_query(ExpenseStates.waiting_category, F.data.startswith("expense_cat:"))
async def expense_add_category(callback: CallbackQuery, state: FSMContext) -> None:
    category = callback.data.split(":")[1]
    await state.update_data(expense_category=category)
    await state.set_state(ExpenseStates.waiting_comment)
    await callback.message.edit_text(
        "Введите <b>комментарий</b> к расходу (или /skip):",
        reply_markup=confirm_cancel_keyboard("expense_skip_comment", "back"),
    )
    await callback.answer()


@router.callback_query(F.data == "expense_skip_comment")
async def expense_skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(expense_comment=None)
    await _expense_finalize(callback, state)


@router.message(ExpenseStates.waiting_comment)
async def expense_add_comment(message: Message, state: FSMContext) -> None:
    if message.text == "/skip":
        await state.update_data(expense_comment=None)
    else:
        await state.update_data(expense_comment=message.text.strip())

    class FakeCallback:
        def __init__(self, msg):
            self.message = msg
            self.from_user = message.from_user
            self.bot = message.bot
        async def answer(self):
            pass

    await _expense_finalize(FakeCallback(message), state)


async def _expense_finalize(callback, state: FSMContext) -> None:
    data = await state.get_data()
    async for session in get_session():
        user_repo = UserRepository(session)
        expense_repo = ExpenseRepository(session)
        audit_repo = AuditLogRepository(session)

        creator = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not creator:
            await callback.message.answer("❌ Ошибка")
            await state.clear()
            return

        expense = Expense(
            amount=data["expense_amount"],
            category=ExpenseCategory(data.get("expense_category", "other")),
            comment=data.get("expense_comment"),
            created_by=creator.id,
            expense_date=date.today(),
        )
        created = await expense_repo.create(expense)

        await audit_repo.create(AuditLog(
            user_id=creator.id,
            action="add_expense",
            entity_type="expense",
            entity_id=created.id,
            details={"amount": str(data["expense_amount"]), "category": data.get("expense_category")},
        ))

        await callback.message.answer(
            f"✅ Расход добавлен!\n"
            f"💰 Сумма: <b>{data['expense_amount']:,.2f}₽</b>\n"
            f"📂 Категория: {data.get('expense_category', 'other')}",
        )
    await state.clear()


@router.callback_query(F.data == "expense_list")
async def expense_list(callback: CallbackQuery) -> None:
    if not await _require_role(callback, UserRole.TREASURER):
        return
    async for session in get_session():
        repo = ExpenseRepository(session)
        expenses = await repo.list_all()
        if not expenses:
            await callback.message.edit_text(
                "📭 Расходов пока нет.",
                reply_markup=back_keyboard(),
            )
        else:
            total = sum((e.amount for e in expenses), Decimal("0"))
            lines = [f"💸 <b>Расходы клуба</b> (всего: {total:,.2f}₽)\n"]
            for e in expenses[:20]:
                lines.append(
                    f"📅 {e.expense_date} | <b>{e.amount:,.2f}₽</b> | {e.category.value}\n"
                    f"   {e.comment or ''}"
                )
            await callback.message.edit_text(
                "\n".join(lines),
                reply_markup=back_keyboard(),
            )
    await callback.answer()


# ─── Участник: "Я оплатил" ──────────────────────

@router.callback_query(F.data == "member_pay")
async def member_pay_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PaymentStates.waiting_amount)
    await callback.message.edit_text(
        "📤 <b>Я оплатил</b>\n\n"
        "Введите <b>сумму</b>, которую оплатили:",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.message(PaymentStates.waiting_amount)
async def member_pay_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
        await state.update_data(pay_amount=amount)
    except (ValueError, Decimal.InvalidOperation):
        await message.answer("❌ Введите положительное число.")
        return

    await state.set_state(PaymentStates.waiting_month)
    now = datetime.utcnow()
    await message.answer(
        f"За какой <b>месяц</b> платите?\n"
        f"(например: {now.month})\n"
        f"Или год.месяц (например: {now.year}.{now.month}):",
    )


@router.message(PaymentStates.waiting_month)
async def member_pay_month(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    now = datetime.utcnow()

    if "." in text:
        parts = text.split(".")
        year = int(parts[0])
        month = int(parts[1])
    else:
        month = int(text)
        year = now.year

    if month < 1 or month > 12:
        await message.answer("❌ Месяц должен быть от 1 до 12.")
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
        await source.message.edit_text(
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
        settings_repo = ClubSettingsRepository(session)

        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.message.answer("❌ Ошибка: пользователь не найден")
            await state.clear()
            return

        # Get treasurers to notify
        treasurers = await user_repo.list_by_role(UserRole.TREASURER)
        admins = await user_repo.list_by_role(UserRole.ADMIN)

        payment = Payment(
            user_id=user.id,
            amount=data["pay_amount"],
            month=data["pay_month"],
            year=data["pay_year"],
            comment=data.get("pay_comment"),
            receipt_photo_id=data.get("pay_receipt"),
            status=PaymentStatus.PENDING,
        )
        created = await pay_repo.create(payment)

        # Notify treasurers
        notify_text = (
            f"📤 <b>Новый платёж</b>\n"
            f"👤 {user.full_name}\n"
            f"💰 Сумма: <b>{data['pay_amount']:,.2f}₽</b>\n"
            f"📅 За: {data['pay_month']:02d}/{data['pay_year']}\n"
        )
        if data.get("pay_comment"):
            notify_text += f"💬 {data['pay_comment']}\n"
        notify_text += f"\n🆔 Платёж #{created.id}"

        from src.presentation.keyboards.common import payment_action_keyboard
        for t in treasurers + admins:
            try:
                kb = payment_action_keyboard(created.id)
                msg = await callback.bot.send_message(t.telegram_id, notify_text)
                # If there's a receipt photo, send it
                if data.get("pay_receipt"):
                    try:
                        await callback.bot.send_photo(
                            t.telegram_id,
                            data["pay_receipt"],
                            caption=f"Чек к платежу #{created.id}",
                        )
                    except Exception:
                        pass
                # Edit with action buttons
                await callback.bot.edit_message_reply_markup(
                    t.telegram_id, msg.message_id,
                    reply_markup=kb,
                )
            except Exception:
                pass

        await callback.message.answer(
            f"✅ Платёж отправлен на подтверждение!\n"
            f"Ожидайте, пока казначей его подтвердит.",
        )
    await state.clear()


# ─── Админ: статистика ───────────────────────────

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery) -> None:
    if not await _require_role(callback, UserRole.ADMIN):
        return
    # Same as treasurer stats
    from src.presentation.handlers.treasurer import show_stats
    await show_stats(callback)


# ─── Админ: журнал действий ──────────────────────

@router.callback_query(F.data == "admin_log")
async def admin_log(callback: CallbackQuery) -> None:
    if not await _require_role(callback, UserRole.ADMIN):
        return
    async for session in get_session():
        from src.infrastructure.repositories.audit_repository import AuditLogRepository
        repo = AuditLogRepository(session)
        logs = await repo.list_all(limit=30)

        if not logs:
            await callback.message.edit_text("📭 Журнал действий пуст.", reply_markup=back_keyboard())
            await callback.answer()
            return

        lines = ["📋 <b>Журнал действий</b>:\n"]
        for log in logs:
            time_str = log.created_at.strftime("%d.%m %H:%M") if log.created_at else "?"
            lines.append(f"{time_str} | {log.action} | {log.entity_type}#{log.entity_id or '?'}")

        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=back_keyboard(),
        )
    await callback.answer()


# ─── Админ: экспорт ──────────────────────────────

@router.callback_query(F.data == "admin_export")
async def admin_export(callback: CallbackQuery) -> None:
    if not await _require_role(callback, UserRole.ADMIN):
        return

    async for session in get_session():
        user_repo = UserRepository(session)
        pay_repo = PaymentRepository(session)
        fine_repo = FineRepository(session)
        exp_repo = ExpenseRepository(session)
        audit_repo = AuditLogRepository(session)

        users = await user_repo.list_all()
        payments = await pay_repo.list_confirmed() + await pay_repo.list_pending()
        fines = await fine_repo.list_active()
        expenses = await exp_repo.list_all()
        logs = await audit_repo.list_all(limit=1000)

        data = {
            "users": [
                {
                    "id": u.id,
                    "telegram_id": u.telegram_id,
                    "username": u.username,
                    "full_name": u.full_name,
                    "role": u.role.value,
                    "status": u.status.value,
                    "joined_at": u.joined_at.isoformat() if u.joined_at else None,
                    "balance_credit": str(u.balance_credit),
                }
                for u in users
            ],
            "payments": [
                {
                    "id": p.id,
                    "user_id": p.user_id,
                    "amount": str(p.amount),
                    "month": p.month,
                    "year": p.year,
                    "status": p.status.value,
                    "payment_method": p.payment_method,
                    "comment": p.comment,
                    "receipt_photo_id": p.receipt_photo_id,
                    "confirmed_by": p.confirmed_by,
                    "confirmed_at": p.confirmed_at.isoformat() if p.confirmed_at else None,
                    "rejection_reason": p.rejection_reason,
                }
                for p in payments
            ],
            "fines": [
                {
                    "id": f.id,
                    "user_id": f.user_id,
                    "amount": str(f.amount),
                    "reason": f.reason,
                    "comment": f.comment,
                    "issued_by": f.issued_by,
                    "status": f.status.value,
                    "cancelled_by": f.cancelled_by,
                    "cancelled_at": f.cancelled_at.isoformat() if f.cancelled_at else None,
                }
                for f in fines
            ],
            "expenses": [
                {
                    "id": e.id,
                    "amount": str(e.amount),
                    "category": e.category.value,
                    "comment": e.comment,
                    "created_by": e.created_by,
                    "expense_date": e.expense_date.isoformat() if e.expense_date else None,
                }
                for e in expenses
            ],
            "audit_logs": [
                {
                    "id": l.id,
                    "user_id": l.user_id,
                    "action": l.action,
                    "entity_type": l.entity_type,
                    "entity_id": l.entity_id,
                    "details": l.details,
                    "created_at": l.created_at.isoformat() if l.created_at else None,
                }
                for l in logs
            ],
        }

        payload = json.dumps(data, ensure_ascii=False, indent=2)
        buffer = io.BytesIO(payload.encode("utf-8"))
        buffer.name = "treasury_export.json"
        buffer.seek(0)

        await callback.message.answer_document(
            InputFile(buffer, filename="treasury_export.json"),
            caption="📄 Экспорт данных клуба",
            reply_markup=back_keyboard(),
        )
    await callback.answer()


# ─── Казначей: штрафы (список) ───────────────────

@router.callback_query(F.data == "treasurer_fines")
async def treasurer_fines(callback: CallbackQuery) -> None:
    if not await _require_role(callback, UserRole.TREASURER):
        return
    async for session in get_session():
        repo = FineRepository(session)
        fines = await repo.list_active()
        if not fines:
            await callback.message.edit_text("✅ Активных штрафов нет.", reply_markup=back_keyboard())
            await callback.answer()
            return

        lines = ["⚠️ <b>Активные штрафы</b>:\n"]
        for f in fines[:20]:
            lines.append(f"ID#{f.id} — {f.amount:,.2f}₽ — {f.reason}")
        await callback.message.edit_text("\n".join(lines), reply_markup=back_keyboard())
    await callback.answer()
