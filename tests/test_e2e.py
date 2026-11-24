"""Prueba de punta a punta (T12): el ciclo completo pasa por bot.dispatch.

Sin red ni token: dispatch decide y commands escribe en una BD temporal.
"""

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone

import pytest

from boxlog import bot, core, dashboard, db


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


def test_mensaje_suelto_historial_y_cierre_punta_a_punta(conn, monkeypatch):
    """Ciclo v0.3 (T5): registro suelto con plan de rango, /historial y cierre.

    Todo pasa por bot.dispatch (el camino real del handler). Reloj fijado como
    en el e2e de la 002: la base guarda marcas UTC y los mensajes muestran
    hora local (UTC-3, RF-02/CL-12).
    """
    reloj = {"ahora": datetime(2026, 10, 16, 23, 35, tzinfo=timezone.utc)}
    monkeypatch.setattr(core, "utc_now", lambda: reloj["ahora"])
    monkeypatch.setattr(
        db, "_now", lambda: reloj["ahora"].replace(tzinfo=None).isoformat(timespec="seconds")
    )

    def send(command, *args):
        return bot.dispatch(1, 1, command, list(args), conn)

    def suelto(texto):
        # el mismo camino que make_free_text_handler: strip y args de un elemento
        return bot.dispatch(1, 1, None, bot.free_text_args(texto), conn)

    def series():
        return conn.execute(
            "SELECT exercise, real_weight_kg, reps FROM series ORDER BY id"
        ).fetchall()

    assert send("rm", "clean", "100") == "RM de clean guardado: 100 kg"
    assert send("inicio") == "Sesión iniciada a las 20:35"  # hora local (UTC-3)
    assert send("hoy", "clean", "70", "80-85x1") == "70% → 70 kg\n80-85% × 1 → 80-85 kg"
    # /log normal: consume el primer ítem del plan.
    assert send("log", "clean", "66x1") == "clean · serie 1: 66 kg × 1 (plan 70)"
    # Mensajes sueltos: toman el ejercicio de la última serie y copian el plan (RF-02).
    assert suelto("52x3") == "clean · serie 2: 52 kg × 3 (plan 80-85 kg × 1)"
    assert suelto("52,5X3") == "clean · serie 3: 52,5 kg × 3"  # plan agotado; coma decimal
    # /deshacer borra la serie del otro ejercicio y el siguiente suelto usa
    # el ejercicio de la que quedó (CL-7).
    assert send("log", "front squat", "70x3") == "front squat · serie 1: 70 kg × 3"
    assert send("deshacer") == "Borrada: front squat 70x3"
    assert suelto("60x2") == "clean · serie 4: 60 kg × 2"

    # Mensajes que NO registran: ayuda o aviso de uso y la base no cambia.
    antes = [tuple(fila) for fila in series()]
    assert suelto("52x3?") == core.help_text()  # CL-2: caracteres extra
    assert suelto("hola") == core.help_text()  # CL-1: sin forma de registro
    assert suelto("52x0") == core.usage_example("log")  # CL-4: aviso sin guardar
    # Persona ajena ignorada también en el texto suelto (CL-8, RF-08).
    assert bot.dispatch(999, 1, None, bot.free_text_args("52x3"), conn) is None
    assert [tuple(fila) for fila in series()] == antes
    assert len(antes) == 4

    # /historial con la sesión abierta: cabecera con hora local (CL-10, CL-14).
    historial = send("historial")
    assert historial.splitlines()[0] == "16/10 · abierta desde las 20:35"
    assert "clean: 4 series · 9 repeticiones · volumen 499,5 kg · máx 66 kg" in historial
    assert "front squat" not in historial  # la borró /deshacer
    assert "plan→real" not in historial  # CL-14: sin pares plan→real

    # Cierre 45 minutos después y /historial con la sesión cerrada.
    reloj["ahora"] = datetime(2026, 10, 17, 0, 20, tzinfo=timezone.utc)
    fin = send("fin")
    assert fin == (
        "Duración: 45 min\n"
        "clean: 4 series · 9 repeticiones · volumen 499,5 kg · máx 66 kg\n"
        "  plan→real: 70→66, 80-85→52\n"
        "Volumen total: 499,5 kg"
    )
    historial = send("historial")
    assert historial.splitlines()[0] == "16/10 · 45 min"
    assert "clean: 4 series · 9 repeticiones · volumen 499,5 kg · máx 66 kg" in historial
    assert "abierta desde" not in historial
    assert db.get_open_session(conn) is None

    # Estado final en la base: 4 series (sin la borrada) y plan consumido del todo.
    assert [(s["exercise"], s["real_weight_kg"], s["reps"]) for s in series()] == [
        ("clean", 66.0, 1),
        ("clean", 52.0, 3),
        ("clean", 52.5, 3),
        ("clean", 60.0, 2),
    ]
    planes = conn.execute(
        "SELECT weight_kg, range_max_kg, consumed FROM plan_items ORDER BY position"
    ).fetchall()
    assert [(p["weight_kg"], p["range_max_kg"], p["consumed"]) for p in planes] == [
        (70.0, None, 1),
        (80.0, 85.0, 1),
    ]


