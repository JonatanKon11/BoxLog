"""Tests de bot.py: dueño, despacho y configuración, sin red ni token real."""

import asyncio
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from telegram.error import NetworkError, TimedOut

from boxlog import bot, core, db


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    db.init_schema(connection)
    yield connection
    connection.close()


def _imports_de(path):
    """Nombres importados por un módulo, leídos con ast."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nombres = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            nombres.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            nombres.append(node.module)
    return nombres


# --- is_owner: dueño único (RF-08, CL-7) ---


def test_is_owner_id_correcto():
    assert bot.is_owner(123, 123) is True


def test_is_owner_id_ajeno():
    assert bot.is_owner(999, 123) is False


def test_is_owner_sin_usuario():
    assert bot.is_owner(None, 123) is False


# --- dispatch: decide respuesta sin conexión (RF-08, RF-12, CL-12) ---


def test_dispatch_dueño_comando_conocido_ejecuta(conn):
    texto = bot.dispatch(1, 1, "rm", ["clean", "100"], conn)
    assert texto == "RM de clean guardado: 100 kg"
    assert db.get_rm(conn, "clean") == 100  # se ejecutó de verdad


def test_dispatch_persona_ajena_no_responde(conn):
    assert bot.dispatch(999, 1, "rm", ["clean", "100"], conn) is None
    assert db.get_rm(conn, "clean") is None  # ni siquiera escribe


def test_dispatch_persona_ajena_comando_desconocido_tampoco(conn):
    # T4: solo cambia la llamada al contrato nuevo de args (texto crudo en su
    # único elemento); la aserción de silencio (RF-08) queda igual.
    assert bot.dispatch(999, 1, None, ["52x3"], conn) is None


def test_dispatch_comando_desconocido_devuelve_la_ayuda(conn):
    assert bot.dispatch(1, 1, "volado", [], conn) == core.help_text()


def test_dispatch_texto_libre_registra_o_devuelve_la_ayuda(conn):
    # T4 (RF-02 y RF-12 modificado por la 003): el texto crudo viaja en args
    # como único token; forma → serie, forma inválida → aviso, sin forma → ayuda.
    bot.dispatch(1, 1, "inicio", [], conn)
    bot.dispatch(1, 1, "log", ["clean", "84x5"], conn)
    assert bot.dispatch(1, 1, None, ["52x3"], conn) == "clean · serie 2: 52 kg × 3"
    assert bot.dispatch(1, 1, None, ["52x0"], conn) == core.usage_example("log")
    assert bot.dispatch(1, 1, None, ["mañana hago 52x3"], conn) == core.help_text()
    assert conn.execute("SELECT COUNT(*) FROM series").fetchone()[0] == 2  # nada extra


def test_dispatch_start_y_ayuda_muestran_la_ayuda(conn):
    assert bot.dispatch(1, 1, "start", [], conn) == core.help_text()
    assert bot.dispatch(1, 1, "ayuda", [], conn) == core.help_text()


def test_dispatch_comando_conocido_por_dueno_sin_sesion(conn):
    assert (
        bot.dispatch(1, 1, "log", ["clean", "84x5"], conn)
        == "No hay sesión abierta, envía /inicio"
    )


# --- T4: texto suelto y /historial cableados (RF-02, RF-03, CL-8) ---


def test_dispatch_texto_suelto_ajeno_no_guarda_nada(conn):
    # CL-8: otro ID con "52x3" → ignorado por completo, sin respuesta ni guardado
    bot.dispatch(1, 1, "inicio", [], conn)
    bot.dispatch(1, 1, "log", ["clean", "84x5"], conn)
    antes = conn.execute("SELECT COUNT(*) FROM series").fetchone()[0]
    assert bot.dispatch(999, 1, None, ["52x3"], conn) is None
    assert conn.execute("SELECT COUNT(*) FROM series").fetchone()[0] == antes


def test_dispatch_historial_cableado_responde(conn):
    # /historial cableado en COMMANDS (RF-03): responde igual que cmd_historial
    assert bot.dispatch(1, 1, "historial", [], conn) == core.HISTORIAL_EMPTY
    bot.dispatch(1, 1, "inicio", [], conn)
    texto = bot.dispatch(1, 1, "historial", [], conn)
    assert "abierta desde las" in texto


# --- load_settings: .env con nombre claro, sin mostrar el token (RNF-2) ---


@pytest.fixture
def sin_dotenv(monkeypatch):
    """Aísla de un .env real del repo: load_dotenv sube desde boxlog/bot.py,
    por lo que cambiar de directorio de trabajo no basta."""
    monkeypatch.setattr(bot, "load_dotenv", lambda: None)


def test_load_settings_ok(tmp_path, monkeypatch, sin_dotenv):
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("OWNER_ID", "42")
    settings = bot.load_settings()
    assert settings.token == "123:abc"
    assert settings.owner_id == 42


def test_load_settings_falta_token_error_claro(tmp_path, monkeypatch, sin_dotenv):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.setenv("OWNER_ID", "42")
    with pytest.raises(SystemExit) as excinfo:
        bot.load_settings()
    assert "TELEGRAM_TOKEN" in str(excinfo.value)


def test_load_settings_falta_owner_id_error_sin_token(tmp_path, monkeypatch, sin_dotenv):
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:SECRETO123")
    monkeypatch.delenv("OWNER_ID", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        bot.load_settings()
    mensaje = str(excinfo.value)
    assert "OWNER_ID" in mensaje
    assert "SECRETO123" not in mensaje  # nunca imprime el token


def test_load_settings_owner_id_no_numerico(tmp_path, monkeypatch, sin_dotenv):
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("OWNER_ID", "no-numero")
    with pytest.raises(SystemExit) as excinfo:
        bot.load_settings()
    assert "OWNER_ID" in str(excinfo.value)


# --- errores de conexión: qué se loguea (T11, ajuste) ---


def _value_error_con_tb():
    try:
        raise ValueError("algo falló por dentro")
    except ValueError as error:
        return error


def test_error_red_loguea_una_linea_sin_traceback():
    texto = bot.format_error_log(NetworkError("connection refused"))
    assert texto == "Sin conexión con Telegram, reintentando..."
    assert "\n" not in texto
    assert "Traceback" not in texto


def test_timeout_loguea_una_linea_sin_traceback():
    texto = bot.format_error_log(TimedOut("timed out"))
    assert texto == "Sin conexión con Telegram, reintentando..."
    assert "\n" not in texto
    assert "Traceback" not in texto


def test_otro_error_loguea_completo_con_traceback():
    texto = bot.format_error_log(_value_error_con_tb())
    assert "ValueError: algo falló por dentro" in texto
    assert "Traceback" in texto


def test_el_token_nunca_aparece_en_el_log():
    token = "999999:AAAA-token-secreto"
    completo = bot.format_error_log(ValueError(f"401 Unauthorized, token {token}"), token)
    assert token not in completo
    assert "***" in completo  # redactado
    corto = bot.format_error_log(NetworkError(f"falla con {token}"), token)
    assert token not in corto
    assert corto == "Sin conexión con Telegram, reintentando..."


# --- T4: aviso de error interno en el chat (RF-04, CL-13, RNF-2, RNF-5) ---


@pytest.mark.parametrize("error", [NetworkError("connection refused"), TimedOut("timed out")])
def test_error_notice_de_red_no_avisa_en_el_chat(error):
    # NetworkError/TimedOut → solo log, como hasta ahora (RF-04)
    assert bot.error_notice(error) is None


def test_error_notice_error_interno_aviso_generico_fijo():
    texto = bot.error_notice(ValueError("detalle interno con el token 999:SECRETO"))
    # texto fijo exacto del RF-04, sin el detalle del error ni el token
    assert texto == "⚠️ Algo salió mal; no se ha perdido nada. Inténtalo de nuevo."
    assert texto == core.INTERNAL_ERROR_TEXT
    assert "detalle" not in texto and "SECRETO" not in texto


class _MensajeFalso:
    """Mensaje falso: acumula las respuestas; opcionalmente reply_text falla."""

    def __init__(self, text=None, falla=False):
        self.text = text
        self.enviados = []
        self._falla = falla

    async def reply_text(self, texto):
        if self._falla:
            raise NetworkError("red caída al avisar")
        self.enviados.append(texto)


def _update_falso(user_id, message):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=message,
        message=message,
    )


def _contexto_falso(error):
    return SimpleNamespace(error=error)


def test_on_error_error_interno_avisa_con_texto_generico(caplog):
    token = "999:SECRETO"
    mensaje = _MensajeFalso()
    handler = bot.make_on_error(token, owner_id=1)
    error = ValueError(f"interno con el token {token}")
    asyncio.run(handler(_update_falso(1, mensaje), _contexto_falso(error)))
    # en el chat: solo el texto genérico (CL-13); nunca el detalle ni el token
    assert mensaje.enviados == [core.INTERNAL_ERROR_TEXT]
    assert "interno" not in mensaje.enviados[0]
    assert token not in mensaje.enviados[0]
    # en el log: el detalle completo con el token redactado (RNF-2)
    assert "ValueError" in caplog.text
    assert token not in caplog.text and "***" in caplog.text


def test_on_error_de_red_no_avisa_y_solo_loguea(caplog):
    mensaje = _MensajeFalso()
    handler = bot.make_on_error("999:SECRETO", owner_id=1)
    asyncio.run(handler(_update_falso(1, mensaje), _contexto_falso(NetworkError("caída"))))
    assert mensaje.enviados == []  # sin aviso en el chat (RF-04)
    assert "Sin conexión con Telegram" in caplog.text  # pero siempre en el log


def test_on_error_update_sin_mensaje_no_rompe(caplog):
    handler = bot.make_on_error("999:SECRETO", owner_id=1)
    asyncio.run(handler(None, _contexto_falso(ValueError("sin update"))))
    asyncio.run(handler(SimpleNamespace(), _contexto_falso(ValueError("sin atributos"))))
    assert caplog.text.count("ValueError") >= 2  # el log siempre recibe el detalle


def test_on_error_si_el_aviso_falla_solo_loguea(caplog):
    token = "999:SECRETO"
    mensaje = _MensajeFalso(falla=True)
    handler = bot.make_on_error(token, owner_id=1)
    asyncio.run(handler(_update_falso(1, mensaje), _contexto_falso(ValueError("origen"))))
    assert mensaje.enviados == []  # el aviso no se pudo enviar...
    assert "ValueError" in caplog.text  # ...pero el detalle del origen quedó en el log


def test_on_error_ajeno_no_recibe_el_aviso(caplog):
    # RNF-5: el aviso solo puede llegar al dueño (RF-08)
    mensaje = _MensajeFalso()
    handler = bot.make_on_error("999:SECRETO", owner_id=1)
    asyncio.run(handler(_update_falso(999, mensaje), _contexto_falso(ValueError("interno"))))
    assert mensaje.enviados == []
    assert "ValueError" in caplog.text


# --- T4: menú publicado al arrancar (RF-01, RNF-2, riesgo R5) ---


class _BotFalso:
    """Bot falso: guarda los comandos publicados o lanza si se pide (sin red)."""

    def __init__(self, falla=False):
        self.comandos = None
        self._falla = falla

    async def set_my_commands(self, comandos):
        if self._falla:
            raise RuntimeError("fallo simulado con el token 999:SECRETO")
        self.comandos = comandos


def test_publish_menu_publica_el_menu_completo():
    bot_falso = _BotFalso()
    asyncio.run(bot.publish_menu(SimpleNamespace(bot=bot_falso)))
    assert bot_falso.comandos == core.COMMAND_MENU  # la constante única (RF-01)
    assert ("historial", "Últimas sesiones") in bot_falso.comandos


def test_publish_menu_si_falla_no_propaga_y_se_loguea_el_tipo(caplog):
    app = SimpleNamespace(bot=_BotFalso(falla=True))
    asyncio.run(bot.publish_menu(app))  # no lanza: el bot arrancaría igual (R5)
    assert "RuntimeError" in caplog.text  # el tipo de la excepción...
    assert "fallo simulado" not in caplog.text  # ...y nunca str(exc) (RNF-2)
    assert "SECRETO" not in caplog.text  # ni el token


# --- T4: handler de texto libre (RF-02) ---


def test_free_text_args_quita_espacios_y_acepta_vacio():
    assert bot.free_text_args("52x3") == ["52x3"]
    assert bot.free_text_args("  52x3  ") == ["52x3"]  # strip (plan §9)
    assert bot.free_text_args(None) is None  # foto, sticker…: se ignora
    assert bot.free_text_args("") is None


def test_handler_texto_libre_registra_y_responde(conn):
    bot.dispatch(1, 1, "inicio", [], conn)
    bot.dispatch(1, 1, "log", ["clean", "84x5"], conn)
    mensaje = _MensajeFalso(text="52x3")
    handler = bot.make_free_text_handler(1, conn)
    asyncio.run(handler(_update_falso(1, mensaje), None))
    assert mensaje.enviados == ["clean · serie 2: 52 kg × 3"]


def test_handler_mensaje_sin_texto_se_ignora_sin_error(conn):
    # foto o sticker (texto None): el handler no responde ni lanza excepción
    mensaje = _MensajeFalso(text=None)
    handler = bot.make_free_text_handler(1, conn)
    asyncio.run(handler(_update_falso(1, mensaje), None))
    assert mensaje.enviados == []


# --- separación de capas (constitución 3) ---


def test_core_db_commands_no_importan_telegram():
    raiz = Path(core.__file__).parent
    for nombre in ("core.py", "db.py", "commands.py"):
        imports = _imports_de(raiz / nombre)
        assert not any("telegram" in modulo.lower() for modulo in imports), nombre


def test_gitignore_cubre_env_y_data():
    raiz = Path(__file__).resolve().parent.parent
    lineas = [l.strip() for l in (raiz / ".gitignore").read_text(encoding="utf-8").splitlines()]
    assert ".env" in lineas
    assert "data/" in lineas


def test_env_example_existe_sin_token():
    raiz = Path(__file__).resolve().parent.parent
    contenido = (raiz / ".env.example").read_text(encoding="utf-8")
    assert "TELEGRAM_TOKEN=" in contenido
    assert "OWNER_ID=" in contenido
