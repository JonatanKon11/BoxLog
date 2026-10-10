"""Tests de commands: /perfil, /rm y /rms (RF-01, RF-02, RF-09, CL-6). BD temporal."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

import boxlog.commands as commands_module
from boxlog import commands, db


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    db.init_schema(connection)
    yield connection
    connection.close()


# --- /perfil (RF-01) ---


def test_perfil_guarda_y_confirma(conn):
    texto = commands.cmd_perfil(conn, ["78", "175"])
    assert texto == "Perfil guardado: 78 kg · 175 cm"
    assert db.get_profile(conn) == {"weight_kg": 78.0, "height_cm": 175.0}


def test_perfil_acepta_coma_decimal(conn):
    texto = commands.cmd_perfil(conn, ["78,5", "170,5"])
    assert texto == "Perfil guardado: 78,5 kg · 170,5 cm"
    assert db.get_profile(conn) == {"weight_kg": 78.5, "height_cm": 170.5}


def test_perfil_actualiza_conservando_el_historial(conn):
    commands.cmd_perfil(conn, ["78", "175"])
    commands.cmd_perfil(conn, ["79,5", "175"])
    assert db.get_profile(conn)["weight_kg"] == 79.5
    assert conn.execute("SELECT COUNT(*) FROM profile").fetchone()[0] == 2


@pytest.mark.parametrize(
    "args",
    [[], ["78"], ["78", "175", "99"], ["peso", "175"], ["78", "abc"]],
)
def test_perfil_argumentos_invalidos_aviso_unico_sin_guardar(conn, args):
    assert commands.cmd_perfil(conn, args) == "Usa /perfil 78 175"
    assert db.get_profile(conn) is None


@pytest.mark.parametrize(
    "args, motivo",
    [
        (["29", "175"], "El peso tiene que estar entre 30 y 300 kg."),
        (["301", "175"], "El peso tiene que estar entre 30 y 300 kg."),
        (["78", "99"], "La altura tiene que estar entre 100 y 250 cm."),
        (["78", "251"], "La altura tiene que estar entre 100 y 250 cm."),
    ],
)
def test_perfil_fuera_de_rango_motivo_y_ejemplo_sin_guardar(conn, args, motivo):
    assert commands.cmd_perfil(conn, args) == f"{motivo} Usa /perfil 78 175"
    assert db.get_profile(conn) is None


def test_perfil_invalido_no_modifica_el_guardado(conn):
    commands.cmd_perfil(conn, ["78", "175"])
    assert (
        commands.cmd_perfil(conn, ["999", "175"])
        == "El peso tiene que estar entre 30 y 300 kg. Usa /perfil 78 175"
    )
    assert db.get_profile(conn) == {"weight_kg": 78.0, "height_cm": 175.0}


def test_perfil_funciona_con_sesion_abierta(conn):
    session_id = db.open_session(conn)
    texto = commands.cmd_perfil(conn, ["78", "175"])
    assert texto == "Perfil guardado: 78 kg · 175 cm"
    assert db.get_open_session(conn)["id"] == session_id  # la sesión no se toca


# --- /rm (RF-02) ---


def test_rm_guarda_y_confirma_con_nombre_normalizado(conn):
    texto = commands.cmd_rm(conn, ["Clean", "100"])
    assert texto == "RM de clean guardado: 100 kg"
    assert db.get_rm(conn, "clean") == 100


def test_rm_acepta_coma_decimal(conn):
    texto = commands.cmd_rm(conn, ["front", "62,5"])
    assert texto == "RM de front guardado: 62,5 kg"
    assert db.get_rm(conn, "front") == 62.5


def test_rm_conserva_historial_y_el_ultimo_es_vigente(conn):
    commands.cmd_rm(conn, ["clean", "100"])
    commands.cmd_rm(conn, ["clean", "102"])
    assert db.get_rm(conn, "clean") == 102
    assert conn.execute("SELECT COUNT(*) FROM rm_history").fetchone()[0] == 2


@pytest.mark.parametrize(
    "args",
    [[], ["clean"], ["clean", "100", "extra"], ["clean", "abc"], ["clean", "1e3"]],
)
def test_rm_argumentos_invalidos_aviso_unico_sin_guardar(conn, args):
    assert commands.cmd_rm(conn, args) == "Usa /rm clean 100"
    assert db.get_rm(conn, "clean") is None


@pytest.mark.parametrize("args", [["clean", "0"], ["clean", "-5"], ["clean", "501"]])
def test_rm_fuera_de_rango_motivo_y_ejemplo_sin_guardar(conn, args):
    assert (
        commands.cmd_rm(conn, args)
        == "El RM tiene que estar entre 1 y 500 kg. Usa /rm clean 100"
    )
    assert db.get_rm(conn, "clean") is None


def test_rm_sin_ejercicio_aviso_de_uso(conn):
    assert commands.cmd_rm(conn, ["", "100"]) == "Usa /rm clean 100"


def test_rm_reemplaza_menciona_el_valor_anterior(conn):
    commands.cmd_rm(conn, ["clean", "120"])
    texto = commands.cmd_rm(conn, ["clean", "125"])
    assert texto == "RM de clean guardado: 125 kg (antes 120 kg)"
    assert db.get_rm(conn, "clean") == 125


def test_rm_funciona_con_sesion_abierta(conn):
    db.open_session(conn)
    assert commands.cmd_rm(conn, ["clean", "100"]) == "RM de clean guardado: 100 kg"


# --- /rms (RF-02) ---


def test_rms_vacio_sugiere_rm(conn):
    assert commands.cmd_rms(conn, []) == "Usa /rm clean 100"


def test_rms_lista_los_vigentes(conn):
    commands.cmd_rm(conn, ["Clean", "100"])
    commands.cmd_rm(conn, ["front", "60"])
    commands.cmd_rm(conn, ["clean", "102"])
    assert commands.cmd_rms(conn, []) == "RM vigentes:\nclean: 102 kg\nfront: 60 kg"


def test_rms_con_argumentos_aviso(conn):
    db.open_session(conn)
    assert commands.cmd_rms(conn, ["clean"]) == "Usa /rms (sin nada más)"


# --- /inicio (RF-03, CL-1) ---


def _fijar_inicio(conn, session_id, moment):
    conn.execute(
        "UPDATE sessions SET started_at = ? WHERE id = ?",
        (moment.isoformat(timespec="seconds"), session_id),
    )
    conn.commit()


def test_inicio_abre_sesion_con_hora_legible(conn):
    texto = commands.cmd_inicio(conn, [])
    abierta = db.get_open_session(conn)
    assert abierta is not None
    hora = abierta["started_at"][11:16]  # HH:MM de la marca ISO interna
    assert texto == f"Sesión iniciada a las {hora}"


def test_inicio_con_sesion_abierta_hoy_aviso_sin_cambiar_nada(conn):
    session_id = db.open_session(conn)
    hoy_2035 = datetime.now().replace(hour=20, minute=35, second=0, microsecond=0)
    _fijar_inicio(conn, session_id, hoy_2035)
    texto = commands.cmd_inicio(conn, [])
    abierta = db.get_open_session(conn)
    assert abierta["id"] == session_id  # la misma sesión
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
    assert texto == "Sesión abierta desde las 20:35. Ciérrala con /fin"


def test_inicio_con_sesion_abierta_otro_dia_menciona_la_fecha(conn):
    session_id = db.open_session(conn)
    otro_dia = datetime.now().replace(
        hour=20, minute=35, second=0, microsecond=0
    ) - timedelta(days=2)
    _fijar_inicio(conn, session_id, otro_dia)
    texto = commands.cmd_inicio(conn, [])
    assert (
        texto
        == f"Sesión abierta desde el {otro_dia:%d/%m} a las 20:35. Ciérrala con /fin"
    )


def test_inicio_con_argumentos_aviso_de_uso(conn):
    assert commands.cmd_inicio(conn, ["x"]) == "Usa /inicio (sin nada más)"
    assert db.get_open_session(conn) is None  # no abre nada


def test_inicio_tras_cerrar_abre_una_nueva(conn):
    primera = db.open_session(conn)
    db.close_session(conn, primera)
    texto = commands.cmd_inicio(conn, [])
    segunda = db.get_open_session(conn)
    assert segunda["id"] != primera
    hora = segunda["started_at"][11:16]
    assert texto == f"Sesión iniciada a las {hora}"


# --- /fin (RF-04, CL-2, CL-5) ---


def _abrir_hace(conn, session_id, minutes):
    hace = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE sessions SET started_at = ? WHERE id = ?", (hace, session_id)
    )
    conn.commit()


def test_fin_sin_sesion_abierta_aviso(conn):
    assert commands.cmd_fin(conn, []) == "No hay sesión abierta, envía /inicio"


def test_fin_con_argumentos_aviso_de_uso_sin_cerrar(conn):
    db.open_session(conn)
    assert commands.cmd_fin(conn, ["x"]) == "Usa /fin (sin nada más)"
    assert db.get_open_session(conn) is not None  # no cierra


def test_fin_sesion_vacia_una_sola_linea(conn):
    commands.cmd_inicio(conn, [])
    texto = commands.cmd_fin(conn, [])
    assert texto == "Sesión cerrada sin series."
    assert db.get_open_session(conn) is None  # la sesión queda cerrada


def test_fin_dos_veces_la_segunda_avisa(conn):
    commands.cmd_inicio(conn, [])
    commands.cmd_fin(conn, [])
    assert commands.cmd_fin(conn, []) == "No hay sesión abierta, envía /inicio"


def test_fin_resumen_duracion_y_volumen_real(conn):
    session_id = db.open_session(conn)
    _abrir_hace(conn, session_id, minutes=45)
    db.insert_series(conn, session_id, "clean", 84, 5, 84, None)
    db.insert_series(conn, session_id, "clean", 82, 5, 84, None)
    texto = commands.cmd_fin(conn, [])
    assert "Duración: 45 min" in texto
    assert "clean: 2 series · 10 repeticiones · volumen 830 kg · máx 84 kg" in texto
    assert "plan→real: 84→84, 84→82" in texto
    assert texto.splitlines()[-1] == "Volumen total: 830 kg"
    assert db.get_open_session(conn) is None


def test_fin_resumen_mas_de_una_hora(conn):
    session_id = db.open_session(conn)
    _abrir_hace(conn, session_id, minutes=83)
    db.insert_series(conn, session_id, "front", 40, 3, None, None)
    texto = commands.cmd_fin(conn, [])
    assert "Duración: 1 h 23 min" in texto
    assert "front: 1 serie · 3 repeticiones · volumen 120 kg · máx 40 kg" in texto
    assert "plan→real" not in texto  # sin series planificadas


# --- separación de capas (constitución 3) ---


def test_commands_no_importa_telegram():
    fuente = Path(commands_module.__file__).read_text(encoding="utf-8").lower()
    assert "telegram" not in fuente
