"""Punto de entrada del bot: conecta el servicio de mensajería con commands.

Aquí solo hay cableado: leer configuración, abrir la base, enrutar cada
mensaje a la función de commands.py y responder su texto. Toda la lógica
de entrenamiento vive en core.py, db.py y commands.py (sin mensajes).
"""

import os
from pathlib import Path
from typing import NamedTuple

from dotenv import load_dotenv

from boxlog import commands, core, db

DATA_PATH = Path("data") / "boxlog.db"


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
}


def dispatch(user_id, owner_id: int, command, args: list[str], connection) -> str | None:
    """Texto de respuesta a un mensaje, o None si no se contesta (RF-08, RF-12).

    Función pura de decisión: no habla con la red, por eso es testeable
    sin conexión. `command` es el nombre en minúsculas sin barra; None es
    texto libre. Dueño ajeno → se ignora; desconocido → ayuda (CL-12).
    """
    if not is_owner(user_id, owner_id):
        return None
    handler = COMMANDS.get(command) if command else None
    if handler is None:
        return core.help_text()
    return handler(connection, args)


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

    app = Application.builder().token(settings.token).build()
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

    async def free_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = dispatch(update.effective_user.id, owner_id, None, [], connection)
        if text is not None:
            await update.message.reply_text(text)

    for name in COMMANDS:
        app.add_handler(CommandHandler(name, make_command_handler(name)))
    conocidos = sorted(COMMANDS)
    app.add_handler(MessageHandler(filters.COMMAND & ~filters.Command(conocidos), unknown_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_text))

    app.run_polling()


if __name__ == "__main__":
    main()
