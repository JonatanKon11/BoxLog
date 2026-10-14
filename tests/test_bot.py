"""Tests de bot.py: dueño, despacho y configuración, sin red ni token real."""

import ast
from pathlib import Path

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
    assert bot.dispatch(999, 1, None, [], conn) is None


def test_dispatch_comando_desconocido_devuelve_la_ayuda(conn):
    assert bot.dispatch(1, 1, "volado", [], conn) == core.help_text()


def test_dispatch_texto_libre_devuelve_la_ayuda(conn):
    assert bot.dispatch(1, 1, None, [], conn) == core.help_text()


def test_dispatch_start_y_ayuda_muestran_la_ayuda(conn):
    assert bot.dispatch(1, 1, "start", [], conn) == core.help_text()
    assert bot.dispatch(1, 1, "ayuda", [], conn) == core.help_text()


def test_dispatch_comando_conocido_por_dueno_sin_sesion(conn):
    assert (
        bot.dispatch(1, 1, "log", ["clean", "84x5"], conn)
        == "No hay sesión abierta, envía /inicio"
    )


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
