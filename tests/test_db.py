"""Tests de db: esquema, perfil y RM (RF-01, RF-02, RNF-3). Siempre con BD temporal."""

import hashlib
import sqlite3

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from boxlog import commands, core, db
from boxlog.core import PlannedSet


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    db.init_schema(connection)
    yield connection
    connection.close()


# --- esquema y PRAGMA (plan §3) ---


def test_connect_crea_la_carpeta_contenedora_si_no_existe(tmp_path):
    db_path = tmp_path / "nueva" / "sub" / "boxlog.db"
    assert not db_path.parent.exists()
    connection = db.connect(db_path)
    connection.close()
    assert db_path.exists()


def test_connect_en_memoria_no_necesita_carpeta():
    connection = db.connect(":memory:")
    db.init_schema(connection)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
    connection.close()


def test_conecta_con_foreign_keys_activas(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_init_schema_crea_las_cinco_tablas(conn):
    tablas = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"profile", "rm_history", "sessions", "plan_items", "series"} <= tablas


def test_plan_items_requiere_sesion_existente(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO plan_items (session_id, exercise, position, weight_kg)"
            " VALUES (999, 'clean', 1, 84)"
        )


def test_init_schema_preserva_los_datos_existentes(conn):
    db.save_rm(conn, "clean", 100)
    db.init_schema(conn)
    assert db.get_rm(conn, "clean") == 100
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2  # versión intacta (v2)


