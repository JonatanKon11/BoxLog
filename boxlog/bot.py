"""Punto de entrada del bot: conecta el servicio de mensajería con commands.

Aquí solo hay cableado: leer configuración, abrir la base, enrutar cada
mensaje a la función de commands.py y responder su texto. Toda la lógica
de entrenamiento vive en core.py, db.py y commands.py (sin mensajes).
"""

import logging
import os
import traceback
from pathlib import Path
from typing import NamedTuple

from dotenv import load_dotenv
from telegram.error import NetworkError, TimedOut

from boxlog import commands, core, db

DATA_PATH = Path("data") / "boxlog.db"
logger = logging.getLogger(__name__)

NETWORK_ERROR_TEXT = "Sin conexión con Telegram, reintentando..."


class Settings(NamedTuple):
    token: str
    owner_id: int


def is_owner(user_id, owner_id: int) -> bool:
    """True solo si el mensaje viene del dueño del bot (RF-08)."""
    return user_id is not None and user_id == owner_id


def _help(connection, args: list[str]) -> str:
    """/start y /ayuda: la ayuda general."""
    return core.help_text()


COMMANDS = {
    "start": _help,
    "ayuda": _help,
    "perfil": commands.cmd_perfil,
    "rm": commands.cmd_rm,
    "rms": commands.cmd_rms,
    "inicio": commands.cmd_inicio,
    "fin": commands.cmd_fin,
    "hoy": commands.cmd_hoy,
    "log": commands.cmd_log,
    "deshacer": commands.cmd_deshacer,
    "historial": commands.cmd_historial,
}


def dispatch(user_id, owner_id: int, command, args: list[str], connection) -> str | None:
    """Texto de respuesta a un mensaje, o None si no se contesta (RF-08, RF-12).

    Función pura de decisión: no habla con la red, por eso es testeable
    sin conexión. `command` es el nombre en minúsculas sin barra; None es
    texto libre y `args` trae el mensaje crudo como único elemento (RF-02).
    Dueño ajeno → se ignora; desconocido → ayuda (RF-12).
    """
    if not is_owner(user_id, owner_id):
        return None
    if command is None:
        return commands.cmd_free_text(connection, args)
    handler = COMMANDS.get(command)
    if handler is None:
        return core.help_text()
    return handler(connection, args)


def format_error_log(error: BaseException, token: str = "") -> str:
    """Texto a loguear para un error de un handler, decidido sin conexión (RF-08).

    NetworkError y TimedOut son fugas de red: una línea corta y sin traceback,
    porque la librería reintenta sola. Cualquier otro error va completo con su
    traceback. El token se redacta del texto en cualquier caso.
    """
    if isinstance(error, (NetworkError, TimedOut)):
        text = NETWORK_ERROR_TEXT
    else:
        text = "".join(traceback.format_exception(error)).rstrip()
    if token:
        text = text.replace(token, "***")
    return text


def error_notice(error: BaseException) -> str | None:
    """Aviso corto para el chat (RF-04): None si es de red/timeout (solo log).

    Texto fijo de core.INTERNAL_ERROR_TEXT: el chat nunca ve el detalle del
    error ni el token (RNF-2); el detalle sigue yendo al log con format_error_log.
    """
    if isinstance(error, (NetworkError, TimedOut)):
        return None
    return core.INTERNAL_ERROR_TEXT


async def publish_menu(app) -> None:
    """Publica el menú de comandos al arrancar (RF-01), sin romper el arranque.

    Si set_my_commands falla (p. ej. de red) solo se loguea el tipo de
    excepción —nunca str(exc) ni el token (RNF-2)— y el bot arranca igual (R5).
    """
    try:
        await app.bot.set_my_commands(core.COMMAND_MENU)
    except Exception as exc:
        logger.error("No se pudo publicar el menú: %s", type(exc).__name__)


def free_text_args(message_text: str | None) -> list[str] | None:
    """Argumentos de dispatch para un mensaje de texto libre (RF-02), o None.

    Devuelve el mensaje con strip() como único elemento (los espacios
    internos los decide después core.is_log_token), o None si no hay texto
    (foto, sticker u otro sin texto: se ignora sin error).
    """
    if not message_text:
        return None
    return [message_text.strip()]


def make_free_text_handler(owner_id: int, connection):
    """Handler de mensajes de texto sin comando (RF-02): solo despacha y responde."""

    async def handler(update, context) -> None:
        message = update.message
        args = free_text_args(message.text if message is not None else None)
        if args is None:
            return
        text = dispatch(update.effective_user.id, owner_id, None, args, connection)
        if text is not None:
            await message.reply_text(text)

    return handler


def make_on_error(token: str, owner_id: int):
    """Handler de errores: log siempre con detalle; aviso genérico en el chat (RF-04).

    El aviso solo llega al dueño (RNF-5) y va dentro de try/except: si el
    envío falla, solo se loguea. El chat nunca ve str(error) ni traceback.
    """

    async def on_error(update, context) -> None:
        error = context.error
        logger.error(format_error_log(error, token))  # siempre (RF-04)
        aviso = error_notice(error)
        if aviso is None:
            return
        mensaje = getattr(update, "effective_message", None) if update is not None else None
        usuario = getattr(update, "effective_user", None) if update is not None else None
        if mensaje is None or not is_owner(getattr(usuario, "id", None), owner_id):
            return
        try:
            await mensaje.reply_text(aviso)
        except Exception as exc:
            logger.error(format_error_log(exc, token))  # el aviso no puede romper nada

    return on_error


def load_settings() -> Settings:
    """Configuración desde .env (TELEGRAM_TOKEN y OWNER_ID); sin el token en los errores."""
    load_dotenv()
    token = os.getenv("TELEGRAM_TOKEN", "")
    owner_raw = os.getenv("OWNER_ID", "")
    faltan = [n for n, v in (("TELEGRAM_TOKEN", token), ("OWNER_ID", owner_raw)) if not v]
    if faltan:
        raise SystemExit(f"Falta en .env: {', '.join(faltan)} (copia .env.example)")
    try:
        owner_id = int(owner_raw)
    except ValueError:
        raise SystemExit("OWNER_ID en .env debe ser un número de Telegram") from None
    return Settings(token.strip(), owner_id)


def main() -> None:
    """Arranca el bot: configuración, base y escucha de mensajes (RNF-1)."""
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

    settings = load_settings()
    connection = db.connect(DATA_PATH)
    db.init_schema(connection)

    app = Application.builder().token(settings.token).post_init(publish_menu).build()
    owner_id = settings.owner_id

    def make_command_handler(name: str):
        async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            user_id = update.effective_user.id
            text = dispatch(user_id, owner_id, name, context.args, connection)
            if text is not None:
                await update.message.reply_text(text)

        return handler

    async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        raw = (update.message.text or "").split(maxsplit=1)[0]
        text = dispatch(
            update.effective_user.id, owner_id, raw.lstrip("/").lower(), [], connection
        )
        if text is not None:
            await update.message.reply_text(text)

    free_text = make_free_text_handler(owner_id, connection)
    on_error = make_on_error(settings.token, owner_id)

    for name in COMMANDS:
        app.add_handler(CommandHandler(name, make_command_handler(name)))
    conocidos = sorted(COMMANDS)
    app.add_handler(MessageHandler(filters.COMMAND & ~filters.Command(conocidos), unknown_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_text))
    app.add_error_handler(on_error)

    app.run_polling()


if __name__ == "__main__":
    main()
