"""
Middleware авторегистрации.
Каждый апдейт от пользователя — автоматически создаёт запись в users если её нет.
"""
from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from bot.db.queries import get_or_create_user, update_username


class AutoRegisterMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Достаём пользователя из любого типа апдейта
        user = None
        if isinstance(event, Update):
            if event.message:
                user = event.message.from_user
            elif event.callback_query:
                user = event.callback_query.from_user
            elif event.inline_query:
                user = event.inline_query.from_user

        if user and not user.is_bot:
            username = user.username or user.full_name
            await get_or_create_user(user.id, username)
            await update_username(user.id, username)

        return await handler(event, data)
