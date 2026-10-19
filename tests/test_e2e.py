"""Prueba de punta a punta (T12): el ciclo completo pasa por bot.dispatch.

Sin red ni token: dispatch decide y commands escribe en una BD temporal.
"""

from datetime import datetime, timezone

import pytest

from boxlog import bot, core, db


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "boxlog.db")
    db.init_schema(connection)
    yield connection
    connection.close()


def _ciclo(user_id, owner_id, connection) -> dict[str, str | None]:
    """Secuencia completa: perfil, RM, sesión, plan, series, deshacer y cierre."""

    def send(command, *args):
        return bot.dispatch(user_id, owner_id, command, list(args), connection)

    return {
        "perfil": send("perfil", "78", "175"),
        "rm_clean": send("rm", "clean", "120"),
        "rm_front": send("rm", "front", "squat", "170"),
        "inicio": send("inicio"),
        "hoy": send("hoy", "clean", "70", "80", "85"),
        "log1": send("log", "clean", "84x5"),
        "log2": send("log", "clean", "95x3"),
        "deshacer": send("deshacer"),
        "log3": send("log", "clean", "96x3"),
        "log4": send("log", "front", "squat", "140x5"),
        "fin": send("fin"),
        "rms": send("rms"),
    }


def test_ciclo_completo_punta_a_punta(conn):
    textos = _ciclo(1, 1, conn)

    assert textos["perfil"] == "Perfil guardado: 78 kg · 175 cm"
    assert textos["rm_clean"] == "RM de clean guardado: 120 kg"
    assert textos["rm_front"] == "RM de front squat guardado: 170 kg"
    assert textos["inicio"].startswith("Sesión iniciada a ")
    assert textos["hoy"] == "70% → 84 kg\n80% → 96 kg\n85% → 102 kg"
    # El plan avanza en orden y el real libre no lo toca.
    assert textos["log1"] == "clean · serie 1: 84 kg × 5 (plan 84)"
    assert textos["log2"] == "clean · serie 2: 95 kg × 3 (plan 96)"
    # /deshacer suelta el ítem 96 y la reanudación lo reutiliza.
    assert textos["deshacer"] == "Borrada: clean 95x3"
    assert textos["log3"] == "clean · serie 2: 96 kg × 3 (plan 96)"
    # front squat sin /hoy: serie sin plan (CL-3).
    assert textos["log4"] == "front squat · serie 1: 140 kg × 5"

    fin = textos["fin"]
    assert "Duración: " in fin
    assert "clean: 2 series · 8 repeticiones · volumen 708 kg · máx 96 kg" in fin
    assert "plan→real: 84→84, 96→96" in fin
    assert "front squat: 1 serie · 5 repeticiones · volumen 700 kg · máx 140 kg" in fin
    assert "Volumen total: 1408 kg" in fin
    assert textos["rms"] == "RM vigentes:\nclean: 120 kg\nfront squat: 170 kg"

    # Estado final en la base: sesión cerrada, series y plan como manda la spec.
    assert db.get_open_session(conn) is None
    series = conn.execute(
        "SELECT exercise, real_weight_kg, reps, planned_weight_kg FROM series ORDER BY id"
    ).fetchall()
    assert [
        (s["exercise"], s["real_weight_kg"], s["reps"], s["planned_weight_kg"])
        for s in series
    ] == [
        ("clean", 84.0, 5, 84.0),
        ("clean", 96.0, 3, 96.0),
        ("front squat", 140.0, 5, None),
    ]
    planes = conn.execute(
        "SELECT weight_kg, consumed FROM plan_items ORDER BY position"
    ).fetchall()
    assert [(p["weight_kg"], p["consumed"]) for p in planes] == [
        (84.0, 1),
        (96.0, 1),
        (102.0, 0),
    ]


def test_estado_sobrevive_a_reiniciar(tmp_path):
    base = tmp_path / "boxlog.db"
    connection = db.connect(base)
    db.init_schema(connection)
    bot.dispatch(1, 1, "rm", ["clean", "120"], connection)
    bot.dispatch(1, 1, "inicio", [], connection)
    bot.dispatch(1, 1, "hoy", ["clean", "80"], connection)  # plan 96 kg
    assert (
        bot.dispatch(1, 1, "log", ["clean", "96x5"], connection)
        == "clean · serie 1: 96 kg × 5 (plan 96)"
    )
    connection.close()  # simulacro de reinicio del proceso

    reopened = db.connect(base)
    db.init_schema(reopened)
    try:
        abierta = db.get_open_session(reopened)
        assert abierta is not None  # la sesión sigue abierta
        assert db.count_series(reopened, abierta["id"], "clean") == 1  # la serie sobrevive
        texto = bot.dispatch(1, 1, "inicio", [], reopened)
        assert texto.startswith("Sesión abierta desde")
        # Se puede seguir: la numeración continúa y el plan ya consumido no reaparece.
        texto = bot.dispatch(1, 1, "log", ["clean", "100x3"], reopened)
        assert texto == "clean · serie 2: 100 kg × 3"
    finally:
        reopened.close()


