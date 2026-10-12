"""Prueba de punta a punta (T12): el ciclo completo pasa por bot.dispatch.

Sin red ni token: dispatch decide y commands escribe en una BD temporal.
"""

import pytest

from boxlog import bot, db


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
