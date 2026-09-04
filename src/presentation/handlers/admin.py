from __future__ import annotations

import io
import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import select

from src.domain.entities.audit_log import AuditLog
from src.domain.entities.expense import Expense
from src.domain.entities.user import User
from src.domain.entities.whitelist import WhitelistEntry
from src.domain.value_objects.expense_category import ExpenseCategory
from src.domain.value_objects.role import UserRole
from src.domain.value_objects.user_status import UserStatus
from src.infrastructure.database.models.audit_log import AuditLogModel
from src.infrastructure.database.session import get_session
from src.infrastructure.repositories.audit_repository import AuditLogRepository
from src.infrastructure.repositories.expense_repository import ExpenseRepository
from src.infrastructure.repositories.fine_repository import FineRepository
from src.infrastructure.repositories.payment_repository import PaymentRepository
from src.infrastructure.repositories.settings_repository import ClubSettingsRepository
from src.infrastructure.repositories.user_repository import UserRepository
from src.infrastructure.repositories.whitelist_repository import WhitelistRepository
from src.infrastructure.timezone import now_msk
from src.presentation.export_pdf import generate_export_pdf
from src.presentation.keyboards.common import (
    admin_invites_keyboard,
    admin_settings_keyboard,
    admin_users_list_keyboard,

    back_keyboard,
    build_kb,
    cancel_keyboard,
    confirm_cancel_keyboard,
    expense_categories_keyboard,
    expense_edit_keyboard,
    main_menu_keyboard,
    user_actions_keyboard,
)
from src.presentation.states import (
    AddUserStates,
    BroadcastStates,
    ExpenseEditStates,
    ExpenseStates,
    RenameUserStates,
    SettingsStates,
    TreasuryAdjustStates,
)
from src.presentation.utils import FakeCallback, require_role, safe_edit

router = Router()
logger = logging.getLogger(__name__)



# ─── Админ: казна (доступ к функциям казначея) ────