# --- dashboard local de solo lectura (spec 004, T7) ---

HOSTIL = "</script><script>alert(1)</script>"

# Mismo esquema v1 que tests/test_db.py y tests/test_commands.py (base de la 001).
_ESQUEMA_V1 = """
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


def _payload_del_html(documento: str) -> dict:
    """El bloque de datos JSON del HTML (misma regex que tests/test_dashboard.py)."""
    match = re.search(
        r'<script id="datos" type="application/json">(.*?)</script>',
        documento,
        re.DOTALL,
    )
    assert match, "falta el bloque de datos JSON"
    return json.loads(match.group(1))


def test_dashboard_e2e_sobre_base_construida_con_los_comandos_del_bot(
    tmp_path, monkeypatch, capsys
):
    """004 T7: pipeline completo del dashboard sobre una base escrita por el bot.

    Todo el historial pasa por bot.dispatch con el reloj fijado (patrón 002):
    un RM anterior, una sesión con /hoy de rango, mensaje suelto, /deshacer,
    un ejercicio hostil vía /log y una segunda sesión el día siguiente.
    """
    base = tmp_path / "data" / "boxlog.db"
    salida = tmp_path / "data" / "dashboard.html"
    connection = db.connect(base)
    db.init_schema(connection)
    reloj = {"ahora": datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(core, "utc_now", lambda: reloj["ahora"])
    monkeypatch.setattr(
        db,
        "_now",
        lambda: reloj["ahora"].replace(tzinfo=None).isoformat(timespec="seconds"),
    )

    def send(command, *args):
        return bot.dispatch(1, 1, command, list(args), connection)

    def suelto(texto):
        return bot.dispatch(1, 1, None, bot.free_text_args(texto), connection)

    # RM anterior (15/10): la evolución del dashboard tendrá dos puntos.
    assert send("rm", "clean", "70") == "RM de clean guardado: 70 kg"

    # Día siguiente (16/10): perfil, RM nuevo y sesión completa con rango.
    reloj["ahora"] = datetime(2026, 10, 16, 23, 35, tzinfo=timezone.utc)
    assert send("perfil", "78", "175") == "Perfil guardado: 78 kg · 175 cm"
    # Segundo RM del mismo ejercicio: el mensaje recuerda el anterior.
    assert send("rm", "clean", "80") == "RM de clean guardado: 80 kg (antes 70 kg)"
    assert send("rm", "front squat", "170") == "RM de front squat guardado: 170 kg"
    assert send("inicio") == "Sesión iniciada a las 20:35"
    assert send("hoy", "clean", "100", "80-85x1") == (
        "100% → 80 kg\n80-85% × 1 → 64-68 kg"
    )
    assert send("log", "clean", "76x2") == "clean · serie 1: 76 kg × 2 (plan 80)"
    # Mensaje suelto: toma el ejercicio y el plan de rango (RF-02 de la 003).
    assert suelto("66x1") == "clean · serie 2: 66 kg × 1 (plan 64-68 kg × 1)"
    assert send("log", "front squat", "140x5") == "front squat · serie 1: 140 kg × 5"
    assert send("log", "clean", "90x1") == "clean · serie 3: 90 kg × 1"
    assert send("deshacer") == "Borrada: clean 90x1"
    # Ejercicio hostil insertado vía /log (CL-8).
    assert send("log", HOSTIL, "50x3") == f"{HOSTIL} · serie 1: 50 kg × 3"
    reloj["ahora"] = datetime(2026, 10, 17, 0, 20, tzinfo=timezone.utc)
    fin = send("fin")
    assert fin.splitlines()[0] == "Duración: 45 min"
    assert "  plan→real: 80→76, 64-68→66" in fin
    assert "Volumen total: 1068 kg" in fin

    # Segunda sesión, otro día (17/10).
    reloj["ahora"] = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
    assert send("inicio") == "Sesión iniciada a las 09:00"
    assert send("log", "clean", "100x3") == "clean · serie 1: 100 kg × 3"
    reloj["ahora"] = datetime(2026, 10, 17, 12, 45, tzinfo=timezone.utc)
    assert send("fin").splitlines()[0] == "Duración: 45 min"
    connection.close()

    # Pipeline del dashboard sobre esa misma base (rutas en tmp_path).
    monkeypatch.setattr(dashboard, "DB_PATH", base)
    monkeypatch.setattr(dashboard, "OUTPUT_PATH", salida)
    antes = hashlib.sha256(base.read_bytes()).hexdigest()

    assert dashboard.main() == 0
    assert capsys.readouterr().out.strip() == (
        f"Dashboard generado: {salida.as_posix()} (2 sesiones)."
    )
    assert hashlib.sha256(base.read_bytes()).hexdigest() == antes  # solo lectura

    documento = salida.read_text(encoding="utf-8")
    assert salida.parent == tmp_path / "data"  # el HTML vive bajo data/ del tmp_path
    assert documento.count("<article>") == 2  # una por sesión (RF-04)
    assert '<select class="controles" id="selector-carga">' in documento
    escapado = "&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;"
    assert f'<option value="{escapado}">' in documento
    assert f"<li>{escapado}: 1 serie" in documento
    assert HOSTIL not in documento  # jamás en crudo (CL-8)
    assert "\\u003c/script>" in documento  # capa JSON
    assert "plan→real: 80→76, 64-68→66" in documento

    assert _payload_del_html(documento) == {
        "generated": "17/10/2026 09:45",
        "streak": {"days": 2, "missing_today": False, "last": "17/10"},
        "month_sessions": 2,
        "rm_current": [
            {"exercise": "clean", "kg": 80},
            {"exercise": "front squat", "kg": 170},
        ],
        "rm_evolution": [
            {"exercise": "clean", "points": [["15/10", 70], ["16/10", 80]]},
            {"exercise": "front squat", "points": [["16/10", 170]]},
        ],
        "percent_table": {
            "exercises": ["clean", "front squat"],
            "steps": [50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100],
            "values": [
                [40, 85],
                [44, 93.5],
                [48, 102],
                [52, 110.5],
                [56, 119],
                [60, 127.5],
                [64, 136],
                [68, 144.5],
                [72, 153],
                [76, 161.5],
                [80, 170],
            ],
        },
        "sessions": [
            {
                "date": "17/10",
                "open": False,
                "opened_at": None,
                "duration": "45 min",
                "volume": "300 kg",
                "lines": [
                    "clean: 1 serie · 3 repeticiones · volumen 300 kg · máx 100 kg"
                ],
                "pairs": [],
            },
            {
                "date": "16/10",
                "open": False,
                "opened_at": None,
                "duration": "45 min",
                "volume": "1068 kg",
                "lines": [
                    "clean: 2 series · 3 repeticiones · volumen 218 kg · máx 76 kg",
                    "front squat: 1 serie · 5 repeticiones · volumen 700 kg · máx 140 kg",
                    f"{HOSTIL}: 1 serie · 3 repeticiones · volumen 150 kg · máx 50 kg",
                ],
                "pairs": ["80→76", "64-68→66"],
            },
        ],
        "max_load": {
            HOSTIL: [["16/10", 50]],
            "clean": [["16/10", 76], ["17/10", 100]],
            "front squat": [["16/10", 140]],
        },
    }

    # Regenerar dos veces con la misma entrada da archivos idénticos.
    primera = salida.read_bytes()
    assert dashboard.main() == 0
    assert capsys.readouterr().out.strip() == (
        f"Dashboard generado: {salida.as_posix()} (2 sesiones)."
    )
    assert salida.read_bytes() == primera
    assert hashlib.sha256(base.read_bytes()).hexdigest() == antes


def test_dashboard_e2e_sobre_base_migrada_de_v1(tmp_path, monkeypatch, capsys):
    """004 T7: base v1 migrada por el bot; pares simples y series sin plan (CL-14).

    La migración 1→2 es la real de la 002 (init_schema con respaldo): las
    columnas de plan llegan NULL, así que el par sale en formato simple o no
    sale; el dashboard no migra nada, solo lee la v2 ya migrada.
    """
    base = tmp_path / "data" / "boxlog.db"
    salida = tmp_path / "data" / "dashboard.html"
    connection = db.connect(base)
    connection.executescript(_ESQUEMA_V1)
    connection.execute("PRAGMA user_version = 1")
    connection.execute(
        "INSERT INTO sessions (id, started_at, ended_at) VALUES (1, ?, ?)",
        ("2026-10-16T20:00:00", "2026-10-16T21:00:00"),  # marcas locales de la 001
    )
    connection.execute(
        "INSERT INTO series (id, session_id, exercise, real_weight_kg, reps,"
        " planned_weight_kg, plan_item_id, created_at)"
        " VALUES (1, 1, 'clean', 84.0, 5, 84.0, NULL, '2026-10-16T20:10:00')"
    )
    connection.execute(
        "INSERT INTO series (id, session_id, exercise, real_weight_kg, reps,"
        " planned_weight_kg, plan_item_id, created_at)"
        " VALUES (2, 1, 'clean', 90.0, 3, NULL, NULL, '2026-10-16T20:20:00')"
    )
    connection.execute(
        "INSERT INTO rm_history (id, exercise, weight_kg, created_at)"
        " VALUES (1, 'clean', 100.0, '2026-10-16T12:00:00')"
    )
    connection.commit()
    connection.close()

    # El bot arranca y migra v1 → v2 con respaldo (camino real de la 002).
    connection = db.connect(base)
    db.init_schema(connection)
    connection.close()
    assert base.with_name("boxlog.db.bak-v1").exists()

    monkeypatch.setattr(dashboard, "DB_PATH", base)
    monkeypatch.setattr(dashboard, "OUTPUT_PATH", salida)
    monkeypatch.setattr(
        core, "utc_now", lambda: datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc)
    )
    antes = hashlib.sha256(base.read_bytes()).hexdigest()

    assert dashboard.main() == 0
    assert capsys.readouterr().out.strip() == (
        f"Dashboard generado: {salida.as_posix()} (1 sesiones)."
    )
    assert hashlib.sha256(base.read_bytes()).hexdigest() == antes  # solo lectura

    payload = _payload_del_html(salida.read_text(encoding="utf-8"))
    assert payload["generated"] == "16/10/2026 21:00"
    assert payload["streak"] == {"days": 1, "missing_today": False, "last": "16/10"}
    assert payload["month_sessions"] == 1
    assert payload["rm_current"] == [{"exercise": "clean", "kg": 100}]
    assert payload["rm_evolution"] == [
        {"exercise": "clean", "points": [["16/10", 100]]}
    ]
    assert payload["sessions"] == [
        {
            "date": "16/10",
            "open": False,
            "opened_at": None,
            "duration": "1 h 0 min",
            "volume": "690 kg",
            "lines": ["clean: 2 series · 8 repeticiones · volumen 690 kg · máx 90 kg"],
            "pairs": ["84→84"],  # sin rango en v1 y la serie NULL no aporta (CL-14)
        }
    ]
    assert payload["max_load"] == {"clean": [["16/10", 90]]}
    assert "plan→real: 84→84" in salida.read_text(encoding="utf-8")


def test_dashboard_e2e_con_el_bot_escribiendo_no_toca_el_html(
    tmp_path, monkeypatch, capsys
):
    """004 T7/CL-11: base ocupada por el bot → mensaje fijo y el HTML intacto."""
    base = tmp_path / "data" / "boxlog.db"
    salida = tmp_path / "data" / "dashboard.html"
    connection = db.connect(base)
    db.init_schema(connection)
    reloj = {"ahora": datetime(2026, 10, 16, 23, 35, tzinfo=timezone.utc)}
    monkeypatch.setattr(core, "utc_now", lambda: reloj["ahora"])
    monkeypatch.setattr(
        db,
        "_now",
        lambda: reloj["ahora"].replace(tzinfo=None).isoformat(timespec="seconds"),
    )
    bot.dispatch(1, 1, "rm", ["clean", "80"], connection)
    bot.dispatch(1, 1, "inicio", [], connection)
    bot.dispatch(1, 1, "log", ["clean", "76x2"], connection)
    reloj["ahora"] = datetime(2026, 10, 17, 0, 20, tzinfo=timezone.utc)
    bot.dispatch(1, 1, "fin", [], connection)
    connection.close()

    monkeypatch.setattr(dashboard, "DB_PATH", base)
    monkeypatch.setattr(dashboard, "OUTPUT_PATH", salida)
    assert dashboard.main() == 0  # HTML previo, con la base libre
    capsys.readouterr()
    previo = salida.read_bytes()

    monkeypatch.setattr(db, "_LOCK_TIMEOUT", 0.01)
    monkeypatch.setattr(db.time, "sleep", lambda _segundos: None)
    bloqueo = sqlite3.connect(base, timeout=5)
    try:
        bloqueo.execute("BEGIN EXCLUSIVE")  # el bot escribiendo a la vez
        assert dashboard.main() == 1
        assert capsys.readouterr().out.strip() == core.DASH_DB_LOCKED
        assert salida.read_bytes() == previo  # el HTML previo, byte a byte
    finally:
        bloqueo.rollback()
        bloqueo.close()
    assert not salida.with_name(salida.name + ".tmp").exists()