def test_init_schema_fija_user_version_en_2(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2


def test_init_schema_no_cambia_una_version_existente(conn):
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    db.init_schema(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 7


# --- perfil con historial (RF-01) ---


def test_get_profile_vacio_devuelve_none(conn):
    assert db.get_profile(conn) is None


def test_save_profile_y_get_devuelve_el_ultimo(conn):
    db.save_profile(conn, 78, 175)
    db.save_profile(conn, 79.5, 175)
    assert db.get_profile(conn) == {"weight_kg": 79.5, "height_cm": 175}


def test_profile_conserva_el_historial(conn):
    db.save_profile(conn, 78, 175)
    db.save_profile(conn, 79.5, 175)
    assert conn.execute("SELECT COUNT(*) FROM profile").fetchone()[0] == 2


# --- RM con historial (RF-02) ---


def test_get_rm_sin_datos_devuelve_none(conn):
    assert db.get_rm(conn, "clean") is None


def test_get_rm_devuelve_el_ultimo_cargado(conn):
    db.save_rm(conn, "clean", 100)
    db.save_rm(conn, "clean", 102)
    assert db.get_rm(conn, "clean") == 102


def test_rm_de_un_ejercicio_no_afecta_a_otro(conn):
    db.save_rm(conn, "clean", 100)
    db.save_rm(conn, "front", 60)
    assert db.get_rm(conn, "clean") == 100
    assert db.get_rm(conn, "front") == 60


def test_rm_conserva_el_historial(conn):
    db.save_rm(conn, "clean", 100)
    db.save_rm(conn, "clean", 102)
    assert conn.execute("SELECT COUNT(*) FROM rm_history").fetchone()[0] == 2


def test_list_rms_vacio_devuelve_lista_vacia(conn):
    assert db.list_rms(conn) == []


def test_list_rms_devuelve_los_vigentes(conn):
    db.save_rm(conn, "clean", 100)
    db.save_rm(conn, "front", 60)
    db.save_rm(conn, "clean", 102)
    assert db.list_rms(conn) == [("clean", 102), ("front", 60)]


# --- sesiones (RF-03, CL-11) ---


def test_open_session_y_get_open_session(conn):
    session_id = db.open_session(conn)
    abierta = db.get_open_session(conn)
    assert abierta["id"] == session_id
    assert abierta["started_at"]  # lleva marca de tiempo


def test_una_sola_sesion_abierta_a_la_vez(conn):
    db.open_session(conn)
    assert db.open_session(conn) is None  # no crea una segunda
    abiertas = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE ended_at IS NULL"
    ).fetchone()[0]
    assert abiertas == 1


def test_close_session(conn):
    session_id = db.open_session(conn)
    db.close_session(conn, session_id)
    assert db.get_open_session(conn) is None
    assert db.get_session(conn, session_id)["ended_at"]  # cerrada con marca


def test_sesion_abierta_sobrevive_al_reabrir_la_conexion(tmp_path):
    db_path = tmp_path / "boxlog.db"
    connection = db.connect(db_path)
    db.init_schema(connection)
    session_id = db.open_session(connection)
    connection.close()
    otra = db.connect(db_path)  # reinicio simulado del bot
    abierta = db.get_open_session(otra)
    assert abierta is not None and abierta["id"] == session_id
    otra.close()


# --- plan por sesión (RF-05) ---


def test_replace_plan_crea_items_en_orden_y_sin_consumir(conn):
    sid = db.open_session(conn)
    db.replace_plan(conn, sid, "clean", [84, 96])
    siguiente = db.get_next_plan_item(conn, sid, "clean")
    assert siguiente["weight_kg"] == 84
    assert siguiente["position"] == 1
    assert conn.execute("SELECT COUNT(*) FROM plan_items").fetchone()[0] == 2


def test_replace_plan_reemplaza_el_plan_del_ejercicio(conn):
    sid = db.open_session(conn)
    db.replace_plan(conn, sid, "clean", [84, 96])
    db.replace_plan(conn, sid, "clean", [90])
    assert conn.execute("SELECT COUNT(*) FROM plan_items").fetchone()[0] == 1
    siguiente = db.get_next_plan_item(conn, sid, "clean")
    assert siguiente["weight_kg"] == 90
    assert siguiente["position"] == 1  # el orden se reinicia


def test_replace_plan_no_toca_otro_ejercicio_ni_otra_sesion(conn):
    s1 = db.open_session(conn)
    db.replace_plan(conn, s1, "clean", [84])
    db.replace_plan(conn, s1, "front", [60])
    db.close_session(conn, s1)
    s2 = db.open_session(conn)
    db.replace_plan(conn, s2, "clean", [100])
    db.replace_plan(conn, s1, "clean", [90])  # reemplazo tardío en la sesión 1
    assert db.get_next_plan_item(conn, s1, "front")["weight_kg"] == 60  # intacto
    assert db.get_next_plan_item(conn, s2, "clean")["weight_kg"] == 100  # intacto
    assert db.get_next_plan_item(conn, s1, "clean")["weight_kg"] == 90


def test_consumo_del_plan_en_orden(conn):
    sid = db.open_session(conn)
    db.replace_plan(conn, sid, "clean", [84, 96])
    primero = db.get_next_plan_item(conn, sid, "clean")
    db.consume_plan_item(conn, primero["id"])
    segundo = db.get_next_plan_item(conn, sid, "clean")
    assert segundo["weight_kg"] == 96
    db.consume_plan_item(conn, segundo["id"])
    assert db.get_next_plan_item(conn, sid, "clean") is None


def test_release_plan_item_devuelve_la_disponibilidad(conn):
    sid = db.open_session(conn)
    db.replace_plan(conn, sid, "clean", [84])
    item = db.get_next_plan_item(conn, sid, "clean")
    db.consume_plan_item(conn, item["id"])
    assert db.get_next_plan_item(conn, sid, "clean") is None
    db.release_plan_item(conn, item["id"])
    assert db.get_next_plan_item(conn, sid, "clean")["id"] == item["id"]


# --- series (RF-06, RF-07) ---


def test_insert_series_y_count_series(conn):
    sid = db.open_session(conn)
    db.insert_series(conn, sid, "clean", 84, 5, None, None)
    db.insert_series(conn, sid, "clean", 82, 5, 84, None)
    assert db.count_series(conn, sid, "clean") == 2
    assert db.count_series(conn, sid, "front") == 0


def test_list_series_devuelve_las_de_su_sesion_en_orden(conn):
    s1 = db.open_session(conn)
    primera = db.insert_series(conn, s1, "clean", 84, 5, None, None)
    db.insert_series(conn, s1, "clean", 82, 5, 84, None)
    db.close_session(conn, s1)
    s2 = db.open_session(conn)
    db.insert_series(conn, s2, "front", 40, 3, None, None)
    serie = db.list_series(conn, s1)[0]
    assert serie["id"] == primera
    assert serie["exercise"] == "clean"
    assert serie["real_weight_kg"] == 84
    assert serie["reps"] == 5
    assert serie["planned_weight_kg"] is None
    assert [s["exercise"] for s in db.list_series(conn, s2)] == ["front"]


def test_get_last_series(conn):
    sid = db.open_session(conn)
    db.insert_series(conn, sid, "clean", 84, 5, None, None)
    db.insert_series(conn, sid, "clean", 82, 5, 84, None)
    assert db.get_last_series(conn, sid)["real_weight_kg"] == 82


def test_delete_series_borra_solo_esa_serie(conn):
    sid = db.open_session(conn)
    ids = [db.insert_series(conn, sid, "clean", w, 5, None, None) for w in (84, 82, 90)]
    db.delete_series(conn, ids[1])
    assert [s["id"] for s in db.list_series(conn, sid)] == [ids[0], ids[2]]


def test_deshacer_libera_el_plan_para_la_siguiente_serie(conn):
    sid = db.open_session(conn)
    db.replace_plan(conn, sid, "clean", [84])
    item = db.get_next_plan_item(conn, sid, "clean")
    db.consume_plan_item(conn, item["id"])
    serie_id = db.insert_series(conn, sid, "clean", 82, 5, item["weight_kg"], item["id"])
    db.release_plan_item(conn, item["id"])
    db.delete_series(conn, serie_id)
    assert db.get_next_plan_item(conn, sid, "clean")["id"] == item["id"]


def test_plan_item_borrado_deja_null_pero_conserva_el_planificado(conn):
    sid = db.open_session(conn)
    db.replace_plan(conn, sid, "clean", [84, 96])
    item = db.get_next_plan_item(conn, sid, "clean")
    db.consume_plan_item(conn, item["id"])
    db.insert_series(conn, sid, "clean", 82, 5, item["weight_kg"], item["id"])
    db.replace_plan(conn, sid, "clean", [100])  # repetir /hoy borra los items
    serie = db.list_series(conn, sid)[0]
    assert serie["plan_item_id"] is None  # ON DELETE SET NULL
    assert serie["planned_weight_kg"] == 84  # el plan de la serie se conserva


# --- esquema v2, UTC y copia del plan (T4: RF-01, RF-02, RF-06, A-2, A-3) ---


def _columnas(connection, tabla):
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({tabla})")}


def test_base_nueva_es_v2_con_las_columnas_nuevas(conn):
    assert {"reps", "range_max_kg"} <= _columnas(conn, "plan_items")
    assert {"planned_reps", "planned_max_kg"} <= _columnas(conn, "series")
    assert "logged_at" not in _columnas(conn, "series")  # A-2: la hora de la serie es created_at
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2  # CL-11


def test_init_schema_en_v2_es_no_op(conn):
    db.init_schema(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2


def test_now_es_utc_en_el_mismo_formato_iso():
    marca = db._now()
    parseada = datetime.fromisoformat(marca)
    assert parseada.tzinfo is None  # convención de la 002: marca sin huso = UTC (core._as_utc)
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs(ahora - parseada) < timedelta(seconds=5)


def test_marcas_nuevas_se_guardan_en_utc(conn, monkeypatch):
    fija = "2026-10-16T12:00:00"
    monkeypatch.setattr(db, "_now", lambda: fija)
    sid = db.open_session(conn)
    db.save_profile(conn, 78, 175)
    db.save_rm(conn, "clean", 100)
    db.insert_series(conn, sid, "clean", 84, 5, None, None)
    marcas = [
        db.get_open_session(conn)["started_at"],
        conn.execute("SELECT created_at FROM profile").fetchone()[0],
        conn.execute("SELECT created_at FROM rm_history").fetchone()[0],
        conn.execute("SELECT created_at FROM series").fetchone()[0],
    ]
    assert marcas == [fija] * 4


def test_replace_plan_con_rangos_y_reps(conn):
    sid = db.open_session(conn)
    db.replace_plan(
        conn,
        sid,
        "clean",
        [PlannedSet(64.0, 68.0, 1), PlannedSet(70.0, None, 3), PlannedSet(80.0, 85.0, None)],
    )
    primero = db.get_next_plan_item(conn, sid, "clean")
    assert (primero["weight_kg"], primero["range_max_kg"], primero["reps"]) == (
        64.0,
        68.0,
        1,
    )
    db.consume_plan_item(conn, primero["id"])
    segundo = db.get_next_plan_item(conn, sid, "clean")
    assert (segundo["weight_kg"], segundo["range_max_kg"], segundo["reps"]) == (
        70.0,
        None,
        3,
    )
    db.consume_plan_item(conn, segundo["id"])
    tercero = db.get_next_plan_item(conn, sid, "clean")
    assert (tercero["weight_kg"], tercero["range_max_kg"], tercero["reps"]) == (
        80.0,
        85.0,
        None,
    )


def test_replace_plan_acepta_solo_pesos_como_en_la_001(conn):
    # Compatibilidad: la llamada actual de commands.py pasa solo pesos.
    sid = db.open_session(conn)
    db.replace_plan(conn, sid, "clean", [84.0, 96.0])
    item = db.get_next_plan_item(conn, sid, "clean")
    assert (item["weight_kg"], item["range_max_kg"], item["reps"]) == (84.0, None, None)


def test_insert_series_copia_el_plan_a_la_serie(conn):
    sid = db.open_session(conn)
    db.replace_plan(conn, sid, "clean", [PlannedSet(64.0, 68.0, 1)])
    item = db.get_next_plan_item(conn, sid, "clean")
    db.insert_series(
        conn,
        sid,
        "clean",
        66,
        2,
        item["weight_kg"],
        item["id"],
        planned_max_kg=item["range_max_kg"],
        planned_reps=item["reps"],
    )
    serie = db.list_series(conn, sid)[0]
    assert (serie["planned_weight_kg"], serie["planned_max_kg"], serie["planned_reps"]) == (
        64.0,
        68.0,
        1,
    )


def test_insert_series_sin_extras_deja_null(conn):
    # Compatibilidad: la llamada actual de commands.py no pasa reps ni máximo (A-3).
    sid = db.open_session(conn)
    db.replace_plan(conn, sid, "clean", [84.0])
    item = db.get_next_plan_item(conn, sid, "clean")
    db.insert_series(conn, sid, "clean", 84, 5, item["weight_kg"], item["id"])
    db.insert_series(conn, sid, "front squat", 140, 5, None, None)
    con_plan, sin_plan = db.list_series(conn, sid)
    assert con_plan["planned_max_kg"] is None and con_plan["planned_reps"] is None
    assert sin_plan["planned_weight_kg"] is None
    assert sin_plan["planned_max_kg"] is None and sin_plan["planned_reps"] is None


def test_list_series_lee_de_la_serie_sin_join(conn):
    # El rango/reps de la serie no dependen de plan_items: repetir /hoy no los toca (A-3).
    sid = db.open_session(conn)
    db.replace_plan(conn, sid, "clean", [PlannedSet(64.0, 68.0, 1)])
    item = db.get_next_plan_item(conn, sid, "clean")
    db.insert_series(
        conn,
        sid,
        "clean",
        66,
        2,
        item["weight_kg"],
        item["id"],
        planned_max_kg=item["range_max_kg"],
        planned_reps=item["reps"],
    )
    db.replace_plan(conn, sid, "clean", [PlannedSet(50.0, 55.0, 1)])  # plan posterior distinto
    serie = db.list_series(conn, sid)[0]
    assert serie["planned_max_kg"] == 68.0 and serie["planned_reps"] == 1
    assert db.get_last_series(conn, sid)["planned_weight_kg"] == 64.0


def test_consumo_en_orden_con_nueve_valores_repetidos_y_deshacer(conn):
    sid = db.open_session(conn)
    db.replace_plan(conn, sid, "clean", [PlannedSet(84.0, None, 3)] * 9)
    vistos = []
    for _ in range(9):
        item = db.get_next_plan_item(conn, sid, "clean")
        vistos.append(item["id"])
        db.consume_plan_item(conn, item["id"])
    assert len(set(vistos)) == 9  # ids distintos aunque los valores se repitan
    assert db.get_next_plan_item(conn, sid, "clean") is None
    db.release_plan_item(conn, vistos[7])  # /deshacer libera exactamente ese ítem
    assert db.get_next_plan_item(conn, sid, "clean")["id"] == vistos[7]


# --- migración 1 → 2 (T6: RF-02, RF-06, CL-9, CL-10, CL-11, RNF-1) ---
# (sustituye al test de protección v1 de T4: la rama 1 ahora migra en vez de rechazar)

# Esquema EXACTO de la spec 001 (user_version 1), para construir bases sintéticas.
_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY,
    weight_kg REAL NOT NULL,
    height_cm REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rm_history (
    id INTEGER PRIMARY KEY,
    exercise TEXT NOT NULL,
    weight_kg REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT
);
CREATE TABLE IF NOT EXISTS plan_items (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    exercise TEXT NOT NULL,
    position INTEGER NOT NULL,
    weight_kg REAL NOT NULL,
    consumed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS series (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    exercise TEXT NOT NULL,
    real_weight_kg REAL NOT NULL,
    reps INTEGER NOT NULL,
    planned_weight_kg REAL,
    plan_item_id INTEGER REFERENCES plan_items(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);
"""

# Datos de partida (horas locales de la 001) y lo que debe quedar tras el +3 h,
# con cruces de día, mes y año entre las filas de la misma tabla.
_SESIONES_LOCAL = [
    (1, "2026-10-16T23:30:00", "2026-10-17T01:15:00"),
    (2, "2026-12-31T22:00:00", None),  # sesión abierta: ended_at NULL
]
_SESIONES_UTC = [
    (1, "2026-10-17T02:30:00", "2026-10-17T04:15:00"),  # 23:30 → 02:30 del día siguiente
    (2, "2027-01-01T01:00:00", None),  # 22:00 del 31/12 → 01:00 del 01/01
]
_PERFIL_LOCAL = [(1, 78.5, 175.0, "2026-11-30T23:50:00")]
_PERFIL_UTC = [(1, 78.5, 175.0, "2026-12-01T02:50:00")]  # cruza mes
_RM_LOCAL = [
    (1, "clean", 120.0, "2026-05-01T19:00:00"),
    (2, "front squat", 170.0, "2026-07-31T23:30:00"),  # cruza mes
]
_RM_UTC = [
    (1, "clean", 120.0, "2026-05-01T22:00:00"),
    (2, "front squat", 170.0, "2026-08-01T02:30:00"),
]
_SERIES_LOCAL = [
    (1, 1, "clean", 84.0, 5, 84.0, 1, "2026-10-16T23:40:00"),  # cruza día
    (2, 1, "clean", 96.0, 3, 96.0, None, "2026-10-17T00:10:00"),
]
_PLAN_LOCAL = [
    (1, 1, "clean", 1, 84.0, 1),  # consumido por la serie 1
    (2, 1, "clean", 2, 96.0, 0),  # sin consumir
]
_CONTEOS = {"profile": 1, "rm_history": 2, "sessions": 2, "plan_items": 2, "series": 2}


def _crear_base_v1(base) -> sqlite3.Connection:
    """Base v1 sintética con el esquema exacto de la 001 y datos en todas las tablas."""
    connection = db.connect(base)
    connection.executescript(_SCHEMA_V1)
    connection.execute("PRAGMA user_version = 1")
    connection.execute(
        "INSERT INTO profile (weight_kg, height_cm, created_at) VALUES (?, ?, ?)",
        _PERFIL_LOCAL[0][1:],
    )
    connection.executemany(
        "INSERT INTO rm_history (id, exercise, weight_kg, created_at)"
        " VALUES (?, ?, ?, ?)",
        _RM_LOCAL,
    )
    connection.executemany(
        "INSERT INTO sessions (id, started_at, ended_at) VALUES (?, ?, ?)",
        _SESIONES_LOCAL,
    )
    connection.executemany(
        "INSERT INTO plan_items (id, session_id, exercise, position, weight_kg,"
        " consumed) VALUES (?, ?, ?, ?, ?, ?)",
        _PLAN_LOCAL,
    )
    connection.executemany(
        "INSERT INTO series (id, session_id, exercise, real_weight_kg, reps,"
        " planned_weight_kg, plan_item_id, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        _SERIES_LOCAL,
    )
    connection.commit()
    return connection


@pytest.fixture
def base_v1(tmp_path):
    """(conexión, ruta) de una base v1 sintética; la cierra al terminar."""
    base = tmp_path / "boxlog.db"
    connection = _crear_base_v1(base)
    yield connection, base
    connection.close()


def _filas(connection, sql) -> list[tuple]:
    return [tuple(row) for row in connection.execute(sql).fetchall()]


def _todas_las_horas(connection) -> list[tuple]:
    """Snapshot de todas las marcas de la base, para comparar antes/después."""
    return (
        _filas(connection, "SELECT id, started_at, ended_at FROM sessions ORDER BY id")
        + _filas(connection, "SELECT id, created_at FROM profile ORDER BY id")
        + _filas(connection, "SELECT id, created_at FROM rm_history ORDER BY id")
        + _filas(connection, "SELECT id, created_at FROM series ORDER BY id")
    )


def test_migracion_v1_a_v2_completa(base_v1):
    connection, base = base_v1
    db.init_schema(connection)

    assert connection.execute("PRAGMA user_version").fetchone()[0] == 2  # RF-06
    assert connection.in_transaction is False  # la transacción terminó con COMMIT
    columnas_plan = {
        row["name"] for row in connection.execute("PRAGMA table_info(plan_items)")
    }
    columnas_serie = {
        row["name"] for row in connection.execute("PRAGMA table_info(series)")
    }
    assert {"reps", "range_max_kg"} <= columnas_plan
    assert {"planned_reps", "planned_max_kg"} <= columnas_serie
    assert "logged_at" not in columnas_serie  # A-2: la hora de serie ya existía

    # Filas viejas: columnas nuevas vacías (CL-9) y todo lo demás intacto (RNF-1).
    assert _filas(
        connection,
        "SELECT id, session_id, exercise, position, weight_kg, consumed, reps,"
        " range_max_kg FROM plan_items ORDER BY id",
    ) == [
        (1, 1, "clean", 1, 84.0, 1, None, None),
        (2, 1, "clean", 2, 96.0, 0, None, None),
    ]
    assert _filas(
        connection,
        "SELECT id, session_id, exercise, real_weight_kg, reps, planned_weight_kg,"
        " planned_reps, planned_max_kg, plan_item_id, created_at FROM series"
        " ORDER BY id",
    ) == [
        (1, 1, "clean", 84.0, 5, 84.0, None, None, 1, "2026-10-17T02:40:00"),
        (2, 1, "clean", 96.0, 3, 96.0, None, None, None, "2026-10-17T03:10:00"),
    ]
    for tabla, total in _CONTEOS.items():
        assert connection.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0] == total

    # Todas las marcas +3 h exactas, con cruces de día, mes y año (RF-02).
    assert _filas(
        connection, "SELECT id, started_at, ended_at FROM sessions ORDER BY id"
    ) == _SESIONES_UTC
    assert _filas(
        connection, "SELECT id, weight_kg, height_cm, created_at FROM profile ORDER BY id"
    ) == _PERFIL_UTC
    assert _filas(
        connection,
        "SELECT id, exercise, weight_kg, created_at FROM rm_history ORDER BY id",
    ) == _RM_UTC

    # CL-9: lo copiado en las series viejas queda intacto y los RM siguen ahí.
    assert [s["planned_weight_kg"] for s in db.list_series(connection, 1)] == [84.0, 96.0]
    assert db.get_rm(connection, "clean") == 120.0
    assert db.get_open_session(connection)["id"] == 2  # la sesión abierta sobrevive


def test_migracion_crea_respaldo_v1_con_los_datos_originales(base_v1):
    connection, base = base_v1
    db.init_schema(connection)
    respaldo = db.connect(base.with_name(base.name + ".bak-v1"))
    try:
        assert respaldo.execute("PRAGMA user_version").fetchone()[0] == 1
        columnas = {
            row["name"] for row in respaldo.execute("PRAGMA table_info(series)")
        }
        assert "planned_reps" not in columnas and "planned_max_kg" not in columnas
        # Los datos y las horas originales (sin +3 h) quedan tal cual.
        assert _filas(
            respaldo, "SELECT id, started_at, ended_at FROM sessions ORDER BY id"
        ) == _SESIONES_LOCAL
        assert _filas(
            respaldo,
            "SELECT id, exercise, weight_kg, created_at FROM rm_history ORDER BY id",
        ) == _RM_LOCAL
        assert _filas(
            respaldo,
            "SELECT id, session_id, exercise, real_weight_kg, reps,"
            " planned_weight_kg, plan_item_id, created_at FROM series ORDER BY id",
        ) == _SERIES_LOCAL
        for tabla, total in _CONTEOS.items():
            assert respaldo.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0] == total
    finally:
        respaldo.close()


def test_migracion_segunda_apertura_no_cambia_nada(base_v1):
    connection, base = base_v1
    db.init_schema(connection)
    horas = _todas_las_horas(connection)
    db.init_schema(connection)  # CL-10: reabrir sobre una base ya en v2
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
    assert _todas_las_horas(connection) == horas  # nada de un segundo +3 h
    for tabla, total in _CONTEOS.items():
        assert connection.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0] == total


def test_migracion_no_sobrescribe_un_respaldo_existente(tmp_path):
    base = tmp_path / "boxlog.db"
    respaldo = tmp_path / "boxlog.db.bak-v1"
    respaldo.write_bytes(b"respaldo anterior, no me toques")
    connection = _crear_base_v1(base)
    try:
        db.init_schema(connection)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert respaldo.read_bytes() == b"respaldo anterior, no me toques"
    finally:
        connection.close()


def test_migracion_fallida_se_revierte_y_permite_reintentar(base_v1):
    connection, base = base_v1
    respaldo = base.with_name(base.name + ".bak-v1")
    connection.execute(
        "CREATE TRIGGER fallo_simulado BEFORE UPDATE ON series"
        " WHEN NEW.created_at <> OLD.created_at"
        " BEGIN SELECT RAISE(ABORT, 'fallo simulado'); END"
    )
    horas_originales = _todas_las_horas(connection)

    with pytest.raises(RuntimeError, match="se deshizo por completo"):
        db.init_schema(connection)

    # Rollback total: versión 1, sin columnas nuevas y sin horas cambiadas.
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    assert "reps" not in {
        row["name"] for row in connection.execute("PRAGMA table_info(plan_items)")
    }
    assert "planned_reps" not in {
        row["name"] for row in connection.execute("PRAGMA table_info(series)")
    }
    assert _todas_las_horas(connection) == horas_originales
    assert connection.in_transaction is False  # ROLLBACK ejecutado
    assert respaldo.exists()  # el respaldo queda disponible (RNF-1)

    # Al quitar el trigger, un reintento migra entero.
    connection.execute("DROP TRIGGER fallo_simulado")
    db.init_schema(connection)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
    assert _filas(
        connection, "SELECT id, started_at, ended_at FROM sessions ORDER BY id"
    ) == _SESIONES_UTC


def test_migracion_corre_dentro_de_una_transaccion(base_v1, monkeypatch):
    connection, base = base_v1
    observado: dict[str, bool] = {}
    original = db._shift_marks_to_utc

    def espiar(con, tabla, columnas):
        observado[tabla] = con.in_transaction
        original(con, tabla, columnas)

    monkeypatch.setattr(db, "_shift_marks_to_utc", espiar)
    db.init_schema(connection)
    # Cada conversión de horas ocurre con la transacción abierta (BEGIN IMMEDIATE).
    assert observado == {tabla: True for tabla in ("sessions", "profile", "rm_history", "series")}
    assert connection.in_transaction is False  # todo confirmado con COMMIT


def test_migracion_en_memoria_no_tiene_respaldo():
    connection = db.connect(":memory:")
    connection.executescript(_SCHEMA_V1)
    connection.execute("PRAGMA user_version = 1")
    connection.execute(
        "INSERT INTO sessions (started_at, ended_at) VALUES ('2026-10-16T23:30:00', NULL)"
    )
    connection.commit()
    try:
        db.init_schema(connection)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert _filas(connection, "SELECT started_at, ended_at FROM sessions") == [
            ("2026-10-17T02:30:00", None)
        ]
    finally:
        connection.close()


def test_base_nueva_v0_nace_en_v2_sin_respaldo(tmp_path):
    base = tmp_path / "nueva.db"
    connection = db.connect(base)
    try:
        db.init_schema(connection)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert not base.with_name(base.name + ".bak-v1").exists()  # CL-11
    finally:
        connection.close()


def test_flujo_real_tras_migrar(base_v1):
    connection, base = base_v1
    db.init_schema(connection)
    # La sesión abierta de v1 quedó en UTC y el flujo completo funciona sobre ella.
    assert commands.cmd_hoy(connection, ["clean", "80-85x1"]) == "80-85% × 1 → 96-102 kg"
    assert (
        commands.cmd_log(connection, ["clean", "98x1"])
        == "clean · serie 1: 98 kg × 1 (plan 96-102 kg × 1)"
    )
    fin = commands.cmd_fin(connection, [])
    assert "Duración: " in fin
    assert "plan→real: 96-102→98" in fin
    assert db.get_open_session(connection) is None


# --- get_recent_sessions para /historial (RF-03, spec 003) ---


def _insertar_sesion(connection, session_id, started, ended):
    connection.execute(
        "INSERT INTO sessions (id, started_at, ended_at) VALUES (?, ?, ?)",
        (session_id, started, ended),
    )


def test_get_recent_sessions_abierta_primero_y_cerradas_de_nueva_a_antigua(conn):
    # 7 cerradas (ids 1-7) + una abierta (id 8): salen la abierta y las 5 cerradas más nuevas
    for numero in range(1, 8):
        _insertar_sesion(
            conn, numero, f"2026-10-{numero:02d}T12:00:00", f"2026-10-{numero:02d}T13:00:00"
        )
    _insertar_sesion(conn, 8, "2026-10-20T02:35:00", None)
    sesiones = db.get_recent_sessions(conn)
    assert [s["id"] for s in sesiones] == [8, 7, 6, 5, 4, 3]
    assert sesiones[0]["ended_at"] is None  # la abierta, arriba
    assert all(s["ended_at"] is not None for s in sesiones[1:])


def test_get_recent_sessions_sin_abierta_las_ultimas_cerradas(conn):
    for numero in range(1, 4):
        _insertar_sesion(
            conn, numero, f"2026-10-{numero:02d}T12:00:00", f"2026-10-{numero:02d}T13:00:00"
        )
    assert [s["id"] for s in db.get_recent_sessions(conn)] == [3, 2, 1]


def test_get_recent_sessions_base_vacia(conn):
    assert db.get_recent_sessions(conn) == []


def test_get_recent_sessions_es_solo_lectura(conn):
    for numero in range(1, 4):
        _insertar_sesion(
            conn, numero, f"2026-10-{numero:02d}T12:00:00", f"2026-10-{numero:02d}T13:00:00"
        )
    antes = _filas(conn, "SELECT * FROM sessions ORDER BY id")
    assert db.get_recent_sessions(conn) != []  # algo devuelve
    assert _filas(conn, "SELECT * FROM sessions ORDER BY id") == antes  # nada cambia


# --- solo lectura para el dashboard (T2, spec 004: RF-01, CL-9 a CL-13) ---


def _base_v2(tmp_path, nombre="boxlog.db"):
    """Base v2 real ya cerrada en tmp_path, para abrirla después en solo lectura."""
    base = tmp_path / nombre
    connection = db.connect(base)
    db.init_schema(connection)
    connection.close()
    return base


def _hash(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _base_con_version(tmp_path, version):
    """Archivo con user_version fijado (el 0 = solo creado, sin esquema)."""
    base = tmp_path / f"v{version}.db"
    connection = db.connect(base)
    connection.executescript("CREATE TABLE t (x INTEGER); DROP TABLE t;")
    connection.execute(f"PRAGMA user_version = {version}")
    connection.commit()
    connection.close()
    return base


def test_open_readonly_construye_la_uri_mode_ro_y_query_only(tmp_path, monkeypatch):
    base = _base_v2(tmp_path)
    real_connect = sqlite3.connect
    captura = {}

    def espiar(url, *args, **kwargs):
        captura["url"] = url
        captura["uri"] = kwargs.get("uri")
        return real_connect(url, *args, **kwargs)

    monkeypatch.setattr(db.sqlite3, "connect", espiar)
    ro = db.open_readonly(base)
    try:
        assert captura["url"] == base.resolve().as_uri() + "?mode=ro"  # file:///…?mode=ro
        assert captura["uri"] is True
        assert ro.execute("PRAGMA query_only").fetchone()[0] == 1
    finally:
        ro.close()


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO profile (weight_kg, height_cm, created_at)"
        " VALUES (70, 170, '2026-10-17T12:00:00')",
        "UPDATE sessions SET ended_at = '2026-10-17T13:00:00'",
        "DELETE FROM series",
        "CREATE TABLE nueva (id INTEGER PRIMARY KEY)",
    ],
)
def test_open_readonly_rechaza_cualquier_escritura(tmp_path, sql):
    base = _base_v2(tmp_path)
    ro = db.open_readonly(base)
    try:
        with pytest.raises(sqlite3.OperationalError):
            ro.execute(sql)
    finally:
        ro.close()


def test_lecturas_no_escriben_ni_llaman_a_init_schema(tmp_path, monkeypatch):
    base = _base_v2(tmp_path)
    # Semilla en la base de la que se leerá después.
    semilla = db.connect(base)
    _insertar_sesion(semilla, 1, "2026-10-17T12:00:00", "2026-10-17T13:00:00")
    semilla.commit()
    semilla.close()

    monkeypatch.setattr(
        db, "init_schema", lambda *_: pytest.fail("no debe crear tablas ni migrar")
    )
    antes = _hash(base)
    ro = db.open_readonly(base)
    try:
        assert db.read_user_version(ro) == 2
        assert len(db.read_sessions(ro)) == 1
        assert db.read_series(ro) == []
        assert db.read_rm_history(ro) == []
    finally:
        ro.close()
    assert _hash(base) == antes  # el sha256 del archivo no cambió


def test_open_readonly_base_inexistente_falla_sin_crear_nada(tmp_path):
    base = tmp_path / "noexiste.db"
    with pytest.raises(sqlite3.OperationalError, match="unable to open database file"):
        db.open_readonly(base)
    assert not base.exists()  # CL-10: el archivo no se crea
    anidada = tmp_path / "carpeta" / "futura" / "boxlog.db"
    with pytest.raises(sqlite3.OperationalError):
        db.open_readonly(anidada)
    assert not anidada.parent.exists()  # ni siquiera la carpeta


@pytest.mark.parametrize("version", [0, 1, 2, 3])
def test_read_user_version_devuelve_el_numero_de_la_base(tmp_path, version):
    base = _base_con_version(tmp_path, version)
    ro = db.open_readonly(base)
    try:
        assert db.read_user_version(ro) == version
    finally:
        ro.close()


# --- mensajes fijos de versión (RF-01: CL-9, CL-10, CL-12, CL-13) ---


@pytest.mark.parametrize(
    "version, esperado",
    [
        (2, None),  # v2: genera sin mensaje
        (0, "La base no está inicializada: ejecuta el bot una vez."),  # CL-12
        (1, "La base está en v1: ejecuta el bot una vez para migrarla."),  # CL-9
        (3, "Versión de la base no soportada por este dashboard."),  # CL-13
        (7, "Versión de la base no soportada por este dashboard."),
    ],
)
def test_dashboard_version_error_mensajes_fijos_de_la_spec(version, esperado):
    assert core.dashboard_version_error(version) == esperado


def test_mensajes_fijos_de_base_faltante_y_ocupada():
    assert core.DASH_DB_MISSING == "No hay base: ejecuta el bot una vez para crearla."
    assert core.DASH_DB_LOCKED == (
        "La base está ocupada (el bot escribiendo): inténtalo de nuevo en unos segundos."
    )


# --- with_lock_retry (CL-11: el bot escribiendo a la vez) ---


def test_with_lock_retry_devuelve_al_primer_intento(monkeypatch):
    monkeypatch.setattr(
        db.time, "sleep", lambda _: pytest.fail("sin lock no debe esperar")
    )
    llamadas = []

    def fn():
        llamadas.append(1)
        return "ok"

    assert db.with_lock_retry(fn) == "ok"
    assert llamadas == [1]


def test_with_lock_retry_reintenta_lock_y_devuelve_al_exito(monkeypatch):
    sleeps = []
    monkeypatch.setattr(db.time, "sleep", sleeps.append)
    intentos = []

    def fn():
        intentos.append(1)
        if len(intentos) < 3:
            raise sqlite3.OperationalError("database is locked")
        return 42

    assert db.with_lock_retry(fn, attempts=3, delay=0.05) == 42
    assert intentos == [1, 1, 1]  # dos fallos de lock y éxito en la 3ª
    assert sleeps == [0.05, 0.05]  # espera solo entre intentos


def test_with_lock_retry_bloqueo_persistente_devuelve_el_mensaje(monkeypatch):
    sleeps = []
    monkeypatch.setattr(db.time, "sleep", sleeps.append)

    def fn():
        raise sqlite3.OperationalError("database is locked")

    assert db.with_lock_retry(fn, attempts=3, delay=0.01) == core.DASH_DB_LOCKED
    assert sleeps == [0.01, 0.01]  # 3 intentos, 2 esperas


def test_with_lock_retry_propaga_otros_errores_sin_esperar(monkeypatch):
    monkeypatch.setattr(
        db.time, "sleep", lambda _: pytest.fail("un error que no es lock no espera")
    )

    def fallo_comun():
        raise ValueError("algo raro")

    with pytest.raises(ValueError, match="algo raro"):
        db.with_lock_retry(fallo_comun)

    def fallo_operacional():
        raise sqlite3.OperationalError("no such table: nada")

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        db.with_lock_retry(fallo_operacional)


def test_lock_real_con_exclusive_devuelve_el_mensaje_de_la_spec(tmp_path, monkeypatch):
    base = _base_v2(tmp_path)
    antes = _hash(base)
    sleeps = []
    monkeypatch.setattr(db.time, "sleep", sleeps.append)
    bloqueo = sqlite3.connect(base, timeout=5)
    try:
        bloqueo.execute("BEGIN EXCLUSIVE")  # el bot escribiendo a la vez

        def leer():
            ro = db.open_readonly(base)
            try:
                return db.read_user_version(ro)
            finally:
                ro.close()

        assert db.with_lock_retry(leer, attempts=3, delay=0.01) == core.DASH_DB_LOCKED
        assert len(sleeps) == 2  # reintenta hasta agotar
    finally:
        bloqueo.rollback()
        bloqueo.close()
    assert _hash(base) == antes  # sin generar nada


# --- lecturas: read_sessions, read_series y read_rm_history (RF-03, RF-04) ---


def test_read_sessions_orden_desc_sin_limit_y_con_la_abierta(conn):
    # Ids crecientes con fechas decrecientes: el orden manda por started_at, no por id.
    for numero in range(1, 8):
        dia = 20 - numero
        _insertar_sesion(
            conn, numero, f"2026-10-{dia:02d}T12:00:00", f"2026-10-{dia:02d}T13:00:00"
        )
    _insertar_sesion(conn, 8, "2026-10-20T02:35:00", None)  # abierta, la más nueva
    sesiones = db.read_sessions(conn)
    # Sin LIMIT: las 8 sesiones (get_recent_sessions solo devolvería 6).
    assert [s["id"] for s in sesiones] == [8, 1, 2, 3, 4, 5, 6, 7]
    assert sesiones[0]["ended_at"] is None
    assert all(s["ended_at"] is not None for s in sesiones[1:])


def test_read_sessions_base_vacia(conn):
    assert db.read_sessions(conn) == []


def _insertar_serie(
    connection,
    serie_id,
    session_id,
    exercise,
    real,
    reps,
    planned=None,
    planned_reps=None,
    planned_max=None,
    created="2026-10-17T12:00:00",
):
    connection.execute(
        "INSERT INTO series (id, session_id, exercise, real_weight_kg, reps,"
        " planned_weight_kg, planned_reps, planned_max_kg, plan_item_id, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)",
        (
            serie_id,
            session_id,
            exercise,
            real,
            reps,
            planned,
            planned_reps,
            planned_max,
            created,
        ),
    )


def test_read_series_todas_en_orden_y_con_claves_de_la_base(conn):
    _insertar_sesion(conn, 1, "2026-10-16T12:00:00", "2026-10-16T13:00:00")
    _insertar_sesion(conn, 2, "2026-10-17T12:00:00", None)
    _insertar_serie(conn, 1, 1, "clean", 84.0, 5, planned=80.0, planned_reps=5)
    _insertar_serie(conn, 2, 1, "clean", 96.0, 3, planned=96.0, planned_max=98.0)
    _insertar_serie(conn, 3, 2, "front squat", 100.0, 2)  # sin plan
    series = db.read_series(conn)
    assert [s["id"] for s in series] == [1, 2, 3]  # todas, orden de registro
    assert set(series[0]) == {
        "id",
        "session_id",
        "exercise",
        "real_weight_kg",
        "reps",
        "planned_weight_kg",
        "planned_reps",
        "planned_max_kg",
        "plan_item_id",
        "created_at",
    }
    assert series[2]["planned_weight_kg"] is None  # serie sin plan


def test_read_series_base_vacia(conn):
    assert db.read_series(conn) == []


def test_read_rm_history_orden_de_registro_y_claves(conn):
    for numero, (ejercicio, kilos) in enumerate(
        [("clean", 100.0), ("clean", 102.0), ("front squat", 170.0)], start=1
    ):
        conn.execute(
            "INSERT INTO rm_history (id, exercise, weight_kg, created_at)"
            " VALUES (?, ?, ?, ?)",
            (numero, ejercicio, kilos, f"2026-10-{numero:02d}T12:00:00"),
        )
    filas = db.read_rm_history(conn)
    assert [(r["exercise"], r["weight_kg"]) for r in filas] == [
        ("clean", 100.0),
        ("clean", 102.0),
        ("front squat", 170.0),
    ]
    assert set(filas[0]) == {"id", "exercise", "weight_kg", "created_at"}


def test_read_rm_history_base_vacia(conn):
    assert db.read_rm_history(conn) == []


def test_lecturas_sobre_base_v1_migrada(base_v1):
    connection, _ = base_v1
    db.init_schema(connection)  # migra 1→2 con respaldo
    sesiones = db.read_sessions(connection)
    assert [s["id"] for s in sesiones] == [2, 1]  # started_at DESC tras el +3 h
    assert sesiones[0]["ended_at"] is None  # la abierta de v1 sigue abierta
    series = db.read_series(connection)
    assert [s["id"] for s in series] == [1, 2]
    assert [s["planned_weight_kg"] for s in series] == [84.0, 96.0]
    # Sin plan en rango/reps en v1: los NULL migrados llegan como None (CL-14).
    assert all(s["planned_reps"] is None for s in series)
    assert all(s["planned_max_kg"] is None for s in series)
    rms = db.read_rm_history(connection)
    assert [(r["exercise"], r["weight_kg"]) for r in rms] == [
        ("clean", 120.0),
        ("front squat", 170.0),
    ]


def test_lecturas_reflejan_lo_escrito_por_los_comandos_reales(conn):
    commands.cmd_rm(conn, ["clean", "100"])
    commands.cmd_inicio(conn, [])
    commands.cmd_log(conn, ["clean", "84x5"])
    commands.cmd_fin(conn, [])

    sesiones = db.read_sessions(conn)
    assert len(sesiones) == 1
    assert sesiones[0]["ended_at"] is not None  # cerrada por /fin

    series = db.read_series(conn)
    assert [(s["exercise"], s["real_weight_kg"], s["reps"]) for s in series] == [
        ("clean", 84.0, 5)
    ]
    assert series[0]["session_id"] == sesiones[0]["id"]

    rms = db.read_rm_history(conn)
    assert [(r["exercise"], r["weight_kg"]) for r in rms] == [("clean", 100.0)]
    assert rms[0]["created_at"]  # la marca UTC puesta por /rm