@router.callback_query(F.data == "admin_treasury")
async def admin_treasury(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    await safe_edit(
        callback,
        "💰 <b>Казна клуба</b>\nВыберите действие:",
        reply_markup=main_menu_keyboard(UserRole.TREASURER),
    )
    await callback.answer()
@router.callback_query(F.data == "admin_user_add")
async def admin_user_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    await state.set_state(AddUserStates.waiting_telegram_id)
    await safe_edit(
        callback,
        "➕ <b>Добавление участника</b>\n\n"
        "Введите <b>@username</b> (например, <code>@wheresyourego</code>) или <b>Telegram ID</b> (число):\n\n"
        "💡 <i>Если пользователь ещё не писал боту, он будет добавлен в список приглашений (Whitelist). При первом запуске бота доступ откроется автоматически.</i>",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.message(AddUserStates.waiting_telegram_id)
async def admin_user_add_tgid(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    text = message.text.strip()

    # Если введён @username или строковый никнейм
    if text.startswith("@") or not text.isdigit():
        clean_username = text.lstrip("@").strip().lower()
        if not clean_username:
            await message.answer("❌ Введите корректный @username или числовой Telegram ID.")
            return

        # 1. Проверяем: нет ли уже такого активного пользователя в базе
        async for session in get_session():
            u_repo = UserRepository(session)
            found_users = await u_repo.search(clean_username)
            matching_user = next(
                (u for u in found_users if (u.username or "").lower() == clean_username and u.status == UserStatus.ACTIVE),
                None,
            )
            if matching_user:
                await message.answer(
                    f"⚠️ Пользователь <b>@{clean_username}</b> уже зарегистрирован в клубе!\n\n"
                    f"👤 Имя: <b>{matching_user.full_name}</b>\n"
                    f"📌 Роль: <b>{matching_user.role.value}</b>\n\n"
                    f"Вы можете изменить его роль или статус в меню «Все участники»."
                )
                return

            # Проверяем, нет ли уже активного приглашения в вайтлисте
            wl_repo = WhitelistRepository(session)
            existing_wl = await wl_repo.get_by_username(clean_username)
            if existing_wl and not existing_wl.is_used:
                await message.answer(
                    f"⚠️ Пользователь <b>@{clean_username}</b> уже находится в списке приглашений!\n"
                    f"Роль: <b>{existing_wl.role.value}</b>, Имя: <b>{existing_wl.full_name}</b>.\n"
                    f"Бот ожидает, пока пользователь отправит команду /start."
                )
                return

        # 2. Пытаемся получить chat через Telegram API (если он уже писал боту или есть в общем чате)
        resolved_tg_id = None
        resolved_name = None
        resolved_username = clean_username
        try:
            chat = await message.bot.get_chat(f"@{clean_username}")  # type: ignore[union-attr]
            resolved_tg_id = chat.id
            resolved_name = chat.full_name or chat.first_name
            resolved_username = chat.username or clean_username
        except Exception:
            pass

        if resolved_tg_id:
            await state.update_data(
                telegram_id=resolved_tg_id,
                resolved_name=resolved_name,
                resolved_username=resolved_username,
                is_whitelist=False,
            )
            await state.set_state(AddUserStates.waiting_full_name)
            await message.answer(
                f"✅ Найден в Telegram: <b>{resolved_name}</b> (ID: <code>{resolved_tg_id}</code>)\n\n"
                f"Введите <b>имя</b> участника (или отправьте /skip, чтобы оставить «{resolved_name}»):"
            )
            return
        else:
            # Пользователь ещё не писал боту — сохраняем в Whitelist
            await state.update_data(
                username=clean_username,
                resolved_name=clean_username,
                is_whitelist=True,
            )
            await state.set_state(AddUserStates.waiting_full_name)
            await message.answer(
                f"ℹ️ Пользователь <b>@{clean_username}</b> ещё не запускал бота.\n"
                f"Он будет добавлен в <b>список приглашений (Whitelist)</b>.\n\n"
                f"Введите <b>имя</b> участника (или отправьте /skip, чтобы оставить «@{clean_username}»):"
            )
            return

    # Числовой ID
    try:
        tg_id = int(text)
        await state.update_data(telegram_id=tg_id, is_whitelist=False)
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
        wl_repo = WhitelistRepository(session)
        ar = AuditLogRepository(session)

        admin = await repo.get_by_telegram_id(callback.from_user.id)
        admin_id = int(admin.id) if admin and admin.id is not None else 0

        # Сценарий Whitelist (предрегистрация по никнейму)
        if data.get("is_whitelist"):
            username = data["username"]
            full_name = data["full_name"]
            entry = WhitelistEntry(
                id=None,
                username=username,
                full_name=full_name,
                role=role,
                created_by=callback.from_user.id,
                created_at=now_msk(),
                is_used=False,
            )
            await wl_repo.create(entry)

            await ar.create(AuditLog(
                user_id=admin_id,
                action="whitelist_user",
                entity_type="whitelist",
                details={"username": username, "full_name": full_name, "role": role.value},
            ))
            await session.commit()

            await safe_edit(
                callback,
                f"✅ <b>Приглашение создано!</b>\n\n"
                f"👤 Имя: <b>{escape(full_name)}</b>\n"
                f"🔖 Никнейм: <b>@{escape(username)}</b>\n"
                f"👑 Роль: <b>{role.value}</b>\n\n"
                f"Пользователь добавлен в список приглашённых клуба. Как только он перейдёт в бота и нажмёт /start, бот автоматически предоставит ему доступ.",
                reply_markup=back_keyboard("admin_users"),
            )
            await state.clear()
            break


        # Сценарий добавления по известному Telegram ID
        existing = await repo.get_by_telegram_id(data["telegram_id"])
        if existing:
            await safe_edit(
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

        await ar.create(AuditLog(
            user_id=admin_id,
            action="add_user",
            entity_type="user",
            entity_id=int(created.id) if created.id is not None else 0,
            details={"telegram_id": data["telegram_id"], "role": role_str},
        ))
        await session.commit()


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
        await safe_edit(
            callback,
            f"✅ Пользователь <b>{escape(created.full_name)}</b> добавлен!\n"
            f"Роль: {role_str}\n"
            f"Telegram: {profile_line}\n\n"
            f"👥 <b>Список участников</b> (выделен новый пользователь):",
            reply_markup=admin_users_list_keyboard(users_list, highlight_id=int(created.id) if created.id is not None else None),
        )
        await state.clear()
        break

    await callback.answer()


@router.callback_query(F.data == "admin_invites_list")
async def admin_invites_list(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    async for session in get_session():
        wl_repo = WhitelistRepository(session)
        invites = await wl_repo.list_pending()
        if not invites:
            await safe_edit(
                callback,
                "⏳ <b>Список приглашений (Whitelist)</b>\n\n"
                "Сейчас нет активных непринятых приглашений.\n"
                "Все приглашённые участники уже запустили бота или список пуст.",
                reply_markup=back_keyboard("admin_users"),
            )
            break

        text = f"⏳ <b>Ожидают первого входа ({len(invites)})</b>:\n\n"
        items = []
        for inv in invites:
            text += f"• <b>@{escape(inv.username)}</b> — {escape(inv.full_name)} ({inv.role.value})\n"
            items.append((int(inv.id) if inv.id is not None else 0, inv.username, inv.full_name, inv.role.value))

        text += "\nНажмите «🗑 Отменить», чтобы отозвать приглашение."
        await safe_edit(
            callback,
            text,
            reply_markup=admin_invites_keyboard(items),
        )
        break
    await callback.answer()


@router.callback_query(F.data.startswith("admin_invite_delete:"))
async def admin_invite_delete(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    if not callback.data:
        await callback.answer()
        return
    invite_id = int(callback.data.split(":")[1])
    async for session in get_session():
        wl_repo = WhitelistRepository(session)
        await wl_repo.delete(invite_id)
        ar = AuditLogRepository(session)
        await ar.create(AuditLog(
            user_id=callback.from_user.id,
            action="delete_invite",
            entity_type="whitelist",
            entity_id=invite_id,
        ))
        await session.commit()
        await callback.answer("Приглашение отозвано", show_alert=False)
        break

    await admin_invites_list(callback)



@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    await _show_admin_user_page(callback, 0)


@router.callback_query(F.data == "admin_user_list")
async def admin_user_list(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    await _show_admin_user_page(callback, 0)


@router.callback_query(F.data.startswith("admin_users_page:"))
async def admin_users_page(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    if not callback.data:
        await callback.answer()
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
        await safe_edit(
            callback,
            text,
            reply_markup=admin_users_list_keyboard(users_list, page),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_role_"))
async def admin_change_role(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
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
            await safe_edit(
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
                entity_id=int(user.id) if user.id is not None else 0,
                details={"new_role": role_str, "user_id": int(user.id) if user.id is not None else 0},
            ))

        await safe_edit(
            callback,
            f"✅ Роль обновлена: <b>{user.full_name}</b> → {role_str}",
            reply_markup=back_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_rename:"))
async def admin_rename_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Start renaming a user."""
    if not await require_role(callback, UserRole.ADMIN):
        return
    if not callback.data:
        await callback.answer()
        return
    user_id = int(callback.data.split(":")[1])
    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if not user:
            await safe_edit(callback, "❌ Пользователь не найден", reply_markup=back_keyboard())
            return
    await state.update_data(rename_user_id=user_id, rename_old_name=user.full_name)
    await state.set_state(RenameUserStates.waiting_new_name)
    await safe_edit(
        callback,
        f"✏️ <b>Смена никнейма</b>\n\n"
        f"Текущее имя: <b>{user.full_name}</b>\n\n"
        f"Введите новое имя:",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.message(RenameUserStates.waiting_new_name)
async def admin_rename_name(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    text = message.text.strip()
    if text == "/cancel":
        await state.clear()
        await message.answer("❌ Отмена")
        return
    data = await state.get_data()
    user_id = data.get("rename_user_id")
    old_name = data.get("rename_old_name", "")
    if not user_id:
        await state.clear()
        await message.answer("❌ Ошибка: сессия сброшена")
        return

    async for session in get_session():
        repo = UserRepository(session)
        audit_repo = AuditLogRepository(session)
        user = await repo.get_by_id(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден")
            await state.clear()
            return

        user.full_name = text
        await repo.update(user)

        admin = await repo.get_by_telegram_id(message.from_user.id)
        if admin:
            await audit_repo.create(AuditLog(
                user_id=int(admin.id) if admin.id is not None else 0,
                action="rename_user",
                entity_type="user",
                entity_id=user.id,
                details={"old_name": old_name, "new_name": text},
            ))

    await state.clear()
    await message.answer(f"✅ Никнейм изменён: <b>{old_name}</b> → <b>{text}</b>")


@router.callback_query(F.data.startswith("admin_archive:"))
async def admin_archive_user(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    if not callback.data:
        await callback.answer()
        return
    user_id = int(callback.data.split(":")[1])

    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if not user:
            await safe_edit(callback, "❌ Пользователь не найден", reply_markup=back_keyboard())
            break

        user.status = UserStatus.ARCHIVED
        await repo.update(user)

        await safe_edit(
            callback,
            f"📦 Пользователь <b>{user.full_name}</b> архивирован.",
            reply_markup=back_keyboard(),
        )
    await callback.answer()


# ─── Админ: удаление пользователя ───────────────────

@router.callback_query(F.data.startswith("admin_delete_confirm:"))
async def admin_delete_confirm(callback: CallbackQuery) -> None:
    """Ask for confirmation before deleting a user."""
    if not await require_role(callback, UserRole.ADMIN):
        return
    if not callback.data:
        await callback.answer()
        return
    user_id = int(callback.data.split(":")[1])

    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if not user:
            await safe_edit(callback, "❌ Пользователь не найден", reply_markup=back_keyboard())
            break

        await safe_edit(
            callback,
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
    if not await require_role(callback, UserRole.ADMIN):
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
                user_id=int(admin.id) if admin.id is not None else 0,
                action="delete_user",
                entity_type="user",
                entity_id=user_id,
                details={
                    "deleted_user": name,
                    "telegram_id": user.telegram_id,
                    "previous_role": previous_role,
                },
            ))

        await safe_edit(
            callback,
            f"🗑 Пользователь <b>{name}</b> удалён.",
            reply_markup=back_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_hard_delete_execute:"))
async def admin_hard_delete_execute(callback: CallbackQuery) -> None:
    """Physically remove the user from DB."""
    if not await require_role(callback, UserRole.ADMIN):
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

        await safe_edit(
            callback,
            f"🧨 Пользователь <b>{name}</b> удалён навсегда.",
            reply_markup=back_keyboard(),
        )


@router.callback_query(F.data.startswith("user_actions:"))
async def callback_user_actions(callback: CallbackQuery) -> None:
    """Show user actions keyboard."""
    if not await require_role(callback, UserRole.ADMIN):
        return
    if not callback.data:
        await callback.answer()
        return
    user_id = int(callback.data.split(":")[1])

    async for session in get_session():
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if not user:
            await callback.answer("❌ Пользователь не найден")
            return

        await safe_edit(
            callback,
            f"👤 <b>{user.full_name}</b> — управление:",
            reply_markup=user_actions_keyboard(user_id, status=user.status.value if user.status else None),
        )


# ─── Админ: восстановление доступа пользователя ───────────────────
@router.callback_query(F.data.startswith("admin_restore:"))
async def admin_restore(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
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

        # Try to restore previous role from latest delete audit log
        stmt = select(AuditLogModel).where(
            AuditLogModel.entity_type == "user",
            AuditLogModel.entity_id == int(user.id) if user.id is not None else 0,
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
                user_id=int(admin.id) if admin.id is not None else 0,
                action="restore_user",
                entity_type="user",
                entity_id=int(user.id) if user.id is not None else 0,
                details={"restored_user": user.full_name, "user_id": int(user.id) if user.id is not None else 0},
            ))

        await safe_edit(
            callback,
            f"✅ Пользователь <b>{user.full_name}</b> восстановлен и получил доступ.",
            reply_markup=back_keyboard(),
        )


# ─── Админ: настройки ────────────────────────────

@router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    await safe_edit(
        callback,
        "⚙️ <b>Настройки клуба</b>",
        reply_markup=admin_settings_keyboard(),
    )


# ─── Админ: корректировка баланса казны ─────────────

@router.callback_query(F.data == "admin_treasury_adjust")
async def admin_treasury_adjust(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    async for session in get_session():
        repo = ClubSettingsRepository(session)
        adjustment = await repo.get_treasury_adjustment()
        await safe_edit(
            callback,
            f"💰 <b>Корректировка баланса казны</b>\n\n"
            f"Текущая корректировка: <b>{adjustment:,.2f}₽</b>\n\n"
            f"Введите новую сумму корректировки (может быть отрицательной):\n"
            f"Примеры: <code>5000</code>, <code>-2000</code>, <code>0</code>",
            reply_markup=back_keyboard(),
        )
    await state.set_state(TreasuryAdjustStates.waiting_adjustment)


@router.message(TreasuryAdjustStates.waiting_adjustment)
async def admin_treasury_adjust_value(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    try:
        value = Decimal(message.text.strip().replace(",", "."))
    except (ValueError, InvalidOperation):
        await message.answer("❌ Введите число (например: 5000 или -2000).")
        return

    async for session in get_session():
        repo = ClubSettingsRepository(session)
        await repo.set_treasury_adjustment(value)
        # Audit log
        audit_repo = AuditLogRepository(session)
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        if user:
            await audit_repo.create(AuditLog(
                user_id=int(user.id) if user.id is not None else 0,
                action="treasury_adjustment",
                entity_type="club_settings",
                details={"adjustment": str(value)},
            ))
        await message.answer(
            f"✅ Корректировка баланса казны установлена: <b>{value:,.2f}₽</b>\n\n"
            f"Баланс в статистике: (поступления - расходы) + корректировка",
            reply_markup=back_keyboard("admin_management"),
        )
    await state.clear()


@router.callback_query(F.data == "admin_set_fee")
async def admin_set_fee(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    async for session in get_session():
        repo = ClubSettingsRepository(session)
        fee = await repo.get_monthly_fee()
        await safe_edit(
            callback,
            f"💰 Текущий размер взноса: <b>{fee:,.2f}₽</b>\n\n"
            f"Введите новую сумму (только число):",
            reply_markup=back_keyboard(),
        )
    await state.set_state(SettingsStates.waiting_fee)


@router.message(SettingsStates.waiting_fee)
async def admin_set_fee_value(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
    except (ValueError, InvalidOperation):
        await message.answer("❌ Введите положительное число.")
        return

    async for session in get_session():
        repo = ClubSettingsRepository(session)
        await repo.update(monthly_fee=amount)
        await message.answer(f"✅ Размер взноса изменён: <b>{amount:,.2f}₽</b>")
    await state.clear()


@router.callback_query(F.data == "admin_set_details")
async def admin_set_details(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    await safe_edit(
        callback,
        "💳 Введите новые <b>реквизиты для оплаты</b>:\n"
        "(номер карты, телефон, или любые инструкции)",
        reply_markup=back_keyboard(),
    )
    await state.set_state(SettingsStates.waiting_details)


@router.message(SettingsStates.waiting_details)
async def admin_set_details_value(message: Message, state: FSMContext) -> None:
    async for session in get_session():
        repo = ClubSettingsRepository(session)
        await repo.update(payment_details=message.text)
        await message.answer("✅ Реквизиты обновлены!")
    await state.clear()


@router.callback_query(F.data == "admin_set_name")
async def admin_set_name(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    await safe_edit(
        callback,
        "🏷 Введите новое <b>название клуба</b>:",
        reply_markup=back_keyboard(),
    )
    await state.set_state(SettingsStates.waiting_club_name)


@router.message(SettingsStates.waiting_club_name)
async def admin_set_name_value(message: Message, state: FSMContext) -> None:
    async for session in get_session():
        repo = ClubSettingsRepository(session)
        await repo.update(club_name=message.text)
        await message.answer(f"✅ Название клуба: <b>{message.text}</b>")
    await state.clear()


@router.callback_query(F.data == "admin_set_assessment_day")
async def admin_set_assessment_day(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    async for session in get_session():
        repo = ClubSettingsRepository(session)
        settings = await repo.get()
        current_day = settings.get("fee_assessment_day", 1)
    await safe_edit(
        callback,
        f"📅 <b>Дата начисления взносов</b>\n\n"
        f"Сейчас: <b>{current_day}</b> число каждого месяца\n\n"
        f"Введите день месяца (1-31) для автоматического начисления:",
        reply_markup=back_keyboard(),
    )
    await state.set_state(SettingsStates.waiting_assessment_day)


@router.message(SettingsStates.waiting_assessment_day)
async def admin_set_assessment_day_value(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    try:
        day = int(message.text.strip())
        if not (1 <= day <= 31):
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число от 1 до 31.")
        return
    async for session in get_session():
        repo = ClubSettingsRepository(session)
        await repo.update(fee_assessment_day=day)
    await message.answer(f"✅ Дата начисления установлена на <b>{day}-е</b> число каждого месяца.")
    await state.clear()


@router.callback_query(F.data == "admin_assess_now")
async def admin_assess_now(callback: CallbackQuery) -> None:
    """Manually trigger fee assessment for current month (works in webhook mode too)."""
    if not await require_role(callback, UserRole.ADMIN):
        return
    from datetime import datetime

    from src.domain.entities.audit_log import AuditLog
    from src.domain.entities.monthly_fee import MonthlyFee
    from src.domain.value_objects.fee_status import FeeStatus
    from src.infrastructure.repositories.audit_repository import AuditLogRepository
    from src.infrastructure.repositories.fee_repository import FeeRepository
    from src.infrastructure.repositories.settings_repository import (
        ClubSettingsRepository,
    )
    from src.infrastructure.repositories.user_repository import UserRepository
    from src.infrastructure.timezone import now_msk

    async for session in get_session():
        user_repo = UserRepository(session)
        fee_repo = FeeRepository(session)
        settings_repo = ClubSettingsRepository(session)
        audit_repo = AuditLogRepository(session)
        monthly_fee = await settings_repo.get_monthly_fee()
        members = await user_repo.list_active()
        now = now_msk()

        assessed_members = []
        for member in members:
            if not await fee_repo.get_by_user_month(member.id, now.month, now.year):
                fee = MonthlyFee(
                    user_id=int(member.id) if member.id else 0,
                    amount=monthly_fee,
                    month=now.month,
                    year=now.year,
                    status=FeeStatus.PENDING,
                )
                await fee_repo.create(fee)
                assessed_members.append(member)

        assessed = len(assessed_members)
        if assessed == 0:
            await safe_edit(
                callback,
                f"ℹ️ Взносы за {now.month:02d}/{now.year} уже начислены всем активным участникам ({len(members)}).",
                reply_markup=back_keyboard(),
            )
            return

        await settings_repo.update(last_fee_assessment=now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))

        actor = await user_repo.get_by_telegram_id(callback.from_user.id)
        if actor:
            await audit_repo.create(AuditLog(
                user_id=int(actor.id) if actor.id else 0,
                action="assess_fees",
                entity_type="monthly_fee",
                details={"count": assessed, "month": now.month, "year": now.year, "amount": str(monthly_fee)},
            ))

        # Notify only newly assessed members
        for member in assessed_members:
            try:
                await callback.bot.send_message(
                    member.telegram_id,
                    f"💰 <b>Начислен взнос</b>\n\n"
                    f"📅 За: {now.month:02d}/{now.year}\n"
                    f"💵 Сумма: <b>{monthly_fee:,.2f}₽</b>\n\n"
                    f"Оплатить можно через меню 💰 Мой бюджет → 📤 Я оплатил",
                )
            except Exception:
                logger.exception("Failed to notify %s", member.telegram_id)

        await safe_edit(callback,
            f"✅ Взносы за {now.month:02d}/{now.year} начислены: {assessed} участников.\n"
            f"💰 {monthly_fee:,.2f}₽ × {assessed} = <b>{monthly_fee * assessed:,.2f}₽</b> в месяц.",
            reply_markup=back_keyboard(),
        )
    await callback.answer()


# ─── Казначей: расходы ───────────────────────────

@router.callback_query(F.data == "treasurer_expenses")
async def expense_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not await require_role(callback, UserRole.TREASURER):
        return
    await safe_edit(
        callback,
        "💸 <b>Расходы клуба</b>\n\n"
        "Выберите действие:",
        reply_markup=build_kb([
            [("➕ Добавить расход", "expense_add")],
            [("📋 История расходов", "expense_list")],
            [("🔙 Назад", "back")],
        ]),
    )


@router.callback_query(F.data == "expense_add")
async def expense_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_role(callback, UserRole.TREASURER):
        return
    await state.set_state(ExpenseStates.waiting_amount)
    await safe_edit(
        callback,
        "💸 <b>Добавление расхода</b>\n\nВведите сумму:",
        reply_markup=back_keyboard(),
    )


@router.message(ExpenseStates.waiting_amount)
async def expense_add_amount(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
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
    await safe_edit(
        callback,
        "Введите <b>комментарий</b> к расходу (или /skip):",
        reply_markup=confirm_cancel_keyboard("expense_skip_comment", "back"),
    )


@router.callback_query(F.data == "expense_skip_comment")
async def expense_skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(expense_comment=None)
    await _expense_finalize(callback, state)


@router.message(ExpenseStates.waiting_comment)
async def expense_add_comment(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    if message.text == "/skip":
        await state.update_data(expense_comment=None)
    else:
        await state.update_data(expense_comment=message.text.strip())

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
            created_by=int(creator.id) if creator.id is not None else 0,
            expense_date=date.today(),
        )
        created = await expense_repo.create(expense)

        await audit_repo.create(AuditLog(
            user_id=int(creator.id) if creator.id is not None else 0,
            action="add_expense",
            entity_type="expense",
            entity_id=int(created.id) if created.id is not None else 0,
            details={"amount": str(data["expense_amount"]), "category": data.get("expense_category")},
        ))

        await callback.message.answer(
            f"✅ Расход добавлен!\n"
            f"💰 Сумма: <b>{data['expense_amount']:,.2f}₽</b>\n"
            f"📂 Категория: {data.get('expense_category', 'other')}",
        )
        await callback.answer()
    await state.clear()


@router.callback_query(F.data == "expense_list")
async def expense_list(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.TREASURER):
        return
    async for session in get_session():
        repo = ExpenseRepository(session)
        expenses = await repo.list_all()
        if not expenses:
            await safe_edit(
                callback,
                "📭 Расходов пока нет.",
                reply_markup=back_keyboard(),
            )
        else:
            total = sum((e.amount for e in expenses), Decimal(0))
            lines = [f"💸 <b>Расходы клуба</b> (всего: {total:,.2f}₽)\n"]
            kb_rows = []
            for e in expenses[:20]:
                lines.append(
                    f"📅 {e.expense_date} | <b>{e.amount:,.2f}₽</b> | {e.category.value}\n"
                    f"   {e.comment or ''}"
                )
                kb_rows.append([
                    (f"💸 {e.amount:,.2f}₽  {e.expense_date}  {e.category.value}", f"expense_view:{e.id}"),
                ])
            kb_rows.append([("🔙 Назад", "back")])
            await safe_edit(
                callback,
                "\n".join(lines),
                reply_markup=build_kb(kb_rows),
            )


@router.callback_query(F.data.startswith("expense_view:"))
async def expense_view(callback: CallbackQuery) -> None:
    """Show expense detail with edit/delete buttons."""
    if not await require_role(callback, UserRole.TREASURER):
        return
    expense_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        repo = ExpenseRepository(session)
        expense = await repo.get_by_id(expense_id)
        if not expense:
            await callback.answer("❌ Расход не найден", show_alert=True)
            return
        await safe_edit(
            callback,
            f"💸 <b>Расход #{expense_id}</b>\n"
            f"💰 Сумма: <code>{expense.amount:,.2f}₽</code>\n"
            f"📂 Категория: <code>{expense.category.value}</code>\n"
            f"📅 Дата: <code>{expense.expense_date}</code>\n"
            f"💬 Комментарий: <code>{expense.comment or '—'}</code>\n"
            f"👤 Создал: <code>{expense.created_by}</code>",
            reply_markup=expense_edit_keyboard(expense_id),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("expense_edit:"))
async def expense_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Start editing an expense."""
    if not await require_role(callback, UserRole.TREASURER):
        return
    expense_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        repo = ExpenseRepository(session)
        expense = await repo.get_by_id(expense_id)
        if not expense:
            await callback.answer("❌ Расход не найден", show_alert=True)
            return
        await state.update_data(
            edit_expense_id=expense_id,
            edit_expense_old={
                "amount": str(expense.amount),
                "category": expense.category.value,
                "comment": expense.comment or "",
                "expense_date": str(expense.expense_date),
                "created_by": expense.created_by,
            },
        )
        await state.set_state(ExpenseEditStates.waiting_amount)
        await safe_edit(
            callback,
            f"✏️ <b>Редактирование расхода #{expense_id}</b>\n"
            f"Сумма: <code>{expense.amount:,.2f}₽</code>\n"
            f"Категория: <code>{expense.category.value}</code>\n"
            f"Комментарий: <code>{expense.comment or '—'}</code>\n"
            f"Дата: <code>{expense.expense_date}</code>\n\n"
            f"Введите <b>новую сумму</b> (или /skip чтобы оставить текущую):",
            reply_markup=confirm_cancel_keyboard("expense_save_edit", "back"),
        )
    await callback.answer()


@router.message(ExpenseEditStates.waiting_amount)
async def expense_edit_amount(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    if message.text.strip().lower() in ("/cancel", "отмена"):
        await state.clear()
        await message.answer("❌ Отменено")
        return
    await state.get_data()
    if message.text.strip().lower() == "/skip":
        await state.set_state(ExpenseEditStates.waiting_category)
        await message.answer(
            "Выберите <b>категорию</b> или /skip:",
            reply_markup=expense_categories_keyboard(),
        )
        return
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
        await state.update_data(edit_amount=amount)
    except Exception:
        await message.answer("❌ Введите корректную сумму.")
        return
    await state.set_state(ExpenseEditStates.waiting_category)
    await message.answer(
        "Выберите <b>категорию</b> или /skip:",
        reply_markup=expense_categories_keyboard(),
    )


@router.callback_query(ExpenseEditStates.waiting_category, F.data.startswith("expense_cat:"))
async def expense_edit_category(callback: CallbackQuery, state: FSMContext) -> None:
    category = callback.data.split(":")[1]
    await state.update_data(edit_category=category)
    await state.set_state(ExpenseEditStates.waiting_comment)
    await safe_edit(
        callback,
        "Введите <b>комментарий</b> (или /skip):",
        reply_markup=confirm_cancel_keyboard("expense_save_edit", "back"),
    )


@router.message(ExpenseEditStates.waiting_category)
async def expense_edit_category_text(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    if message.text.strip().lower() in ("/cancel", "отмена"):
        await state.clear()
        await message.answer("❌ Отменено")
        return
    if message.text.strip().lower() == "/skip":
        await state.set_state(ExpenseEditStates.waiting_comment)
        await message.answer(
            "Введите <b>комментарий</b> (или /skip):",
            reply_markup=confirm_cancel_keyboard("expense_save_edit", "back"),
        )
        return
    await state.update_data(edit_category=message.text.strip())
    await state.set_state(ExpenseEditStates.waiting_comment)
    await message.answer(
        "Введите <b>комментарий</b> (или /skip):",
        reply_markup=confirm_cancel_keyboard("expense_save_edit", "back"),
    )


@router.message(ExpenseEditStates.waiting_comment)
async def expense_edit_comment(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    if message.text.strip().lower() in ("/cancel", "отмена"):
        await state.clear()
        await message.answer("❌ Отменено")
        return
    await state.get_data()
    new_comment = "" if message.text.strip().lower() == "/skip" else message.text.strip()
    await state.update_data(edit_comment=new_comment)
    await state.set_state(ExpenseEditStates.waiting_date)
    await message.answer(
        "Введите <b>дату</b> в формате ГГГГ-ММ-ДД (или /skip для текущей):",
        reply_markup=confirm_cancel_keyboard("expense_save_edit", "back"),
    )


@router.message(ExpenseEditStates.waiting_date)
async def expense_edit_date(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    if message.text.strip().lower() in ("/cancel", "отмена"):
        await state.clear()
        await message.answer("❌ Отменено")
        return
    await state.get_data()
    if message.text.strip().lower() == "/skip":
        new_date = date.today()
    else:
        try:
            new_date = date.fromisoformat(message.text.strip())
        except Exception:
            await message.answer("❌ Неверный формат даты. Используйте ГГГГ-ММ-ДД.")
            return
    await state.update_data(edit_date=new_date)
    await _save_edit_expense(message, state)


async def _save_edit_expense(source, state: FSMContext) -> None:
    data = await state.get_data()
    expense_id = data.get("edit_expense_id")
    if not expense_id:
        await source.answer("❌ Ошибка сессии")
        await state.clear()
        return

    async for session in get_session():
        repo = ExpenseRepository(session)
        user_repo = UserRepository(session)
        audit_repo = AuditLogRepository(session)

        expense = await repo.get_by_id(expense_id)
        if not expense:
            await source.answer("❌ Расход не найден", show_alert=True)
            await state.clear()
            return

        old_amount = expense.amount
        old_category = expense.category.value
        old_comment = expense.comment or ""
        old_date = expense.expense_date

        expense.amount = Decimal(data.get("edit_amount", old_amount))
        expense.category = ExpenseCategory(data.get("edit_category", old_category))
        expense.comment = data.get("edit_comment", old_comment)
        expense.expense_date = data.get("edit_date", old_date)

        await repo.update(expense)

        # Audit
        actor = await user_repo.get_by_telegram_id(source.from_user.id if hasattr(source, "from_user") and source.from_user else 0)
        if actor:
            await audit_repo.create(AuditLog(
                user_id=int(actor.id) if actor.id is not None else 0,
                action="edit_expense",
                entity_type="expense",
                entity_id=expense.id,
                details={
                    "old_amount": str(old_amount),
                    "new_amount": str(expense.amount),
                    "old_category": old_category,
                    "new_category": expense.category.value,
                    "old_comment": old_comment,
                    "new_comment": expense.comment or "",
                    "old_date": str(old_date),
                    "new_date": str(expense.expense_date),
                },
            ))

        await safe_edit(
            source,
            f"✅ Расход #{expense_id} обновлён!\n"
            f"💰 Сумма: <b>{expense.amount:,.2f}₽</b>\n"
            f"📂 Категория: <b>{expense.category.value}</b>\n"
            f"📅 Дата: <b>{expense.expense_date}</b>\n"
            f"💬 Комментарий: <b>{expense.comment or '—'}</b>",
            reply_markup=back_keyboard("expense_list"),
        )
    await state.clear()


@router.callback_query(F.data.startswith("expense_delete_confirm:"))
async def expense_delete_confirm(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.TREASURER):
        return
    expense_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        repo = ExpenseRepository(session)
        expense = await repo.get_by_id(expense_id)
        if not expense:
            await callback.answer("❌ Расход не найден", show_alert=True)
            return
        await safe_edit(
            callback,
            f"🗑 <b>Подтверждение удаления</b>\n\n"
            f"Вы уверены, что хотите удалить расход #{expense_id}?\n"
            f"💰 Сумма: <b>{expense.amount:,.2f}₽</b>\n"
            f"📂 Категория: <b>{expense.category.value}</b>\n"
            f"📅 Дата: <b>{expense.expense_date}</b>\n"
            f"💬 Комментарий: <b>{expense.comment or '—'}</b>",
            reply_markup=confirm_cancel_keyboard(f"expense_delete:{expense_id}", "back"),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("expense_delete:"))
async def expense_delete(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.TREASURER):
        return
    expense_id = int((callback.data or "").split(":")[1])
    async for session in get_session():
        repo = ExpenseRepository(session)
        user_repo = UserRepository(session)
        audit_repo = AuditLogRepository(session)

        expense = await repo.get_by_id(expense_id)
        if not expense:
            await callback.answer("❌ Расход не найден", show_alert=True)
            return

        # Store for audit
        audit_details = {
            "amount": str(expense.amount),
            "category": expense.category.value,
            "comment": expense.comment or "",
            "expense_date": str(expense.expense_date),
            "created_by": expense.created_by,
        }

        await repo.delete(expense_id)

        # Audit
        actor = await user_repo.get_by_telegram_id(callback.from_user.id)
        if actor:
            await audit_repo.create(AuditLog(
                user_id=int(actor.id) if actor.id is not None else 0,
                action="delete_expense",
                entity_type="expense",
                entity_id=expense_id,
                details=audit_details,
            ))

        await safe_edit(
            callback,
            f"✅ Расход #{expense_id} удалён.",
            reply_markup=back_keyboard("expense_list"),
        )
    await callback.answer()


# ─── Админ: статистика ───────────────────────────

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    # Same as treasurer stats
    from src.presentation.handlers.treasurer import show_stats
    await show_stats(callback)


# ─── Админ: журнал действий ──────────────────────

LOG_PER_PAGE = 10


async def _show_admin_log_page(callback: CallbackQuery, page: int) -> None:
    """Show paginated audit log page."""
    async for session in get_session():
        from src.infrastructure.repositories.audit_repository import AuditLogRepository
        repo = AuditLogRepository(session)

        logs, total = await repo.list_paginated(page=page, per_page=LOG_PER_PAGE)
        total_pages = max(1, (total + LOG_PER_PAGE - 1) // LOG_PER_PAGE)

        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1

        if not logs:
            await safe_edit(
                callback,
                "📭 Журнал действий пуст.",
                reply_markup=back_keyboard(),
            )
            return

        lines = [f"📋 <b>Журнал действий</b> (стр. {page + 1}/{total_pages}, всего: {total}):\n"]
        for log in logs:
            time_str = log.created_at.strftime("%d.%m %H:%M") if log.created_at else "?"
            lines.append(f"{time_str} | {log.action} | {log.entity_type}#{log.entity_id or '?'}")

        # Navigation buttons
        nav = []
        if page > 0:
            nav.append(("⬅️ Назад", f"admin_log_page:{page - 1}"))
        if page < total_pages - 1:
            nav.append(("Вперёд ➡️", f"admin_log_page:{page + 1}"))

        kb_rows = []
        if nav:
            kb_rows.append(nav)
        kb_rows.append([("🔙 В меню", "back")])

        await safe_edit(
            callback,
            "\r\n".join(lines).strip(),
            reply_markup=build_kb(kb_rows),
        )


@router.callback_query(F.data == "admin_log")
async def admin_log(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    await _show_admin_log_page(callback, 0)


@router.callback_query(F.data.startswith("admin_log_page:"))
async def admin_log_page(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
        return
    if not callback.data:
        await callback.answer()
        return
    page = int(callback.data.split(":")[1])
    await _show_admin_log_page(callback, page)


# ─── Админ: экспорт ──────────────────────────────

@router.callback_query(F.data == "admin_export")
async def admin_export(callback: CallbackQuery) -> None:
    if not await require_role(callback, UserRole.ADMIN):
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
                    "id": int(u.id) if u.id is not None else 0,
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
                    "id": int(p.id) if p.id is not None else 0,
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
                    "id": int(f.id) if f.id is not None else 0,
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
                    "id": int(e.id) if e.id is not None else 0,
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
                    "id": int(l.id) if l.id is not None else 0,
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

        await callback.message.send_document(
            BufferedInputFile(buffer.read(), filename="treasury_export.json"),
            caption="📄 Экспорт данных клуба (JSON)",
            reply_markup=back_keyboard(),
        )

        # Also generate CSV for spreadsheet use
        lines_csv = ["id,telegram_id,username,full_name,role,status,balance_credit"]
        for u in users:
            lines_csv.append(
                f'{u.id},{u.telegram_id},"{u.username or ""}","{u.full_name}",{u.role.value},{u.status.value},{u.balance_credit}'
            )
        lines_csv.append("")
        lines_csv.append("payments:")
        lines_csv.append("id,user_id,amount,month,year,status,comment,confirmed_at")
        for p in payments:
            lines_csv.append(
                f'{p.id},{p.user_id},{p.amount},{p.month},{p.year},{p.status.value},"{p.comment or ""}","{p.confirmed_at.isoformat() if p.confirmed_at else ""}"'
            )
        lines_csv.append("")
        lines_csv.append("fines:")
        lines_csv.append("id,user_id,amount,reason,status")
        for f in fines:
            lines_csv.append(f'{f.id},{f.user_id},{f.amount},"{f.reason}","{f.status.value}"')
        lines_csv.append("")
        lines_csv.append("expenses:")
        lines_csv.append("id,amount,category,comment,expense_date")
        for e in expenses:
            lines_csv.append(f'{e.id},{e.amount},"{e.category.value}","{e.comment or ""}",{e.expense_date.isoformat() if e.expense_date else ""}')

        csv_payload = "\r\n".join(lines_csv).encode("utf-8")
        await callback.message.send_document(
            BufferedInputFile(io.BytesIO(csv_payload).getvalue(), filename="treasury_export.csv"),
            caption="📊 Экспорт данных клуба (CSV для Excel)",
            reply_markup=back_keyboard(),
        )

        # PDF report
        try:
            pdf_buf = generate_export_pdf(users, payments, fines, expenses)
            await callback.message.answer_document(
                BufferedInputFile(pdf_buf.getvalue(), filename="treasury_export.pdf"),
                caption="📑 Экспорт данных клуба (PDF-отчёт)",
            )
        except Exception:
            logger.exception("PDF export failed, continuing without it")

    await callback.answer()
    # Return to main menu after export completes
    user = None
    async for session in get_session():
        user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
        break
    kb = main_menu_keyboard(user.role if user else UserRole.MEMBER)
    await callback.message.answer("🏠 Главное меню", reply_markup=kb)


# ─── Админ: рассылка ───────────────────────────

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    """Start broadcast FSM."""
    if not await require_role(callback, UserRole.ADMIN):
        return
    await state.set_state(BroadcastStates.waiting_text)
    await safe_edit(
        callback,
        "📣 <b>Рассылка</b>\n\n"
        "Введите текст сообщения (будет отправлено всем активным участникам):\n\n"
        "Отправьте отмену словом «отмена».",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(BroadcastStates.waiting_text)
async def admin_broadcast_message(message: Message, state: FSMContext) -> None:
    """Broadcast the message to all active users with rate limiting."""
    import asyncio

    text = message.text or message.caption or ""
    if text.strip().lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await message.answer("❌ Рассылка отменена.")
        return

    await message.answer("⏳ Рассылка началась…")

    async for session in get_session():
        user_repo = UserRepository(session)
        members = await user_repo.list_active()
        bot = message.bot

        total = len(members)
        sent = 0
        failed = 0
        failed_ids = []

        for i, member in enumerate(members, 1):
            try:
                await bot.send_message(member.telegram_id, text)
                sent += 1
            except Exception:
                failed += 1
                failed_ids.append(member.telegram_id)
                logger.exception("Broadcast failed for member %s", member.telegram_id)

            # Rate limit: 0.5s between messages to avoid Telegram flood control
            if i < total:
                await asyncio.sleep(0.5)

        await state.clear()
        summary = f"✅ Рассылка завершена.\nОтправлено: {sent}/{total}\nОшибок: {failed}"
        await message.answer(summary, parse_mode="HTML")
        if failed_ids:
            logger.warning("Broadcast: %d failures for user ids: %s", failed, failed_ids)
        kb = main_menu_keyboard(UserRole.ADMIN)
        await message.answer("🏠 Главное меню", reply_markup=kb)


