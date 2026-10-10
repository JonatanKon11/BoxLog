"""Tests de db: esquema, perfil y RM (RF-01, RF-02, RNF-3). Siempre con BD temporal."""

import sqlite3

import pytest

from boxlog import db


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
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
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
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1  # versión intacta


def test_init_schema_fija_user_version_en_1(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1


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
