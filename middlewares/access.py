"""Middleware globale per il controllo degli accessi."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, Update, User

# Messaggio mostrato agli utenti non autorizzati.
ACCESS_DENIED_TEXT = (
    "⛔ <b>Accesso negato</b>\n\n"
    "Questo bot è privato e può essere usato solo da utenti autorizzati. "
    "Il tuo ID non è presente nella lista degli utenti consentiti."
)


class AccessControlMiddleware(BaseMiddleware):
    """Blocca qualsiasi evento proveniente da un utente non autorizzato.

    Il controllo avviene nell'*outer scope* (prima dei filtri e dei gestori),
    quindi nessun handler viene mai eseguito per utenti non ammessi.
    """

    def __init__(self, allowed_user_ids: frozenset[int]) -> None:
        super().__init__()
        self.allowed_user_ids = allowed_user_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            # Non è un update Telegram vero e proprio: lascia passare.
            return await handler(event, data)

        user = self._extract_user(event)

        if user is not None and user.id not in self.allowed_user_ids:
            await self._reject(event, data)
            # Non viene chiamato handler(): l'evento viene scartato qui.
            return None

        return await handler(event, data)

    @staticmethod
    def _extract_user(update: Update) -> User | None:
        """Estrae l'utente mittente da qualsiasi tipo di update."""
        candidates = (
            update.message,
            update.edited_message,
            update.channel_post,
            update.edited_channel_post,
            update.inline_query,
            update.chosen_inline_result,
            update.callback_query,
            update.shipping_query,
            update.pre_checkout_query,
            update.poll,
            update.poll_answer,
            update.my_chat_member,
            update.chat_member,
            update.chat_join_request,
        )
        for obj in candidates:
            if obj is None:
                continue
            if (user := getattr(obj, "from_user", None)) is not None:
                return user
            if (user := getattr(obj, "user", None)) is not None:
                return user
        return None

    @staticmethod
    async def _reject(update: Update, data: dict[str, Any]) -> None:
        """Invia un errore formattato, senza eseguire alcun comando."""
        bot: Bot = data["bot"]
        chat_id: int | None = None

        if update.message is not None:
            chat_id = update.message.chat.id
        elif update.edited_message is not None:
            chat_id = update.edited_message.chat.id
        elif (
            update.callback_query is not None
            and update.callback_query.message is not None
        ):
            chat_id = update.callback_query.message.chat.id
            try:
                await update.callback_query.answer("Accesso negato.", show_alert=True)
            except Exception:
                # La callback può essere scaduta: non è critico.
                pass

        if chat_id is not None:
            try:
                await bot.send_message(chat_id, ACCESS_DENIED_TEXT)
            except Exception:
                # L'utente potrebbe aver bloccato il bot: ignora.
                pass