def test_secuencia_como_ajeno_no_deja_nada_en_la_base(conn):
    textos = _ciclo(999, 1, conn)

    assert all(texto is None for texto in textos.values())  # silencio total
    for tabla in ("profile", "rm_history", "sessions", "plan_items", "series"):
        assert conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0] == 0, tabla


def test_ciclo_con_rango_reps_y_hora_local_punta_a_punta(conn, monkeypatch):
    """Ciclo v0.2 (T7): plan mixto con "80-85x1", reales distintos del plan y hora local.

    El reloj queda fijado en 2026-10-16T23:35Z: la base guarda esa marca UTC y
    /inicio debe mostrar las 20:35, la hora local (UTC-3, RF-02/CL-12).
    """
    reloj = {"ahora": datetime(2026, 10, 16, 23, 35, tzinfo=timezone.utc)}
    monkeypatch.setattr(core, "utc_now", lambda: reloj["ahora"])
    monkeypatch.setattr(
        db, "_now", lambda: reloj["ahora"].replace(tzinfo=None).isoformat(timespec="seconds")
    )

    def send(command, *args):
        return bot.dispatch(1, 1, command, list(args), conn)

    assert send("perfil", "78", "175") == "Perfil guardado: 78 kg · 175 cm"
    assert send("rm", "clean", "80") == "RM de clean guardado: 80 kg"
    # La marca guardada es 23:35 UTC; el mensaje muestra la hora local.
    assert send("inicio") == "Sesión iniciada a las 20:35"
    assert (
        send("hoy", "clean", "70", "65x3", "80-85", "80-85x1")
        == "70% → 56 kg\n65% × 3 → 52 kg\n80-85% → 64-68 kg\n80-85% × 1 → 64-68 kg"
    )
    # Reales (y reps) distintos del plan: el plan avanza igual, sin avisos (RF-04).
    assert send("log", "clean", "57x4") == "clean · serie 1: 57 kg × 4 (plan 56)"
    assert send("log", "clean", "55x2") == "clean · serie 2: 55 kg × 2 (plan 52 kg × 3)"
    assert send("log", "clean", "67x1") == "clean · serie 3: 67 kg × 1 (plan 64-68)"
    assert send("log", "clean", "66x1") == "clean · serie 4: 66 kg × 1 (plan 64-68 kg × 1)"
    # /deshacer libera el ítem con rango y reps, que se reutiliza (RF-07).
    assert send("deshacer") == "Borrada: clean 66x1"
    assert send("log", "clean", "66x2") == "clean · serie 4: 66 kg × 2 (plan 64-68 kg × 1)"

    reloj["ahora"] = datetime(2026, 10, 17, 0, 20, tzinfo=timezone.utc)  # 45 min después
    fin = send("fin")
    assert fin == (
        "Duración: 45 min\n"
        "clean: 4 series · 9 repeticiones · volumen 537 kg · máx 67 kg\n"
        "  plan→real: 56→57, 52→55, 64-68→67, 64-68→66\n"
        "Volumen total: 537 kg"
    )
    assert "64-68→66" in fin  # el par del rango con reps (RF-05, A-1)

    # Estado final en la base: el plan quedó copiado en cada serie (A-3).
    series = conn.execute(
        "SELECT real_weight_kg, reps, planned_weight_kg, planned_reps, planned_max_kg"
        " FROM series ORDER BY id"
    ).fetchall()
    assert [
        (
            s["real_weight_kg"],
            s["reps"],
            s["planned_weight_kg"],
            s["planned_reps"],
            s["planned_max_kg"],
        )
        for s in series
    ] == [
        (57.0, 4, 56.0, None, None),
        (55.0, 2, 52.0, 3, None),
        (67.0, 1, 64.0, None, 68.0),
        (66.0, 2, 64.0, 1, 68.0),
    ]
    planes = conn.execute(
        "SELECT weight_kg, reps, range_max_kg, consumed FROM plan_items ORDER BY position"
    ).fetchall()
    assert [(p["weight_kg"], p["reps"], p["range_max_kg"], p["consumed"]) for p in planes] == [
        (56.0, None, None, 1),
        (52.0, 3, None, 1),
        (64.0, None, 68.0, 1),
        (64.0, 1, 68.0, 1),
    ]
