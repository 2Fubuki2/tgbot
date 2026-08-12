"""Navigation middleware для отслеживания истории экранов."""

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject


class NavigationMiddleware(BaseMiddleware):
    """Middleware для отслеживания истории навигации пользователя."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """Обработка события и сохранение истории навигации."""
        if isinstance(event, CallbackQuery):
            callback_data = event.data or ""
            user_id = event.from_user.id
            state = data.get("state")

            # Получаем текущую историю навигации
            if state:
                state_data = await state.get_data()
                nav_history = state_data.get("nav_history", [])

                # Если нажата кнопка "Назад"
                if callback_data == "back":
                    if len(nav_history) > 1:
                        # Убираем текущий экран
                        nav_history.pop()
                        # Получаем предыдущий экран
                        previous_screen = nav_history[-1]
                        await state.update_data(nav_history=nav_history)
                        # Перенаправляем на предыдущий экран
                        event.data = previous_screen
                    else:
                        # Если истории нет, идем в главное меню
                        event.data = "main_menu"
                        await state.update_data(nav_history=["main_menu"])

                # Если это главное меню, очищаем историю
                elif callback_data == "main_menu":
                    await state.update_data(nav_history=["main_menu"])

                # Для остальных экранов добавляем в историю
                elif not callback_data.startswith(("back", "confirm_", "cancel_", "skip_")):
                    # Не добавляем служебные callback (подтверждения, отмены)
                    if callback_data not in nav_history[-1:]:
                        nav_history.append(callback_data)
                        # Ограничиваем историю 10 экранами
                        if len(nav_history) > 10:
                            nav_history = nav_history[-10:]
                        await state.update_data(nav_history=nav_history)

        return await handler(event, data)
