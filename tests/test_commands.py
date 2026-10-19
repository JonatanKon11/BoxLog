"""Tests de commands: /perfil, /rm y /rms (RF-01, RF-02, RF-09, CL-6). BD temporal."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import boxlog.commands as commands_module
from boxlog import commands, core, db


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
    # La marca guardada es UTC (RF-02) y el texto muestra la hora local (RF-03).
    local = core.to_local(datetime.fromisoformat(abierta["started_at"]))
    assert texto == f"Sesión iniciada a las {local:%H:%M}"


def test_inicio_con_sesion_abierta_hoy_aviso_sin_cambiar_nada(conn):
    session_id = db.open_session(conn)
    # 20:35 hora local de hoy; la marca de la base se escribe en UTC (RF-02).
    hoy_2035 = datetime.now().replace(hour=20, minute=35, second=0, microsecond=0)
    _fijar_inicio(conn, session_id, hoy_2035 - core.LOCAL_UTC_OFFSET)
    texto = commands.cmd_inicio(conn, [])
    abierta = db.get_open_session(conn)
    assert abierta["id"] == session_id  # la misma sesión
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
    assert texto == "Sesión abierta desde las 20:35. Ciérrala con /fin"


def test_inicio_con_sesion_abierta_otro_dia_menciona_la_fecha(conn):
    session_id = db.open_session(conn)
    # 20:35 locales de hace 2 días, guardadas como UTC (RF-02).
    otro_dia = datetime.now().replace(
        hour=20, minute=35, second=0, microsecond=0
    ) - timedelta(days=2)
    _fijar_inicio(conn, session_id, otro_dia - core.LOCAL_UTC_OFFSET)
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
    # La marca de la base es UTC (RF-02) y el texto muestra la local (RF-03).
    local = core.to_local(datetime.fromisoformat(segunda["started_at"]))
    assert texto == f"Sesión iniciada a las {local:%H:%M}"


# --- /fin (RF-04, CL-2, CL-5) ---


def _abrir_hace(conn, session_id, minutes):
    # started_at es una marca UTC en la base (RF-02): la duración se resta en UTC.
    hace = (
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=minutes)
    ).isoformat(timespec="seconds")
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


# --- /hoy (RF-05, CL-2, CL-4, CL-10) ---


@pytest.mark.parametrize(
    "args", [[], ["clean"], ["clean", "-5"], ["clean", "abc"]]
)
def test_hoy_argumentos_invalidos_aviso(conn, args):
    db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    assert commands.cmd_hoy(conn, args) == "Usa /hoy clean 70 80 85"
    assert conn.execute("SELECT COUNT(*) FROM plan_items").fetchone()[0] == 0


@pytest.mark.parametrize("valor", ["0", "121"])
def test_hoy_porcentaje_fuera_de_rango_motivo_y_ejemplo(conn, valor):
    # Estos dos casos eran "aviso de uso" en la 001; la 002 (RF-09, CL-17)
    # exige motivo + ejemplo, sin guardar nada.
    db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    texto = commands.cmd_hoy(conn, ["clean", valor])
    assert texto == "El porcentaje tiene que estar entre 1 y 120. Usa /hoy clean 70 80 85"
    assert conn.execute("SELECT COUNT(*) FROM plan_items").fetchone()[0] == 0


def test_hoy_sin_sesion_abierta_aviso_sin_cambiar_nada(conn):
    assert (
        commands.cmd_hoy(conn, ["clean", "70"]) == "No hay sesión abierta, envía /inicio"
    )
    assert conn.execute("SELECT COUNT(*) FROM plan_items").fetchone()[0] == 0


def test_hoy_ejercicio_sin_rm_aviso_sin_cambiar_nada(conn):
    db.open_session(conn)
    assert (
        commands.cmd_hoy(conn, ["clean", "70"])
        == "No tengo RM de clean, cárgalo con /rm"
    )
    assert conn.execute("SELECT COUNT(*) FROM plan_items").fetchone()[0] == 0


def test_hoy_convierte_y_guarda_el_plan_en_orden(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 120)
    texto = commands.cmd_hoy(conn, ["clean", "70", "80", "85"])
    assert texto == "70% → 84 kg\n80% → 96 kg\n85% → 102 kg"
    assert db.get_next_plan_item(conn, session_id, "clean")["weight_kg"] == 84


def test_hoy_porcentaje_con_decimal(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 120)
    texto = commands.cmd_hoy(conn, ["clean", "77,5"])
    assert texto == "77,5% → 93 kg"
    assert db.get_next_plan_item(conn, session_id, "clean")["weight_kg"] == 93


def test_hoy_nombre_normalizado_comparte_el_rm(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    texto = commands.cmd_hoy(conn, ["Clean", "70"])
    assert texto == "70% → 70 kg"
    assert db.get_next_plan_item(conn, session_id, "clean") is not None


def test_hoy_valores_repetidos_se_guardan_completos_y_en_orden(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 120)
    args = ["clean", "70", "80", "85", "70", "80", "85", "70", "80", "85"]
    texto = commands.cmd_hoy(conn, args)
    assert texto.splitlines() == ["70% → 84 kg", "80% → 96 kg", "85% → 102 kg"] * 3
    items = conn.execute(
        "SELECT position, weight_kg FROM plan_items ORDER BY position"
    ).fetchall()
    assert [item["weight_kg"] for item in items] == [84, 96, 102] * 3


def test_hoy_reemplaza_el_plan_del_mismo_ejercicio(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    db.save_rm(conn, "front", 60)
    commands.cmd_hoy(conn, ["clean", "70", "80"])
    commands.cmd_hoy(conn, ["front", "80"])
    commands.cmd_hoy(conn, ["clean", "90"])  # repite /hoy de clean
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM plan_items WHERE exercise = 'clean'"
        ).fetchone()[0]
        == 1
    )
    assert db.get_next_plan_item(conn, session_id, "clean")["weight_kg"] == 90
    assert db.get_next_plan_item(conn, session_id, "front")["weight_kg"] == 48  # intacto


def test_hoy_repite_reinicia_el_orden_del_consumo(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    commands.cmd_hoy(conn, ["clean", "70"])
    item = db.get_next_plan_item(conn, session_id, "clean")
    db.consume_plan_item(conn, item["id"])
    commands.cmd_hoy(conn, ["clean", "80"])  # el plan nuevo empieza de cero
    assert db.get_next_plan_item(conn, session_id, "clean")["weight_kg"] == 80


def test_hoy_nombre_multipalabra(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "front squat", 140)
    texto = commands.cmd_hoy(conn, ["front", "squat", "70", "80"])
    assert texto == "70% → 98 kg\n80% → 112 kg"
    assert db.get_next_plan_item(conn, session_id, "front squat")["weight_kg"] == 98


def test_hoy_multipalabra_usa_el_rm_de_su_ejercicio(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "front squat", 140)
    db.save_rm(conn, "clean", 100)
    texto = commands.cmd_hoy(conn, ["front", "squat", "70"])
    assert texto == "70% → 98 kg"  # 140·0,7, no el RM de clean
    assert db.get_next_plan_item(conn, session_id, "front squat")["weight_kg"] == 98
    assert db.get_next_plan_item(conn, session_id, "clean") is None


def test_hoy_multipalabra_sin_rm_avisa(conn):
    db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    assert (
        commands.cmd_hoy(conn, ["front", "squat", "70"])
        == "No tengo RM de front squat, cárgalo con /rm"
    )


def test_hoy_sin_nombre_aviso_de_uso(conn):
    db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    assert commands.cmd_hoy(conn, ["70", "80"]) == "Usa /hoy clean 70 80 85"
    assert conn.execute("SELECT COUNT(*) FROM plan_items").fetchone()[0] == 0


def test_rm_nombre_multipalabra_normalizado(conn):
    texto = commands.cmd_rm(conn, ["Front", "Squat", "170"])
    assert texto == "RM de front squat guardado: 170 kg"
    assert db.get_rm(conn, "front squat") == 170
    assert db.get_rm(conn, "Front Squat") is None


# --- /log (RF-06, CL-2, CL-3, CL-8) ---


def test_log_sin_sesion_abierta_aviso_sin_guardar(conn):
    assert (
        commands.cmd_log(conn, ["clean", "84x5"]) == "No hay sesión abierta, envía /inicio"
    )
    assert conn.execute("SELECT COUNT(*) FROM series").fetchone()[0] == 0


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["clean"],
        ["clean", "84"],
        ["clean", "84x"],
        ["clean", "x5"],
        ["clean", "84x5.5"],
        ["clean", "84x0"],
        ["clean", "84x-5"],
        ["clean", "1e3x5"],
        ["clean", "84x5", "extra"],
        ["84x5"],
    ],
)
def test_log_argumentos_invalidos_aviso_unico_sin_guardar(conn, args):
    db.open_session(conn)
    assert commands.cmd_log(conn, args) == "Usa /log clean 84x5"
    assert conn.execute("SELECT COUNT(*) FROM series").fetchone()[0] == 0


def test_log_sin_plan_se_guarda_con_planificado_vacio(conn):
    session_id = db.open_session(conn)
    texto = commands.cmd_log(conn, ["clean", "84x5"])
    assert texto == "clean · serie 1: 84 kg × 5"
    serie = db.list_series(conn, session_id)[0]
    assert serie["planned_weight_kg"] is None and serie["plan_item_id"] is None


def test_log_con_plan_toma_el_siguiente_en_orden(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    commands.cmd_hoy(conn, ["clean", "70", "80"])
    assert (
        commands.cmd_log(conn, ["clean", "70x5"])
        == "clean · serie 1: 70 kg × 5 (plan 70)"
    )
    assert (
        commands.cmd_log(conn, ["clean", "72x5"])
        == "clean · serie 2: 72 kg × 5 (plan 80)"
    )
    series = db.list_series(conn, session_id)
    assert [s["planned_weight_kg"] for s in series] == [70, 80]
    assert all(s["plan_item_id"] is not None for s in series)


def test_log_plan_con_valores_repetidos_consumidos_en_orden(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 120)
    commands.cmd_hoy(
        conn, ["clean", "70", "80", "85", "70", "80", "85", "70", "80", "85"]
    )
    for peso in (84, 96, 102, 84, 96, 102, 84, 96, 102):
        commands.cmd_log(conn, ["clean", f"{peso}x5"])
    series = db.list_series(conn, session_id)
    assert [s["planned_weight_kg"] for s in series] == [84, 96, 102] * 3
    assert len({s["plan_item_id"] for s in series}) == 9  # cada ítem, solo una vez


def test_log_real_distinto_del_plan(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 120)
    commands.cmd_hoy(conn, ["clean", "80"])  # 96 kg
    texto = commands.cmd_log(conn, ["clean", "95x5"])
    assert texto == "clean · serie 1: 95 kg × 5 (plan 96)"
    serie = db.list_series(conn, session_id)[0]
    assert serie["real_weight_kg"] == 95 and serie["planned_weight_kg"] == 96


def test_log_mas_que_valores_de_plan_sigue_guardando(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    commands.cmd_hoy(conn, ["clean", "70"])
    commands.cmd_log(conn, ["clean", "70x5"])
    texto = commands.cmd_log(conn, ["clean", "75x5"])  # plan agotado (CL-3)
    assert texto == "clean · serie 2: 75 kg × 5"
    serie = db.list_series(conn, session_id)[1]
    assert serie["planned_weight_kg"] is None and serie["plan_item_id"] is None


def test_log_nombre_multipalabra(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "front squat", 140)
    commands.cmd_hoy(conn, ["front", "squat", "70"])  # 98 kg
    texto = commands.cmd_log(conn, ["front", "squat", "95x3"])
    assert texto == "front squat · serie 1: 95 kg × 3 (plan 98)"
    serie = db.list_series(conn, session_id)[0]
    assert serie["exercise"] == "front squat" and serie["planned_weight_kg"] == 98


def test_log_mayusculas_y_espacios_extra_comparten_serie(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    commands.cmd_hoy(conn, ["clean", "70", "80"])
    commands.cmd_log(conn, ["Clean", "70x5"])
    texto = commands.cmd_log(conn, ["  CLEAN  ", "72x5"])
    assert texto == "clean · serie 2: 72 kg × 5 (plan 80)"
    assert [s["exercise"] for s in db.list_series(conn, session_id)] == ["clean", "clean"]


def test_log_tras_repetir_hoy_reinicia_el_plan(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    commands.cmd_hoy(conn, ["clean", "70"])
    commands.cmd_log(conn, ["clean", "70x5"])  # consume el primer plan
    commands.cmd_hoy(conn, ["clean", "70", "80"])  # repite /hoy → orden nuevo
    texto = commands.cmd_log(conn, ["clean", "71x5"])
    assert texto == "clean · serie 2: 71 kg × 5 (plan 70)"
    assert db.list_series(conn, session_id)[0]["planned_weight_kg"] == 70  # la vieja no cambia


# --- /deshacer (RF-07, CL-2, CL-9) ---


def test_deshacer_sin_sesion_abierta_aviso(conn):
    assert commands.cmd_deshacer(conn, []) == "No hay sesión abierta, envía /inicio"


def test_deshacer_con_argumentos_aviso_de_uso(conn):
    db.open_session(conn)
    assert commands.cmd_deshacer(conn, ["x"]) == "Usa /deshacer (sin nada más)"


def test_deshacer_sin_series_aviso(conn):
    db.open_session(conn)
    assert commands.cmd_deshacer(conn, []) == "No hay series en esta sesión"


def test_deshacer_borra_la_ultima_y_confirma(conn):
    session_id = db.open_session(conn)
    commands.cmd_log(conn, ["clean", "84x5"])
    commands.cmd_log(conn, ["clean", "82x5"])
    texto = commands.cmd_deshacer(conn, [])
    assert texto == "Borrada: clean 82x5"
    series = db.list_series(conn, session_id)
    assert len(series) == 1 and series[0]["real_weight_kg"] == 84


def test_deshacer_libera_el_mismo_plan_item(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    commands.cmd_hoy(conn, ["clean", "70", "80"])
    commands.cmd_log(conn, ["clean", "70x5"])  # ítem 1 (70)
    commands.cmd_log(conn, ["clean", "80x5"])  # ítem 2 (80)
    commands.cmd_deshacer(conn, [])  # borra la serie del ítem 2
    texto = commands.cmd_log(conn, ["clean", "90x5"])
    assert texto == "clean · serie 2: 90 kg × 5 (plan 80)"  # repite ese ítem exacto
    states = conn.execute(
        "SELECT position, consumed FROM plan_items ORDER BY position"
    ).fetchall()
    assert [(i["position"], i["consumed"]) for i in states] == [(1, 1), (2, 1)]


def test_deshacer_solo_borra_la_ultima(conn):
    session_id = db.open_session(conn)
    commands.cmd_log(conn, ["clean", "84x5"])
    commands.cmd_log(conn, ["front", "squat", "60x3"])  # multipalabra
    commands.cmd_log(conn, ["clean", "82x5"])
    ids = [s["id"] for s in db.list_series(conn, session_id)]
    texto = commands.cmd_deshacer(conn, [])
    assert texto == "Borrada: clean 82x5"
    assert [s["id"] for s in db.list_series(conn, session_id)] == ids[:2]


# --- T5: /hoy con reps y rangos (RF-03, RF-09, CL-13 a CL-19) ---


def test_hoy_con_reps_guarda_y_responde_con_x(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    texto = commands.cmd_hoy(conn, ["clean", "65x3"])
    assert texto == "65% × 3 → 65 kg"
    item = db.get_next_plan_item(conn, session_id, "clean")
    assert (item["weight_kg"], item["reps"], item["range_max_kg"]) == (65, 3, None)


def test_hoy_con_rango_y_reps(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    texto = commands.cmd_hoy(conn, ["clean", "80-85x1"])
    assert texto == "80-85% × 1 → 80-85 kg"
    item = db.get_next_plan_item(conn, session_id, "clean")
    assert (item["weight_kg"], item["reps"], item["range_max_kg"]) == (80, 1, 85)


def test_hoy_mixto_cuatro_formatos(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    texto = commands.cmd_hoy(conn, ["clean", "70", "65x3", "80-85", "80-85x1"])
    assert texto.splitlines() == [
        "70% → 70 kg",
        "65% × 3 → 65 kg",
        "80-85% → 80-85 kg",
        "80-85% × 1 → 80-85 kg",
    ]
    items = conn.execute(
        "SELECT position, weight_kg, reps, range_max_kg FROM plan_items"
        " ORDER BY position"
    ).fetchall()
    assert [(i["weight_kg"], i["reps"], i["range_max_kg"]) for i in items] == [
        (70, None, None),
        (65, 3, None),
        (80, None, 85),
        (80, 1, 85),
    ]
    assert session_id == db.get_open_session(conn)["id"]


def test_hoy_lista_de_nueve_entradas_en_orden(conn):
    db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    args = ["clean"] + ["70", "65x3", "80-85"] * 3
    texto = commands.cmd_hoy(conn, args)
    assert texto.splitlines() == [
        "70% → 70 kg",
        "65% × 3 → 65 kg",
        "80-85% → 80-85 kg",
    ] * 3
    items = conn.execute(
        "SELECT position, weight_kg, reps, range_max_kg FROM plan_items"
        " ORDER BY position"
    ).fetchall()
    assert [i["position"] for i in items] == list(range(1, 10))
    assert [(i["weight_kg"], i["reps"], i["range_max_kg"]) for i in items] == [
        (70, None, None),
        (65, 3, None),
        (80, None, 85),
    ] * 3


def test_hoy_con_error_no_guarda_nada_ni_toca_el_plan_anterior(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    commands.cmd_hoy(conn, ["clean", "70"])  # plan previo
    texto = commands.cmd_hoy(conn, ["clean", "80", "130"])  # primer error: fuera de rango
    assert texto == "El porcentaje tiene que estar entre 1 y 120. Usa /hoy clean 70 80 85"
    items = conn.execute(
        "SELECT position, weight_kg, consumed FROM plan_items"
    ).fetchall()
    assert [(i["position"], i["weight_kg"], i["consumed"]) for i in items] == [(1, 70, 0)]
    assert db.get_next_plan_item(conn, session_id, "clean")["weight_kg"] == 70


def test_hoy_primer_error_izquierda_a_derecha_y_nada_se_guarda(conn):
    db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    # CL-17: tres entradas inválidas; solo se informa la primera (A-4).
    texto = commands.cmd_hoy(conn, ["clean", "130", "65x0", "85-80"])
    assert texto == "El porcentaje tiene que estar entre 1 y 120. Usa /hoy clean 70 80 85"
    assert conn.execute("SELECT COUNT(*) FROM plan_items").fetchone()[0] == 0


def test_hoy_avisos_de_gramatica_con_motivo_y_ejemplo(conn):
    db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    assert (
        commands.cmd_hoy(conn, ["clean", "65", "x", "3"])  # CL-13: espacios
        == "'x' va pegada, sin espacios: 65x3"
    )
    assert (
        commands.cmd_hoy(conn, ["clean", "70", "-5"])  # CL-14
        == "'-5' no es válido: no se aceptan negativos. Usa /hoy clean 70 80 85"
    )
    assert (
        commands.cmd_hoy(conn, ["clean", "70", "80-"])  # CL-14
        == "'80-' es un rango incompleto: 80-85"
    )
    assert conn.execute("SELECT COUNT(*) FROM plan_items").fetchone()[0] == 0


def test_hoy_acepta_en_dash_y_mayusculas(conn):
    db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    texto = commands.cmd_hoy(conn, ["clean", "65X3", "80–85x1"])  # CL-18 y CL-15
    assert texto.splitlines() == ["65% × 3 → 65 kg", "80-85% × 1 → 80-85 kg"]
    assert conn.execute("SELECT COUNT(*) FROM plan_items").fetchone()[0] == 2


def test_hoy_repetido_con_rangos_reemplaza_solo_ese_ejercicio(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    db.save_rm(conn, "front squat", 140)
    commands.cmd_hoy(conn, ["clean", "80-85x1"])
    commands.cmd_hoy(conn, ["front", "squat", "70"])
    commands.cmd_hoy(conn, ["clean", "70-75x2"])  # repite /hoy de clean con rango
    clean = conn.execute(
        "SELECT weight_kg, reps, range_max_kg FROM plan_items WHERE exercise = 'clean'"
    ).fetchall()
    assert [(i["weight_kg"], i["reps"], i["range_max_kg"]) for i in clean] == [(70, 2, 75)]
    # El plan de front squat sigue intacto (CL-10).
    assert db.get_next_plan_item(conn, session_id, "front squat")["weight_kg"] == 98


def test_hoy_nombre_multipalabra_con_tokens(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "front squat", 140)
    texto = commands.cmd_hoy(conn, ["front", "squat", "65x3", "75x2"])
    assert texto.splitlines() == ["65% × 3 → 91 kg", "75% × 2 → 105 kg"]
    item = db.get_next_plan_item(conn, session_id, "front squat")
    assert item["weight_kg"] == 91 and item["reps"] == 3


# --- T5: /log con plan copiado a la serie (RF-04, A-1, A-3) ---


def test_log_con_plan_de_reps_copia_a_la_serie(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    commands.cmd_hoy(conn, ["clean", "65x3"])
    texto = commands.cmd_log(conn, ["clean", "64x3"])
    assert texto == "clean · serie 1: 64 kg × 3 (plan 65 kg × 3)"
    serie = db.list_series(conn, session_id)[0]
    assert (serie["planned_weight_kg"], serie["planned_reps"], serie["planned_max_kg"]) == (
        65,
        3,
        None,
    )


def test_log_con_plan_de_rango_confirma_con_rango(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    commands.cmd_hoy(conn, ["clean", "80-85x1"])
    texto = commands.cmd_log(conn, ["clean", "82x1"])
    assert texto == "clean · serie 1: 82 kg × 1 (plan 80-85 kg × 1)"
    serie = db.list_series(conn, session_id)[0]
    assert (serie["planned_weight_kg"], serie["planned_max_kg"], serie["planned_reps"]) == (
        80,
        85,
        1,
    )


def test_log_sin_plan_no_lleva_sufijo_y_la_serie_queda_vacia(conn):
    session_id = db.open_session(conn)
    texto = commands.cmd_log(conn, ["clean", "84x5"])
    assert texto == "clean · serie 1: 84 kg × 5"
    serie = db.list_series(conn, session_id)[0]
    assert serie["planned_weight_kg"] is None
    assert serie["planned_reps"] is None and serie["planned_max_kg"] is None


def test_log_plan_agotado_no_lleva_sufijo(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    commands.cmd_hoy(conn, ["clean", "65x3"])  # una sola entrada
    assert (
        commands.cmd_log(conn, ["clean", "64x3"])
        == "clean · serie 1: 64 kg × 3 (plan 65 kg × 3)"
    )
    texto = commands.cmd_log(conn, ["clean", "70x3"])  # plan agotado (CL-3)
    assert texto == "clean · serie 2: 70 kg × 3"
    serie = db.list_series(conn, session_id)[1]
    assert serie["planned_weight_kg"] is None and serie["planned_reps"] is None


def test_log_reps_reales_distintas_del_plan_sin_aviso(conn):
    # RF-04: plan de 3 reps y real de 5 → se guarda igual y sin aviso.
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    commands.cmd_hoy(conn, ["clean", "65x3"])
    texto = commands.cmd_log(conn, ["clean", "64x5"])
    assert texto == "clean · serie 1: 64 kg × 5 (plan 65 kg × 3)"
    serie = db.list_series(conn, session_id)[0]
    assert serie["reps"] == 5 and serie["planned_reps"] == 3


# --- T5: horas en UTC y /fin con rango (RF-02, RF-05, CL-12) ---


def test_inicio_muestra_la_hora_local_cerca_de_medianoche_utc(conn, monkeypatch):
    # CL-12: 01:00 UTC = 22:00 hora local del día anterior → sigue siendo "hoy".
    monkeypatch.setattr(
        core, "utc_now", lambda: datetime(2026, 10, 11, 1, 30, tzinfo=timezone.utc)
    )
    session_id = db.open_session(conn)
    _fijar_inicio(conn, session_id, datetime(2026, 10, 11, 1, 0))  # 01:00 UTC
    texto = commands.cmd_inicio(conn, [])
    assert texto == "Sesión abierta desde las 22:00. Ciérrala con /fin"


def test_fin_duracion_correcta_cruzando_medianoche_utc(conn, monkeypatch):
    # §4: la duración se resta con marcas en UTC, nunca con hora local naive.
    monkeypatch.setattr(
        core, "utc_now", lambda: datetime(2026, 10, 11, 3, 0, tzinfo=timezone.utc)
    )
    session_id = db.open_session(conn)
    _fijar_inicio(conn, session_id, datetime(2026, 10, 11, 2, 30))  # 02:30 UTC
    db.insert_series(conn, session_id, "clean", 84, 5, None, None)
    texto = commands.cmd_fin(conn, [])
    assert "Duración: 30 min" in texto


def test_fin_par_de_rango_desde_la_serie(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    commands.cmd_hoy(conn, ["clean", "80-85x1"])
    commands.cmd_log(conn, ["clean", "82x1"])
    texto = commands.cmd_fin(conn, [])
    assert "Duración: " in texto
    assert "clean: 1 serie · 1 repetición · volumen 82 kg · máx 82 kg" in texto
    assert "plan→real: 80-85→82" in texto  # RF-05: par con rango, flecha de la 001
    assert texto.splitlines()[-1] == "Volumen total: 82 kg"
    assert db.get_open_session(conn) is None


def test_deshacer_restaura_el_item_con_reps_y_rango(conn):
    session_id = db.open_session(conn)
    db.save_rm(conn, "clean", 100)
    commands.cmd_hoy(conn, ["clean", "80-85x1", "70x3"])
    primero = db.get_next_plan_item(conn, session_id, "clean")
    commands.cmd_log(conn, ["clean", "82x1"])
    assert commands.cmd_deshacer(conn, []) == "Borrada: clean 82x1"
    restaurado = db.get_next_plan_item(conn, session_id, "clean")
    assert restaurado["id"] == primero["id"]  # el mismo ítem, liberado (CL-8)
    assert (restaurado["weight_kg"], restaurado["range_max_kg"], restaurado["reps"]) == (
        80,
        85,
        1,
    )


# --- separación de capas (constitución 3) ---


def test_commands_no_importa_telegram():
    fuente = Path(commands_module.__file__).read_text(encoding="utf-8").lower()
    assert "telegram" not in fuente
