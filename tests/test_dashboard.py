"""Tests del dashboard local: payload, CLI, render y escapado (spec 004, T3)."""

import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import boxlog.dashboard as dashboard
from boxlog import commands, core, db

# Reloj fijado (patrón 002): 00:04 UTC del 17/10 es 21:04 local del 16/10.
RELOJ = datetime(2026, 10, 17, 0, 4, tzinfo=timezone.utc)
HOY = date(2026, 10, 16)

# Sesiones como las devuelve db.read_sessions: ordenadas por started_at
# descendente; la primera está abierta y la última empezó a las 01:30 UTC,
# que es 22:30 del 15/10 en local (CL-6).
SESIONES = [
    {"id": 1, "started_at": "2026-10-16T23:35:00", "ended_at": None},
    {"id": 2, "started_at": "2026-10-16T21:00:00", "ended_at": "2026-10-16T21:45:00"},
    {"id": 3, "started_at": "2026-10-16T01:30:00", "ended_at": "2026-10-16T02:30:00"},
]

SESIONES_PAYLOAD = [
    {
        "date": "16/10",
        "open": True,
        "opened_at": "20:35",
        "duration": None,
        "volume": None,
        "lines": [],
        "pairs": [],
    },
    {
        "date": "16/10",
        "open": False,
        "opened_at": None,
        "duration": "45 min",
        "volume": None,
        "lines": [],
        "pairs": [],
    },
    {
        "date": "15/10",
        "open": False,
        "opened_at": None,
        "duration": "1 h 0 min",
        "volume": None,
        "lines": [],
        "pairs": [],
    },
]

PAYLOAD_ESPERADO = {
    "generated": "16/10/2026 21:04",
    "streak": {"days": 2, "missing_today": False, "last": "16/10"},
    "month_sessions": 3,
    "sessions": SESIONES_PAYLOAD,
}

# Nombre hostil de la spec (CL-8) y sus compañeros de lista.
HOSTIL = "</script><script>alert(1)</script>"


# --- helpers de los tests ---


@pytest.fixture
def rutas(tmp_path, monkeypatch):
    """Rutas de la CLI inyectadas en tmp_path: nada toca data/ del proyecto."""
    base = tmp_path / "data" / "boxlog.db"
    salida = tmp_path / "data" / "dashboard.html"
    monkeypatch.setattr(dashboard, "DB_PATH", base)
    monkeypatch.setattr(dashboard, "OUTPUT_PATH", salida)
    return base, salida


def _crear_v2(base, sesiones=(), series=()):
    """Base v2 real creada con init_schema, con sesiones y series sembradas."""
    connection = db.connect(base)
    db.init_schema(connection)
    for fila in sesiones:
        connection.execute(
            "INSERT INTO sessions (id, started_at, ended_at) VALUES (?, ?, ?)",
            (fila["id"], fila["started_at"], fila["ended_at"]),
        )
    for serie in series:
        connection.execute(
            "INSERT INTO series (id, session_id, exercise, real_weight_kg, reps,"
            " planned_weight_kg, planned_reps, planned_max_kg, plan_item_id,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)",
            (
                serie["id"],
                serie["session_id"],
                serie["exercise"],
                serie["real_weight_kg"],
                serie["reps"],
                serie.get("planned_weight_kg"),
                serie.get("planned_reps"),
                serie.get("planned_max_kg"),
                serie.get("created_at", "2026-10-16T18:00:00"),
            ),
        )
    connection.commit()
    connection.close()


def _crear_con_version(base, version):
    """Archivo con user_version fijado: el corte es anterior a leer tablas."""
    base.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(base)
    connection.executescript("CREATE TABLE t (x INTEGER); DROP TABLE t;")
    connection.execute(f"PRAGMA user_version = {version}")
    connection.commit()
    connection.close()


def _payload_del_html(documento: str) -> dict:
    """Extrae el bloque de datos con regex (el \\u003c impide cerrarlo antes)."""
    match = re.search(
        r'<script id="datos" type="application/json">(.*?)</script>',
        documento,
        re.DOTALL,
    )
    assert match, "falta el bloque de datos JSON"
    return json.loads(match.group(1))


# --- payload en core (RF-01, RF-02, plan §5) ---


def test_mensajes_fijos_del_dashboard_viven_en_core():
    assert core.DASH_GENERATED == "Dashboard generado: {ruta} ({n} sesiones)."
    assert core.DASH_NO_RM == "Aún no hay RM. Guarda uno con /rm <ejercicio> <kg>"


def test_build_dashboard_payload_campos_base():
    payload = core.build_dashboard_payload(SESIONES, [], RELOJ, HOY)
    assert payload == PAYLOAD_ESPERADO


def test_build_dashboard_payload_base_vacia():
    payload = core.build_dashboard_payload([], [], RELOJ, HOY)
    assert payload == {
        "generated": "16/10/2026 21:04",
        "streak": {"days": 0, "missing_today": False, "last": None},
        "month_sessions": 0,
        "sessions": [],
    }


def test_build_dashboard_payload_usa_today_inyectado():
    # Sesión del 16/10 y "hoy" = 17/10: racha viva con aviso (CL-5).
    payload = core.build_dashboard_payload(
        [SESIONES[0]], [], RELOJ, date(2026, 10, 17)
    )
    assert payload["streak"] == {"days": 1, "missing_today": True, "last": "16/10"}
    assert payload["month_sessions"] == 1


def test_build_dashboard_payload_no_consulta_el_reloj(monkeypatch):
    monkeypatch.setattr(core, "utc_now", lambda: pytest.fail("no debe usar el reloj"))
    core.build_dashboard_payload([], [], RELOJ, HOY)


# --- CLI: éxito, payload incrustado y estados vacíos (RF-01, CL-1) ---


def test_main_genera_html_y_mensaje_con_el_numero_de_sesiones(
    rutas, monkeypatch, capsys
):
    base, salida = rutas
    _crear_v2(base, SESIONES)
    monkeypatch.setattr(core, "utc_now", lambda: RELOJ)
    salida.write_text("<html>previo</html>", encoding="utf-8")  # CL-16: regenera

    assert dashboard.main() == 0
    documento = salida.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in documento
    assert "<html>previo</html>" not in documento  # se sobrescribe completo
    assert capsys.readouterr().out.strip() == (
        f"Dashboard generado: {salida.as_posix()} (3 sesiones)."
    )


def test_el_html_trae_el_payload_completo_en_json(rutas, monkeypatch, capsys):
    base, salida = rutas
    _crear_v2(base, SESIONES)
    monkeypatch.setattr(core, "utc_now", lambda: RELOJ)

    assert dashboard.main() == 0
    payload = _payload_del_html(salida.read_text(encoding="utf-8"))
    assert payload == PAYLOAD_ESPERADO


def test_base_vacia_genera_html_con_estados_vacios_y_racha_cero(
    rutas, monkeypatch, capsys
):
    base, salida = rutas
    _crear_v2(base)  # sin sesiones ni RM (CL-1)
    monkeypatch.setattr(core, "utc_now", lambda: RELOJ)

    assert dashboard.main() == 0
    documento = salida.read_text(encoding="utf-8")
    assert core.HISTORIAL_EMPTY in documento
    assert "Aún no hay RM. Guarda uno con /rm &lt;ejercicio&gt; &lt;kg&gt;" in documento
    assert "🔥 0" in documento
    assert "Sesiones del mes: 0" in documento
    assert "<article>" not in documento  # sin sesiones no hay artículos (T4)
    payload = _payload_del_html(documento)
    assert payload["streak"] == {"days": 0, "missing_today": False, "last": None}
    assert payload["sessions"] == []
    assert capsys.readouterr().out.strip().endswith("(0 sesiones).")


def test_html_estructura_minima_sin_recursos_externos(rutas, monkeypatch, capsys):
    base, salida = rutas
    _crear_v2(base, SESIONES)
    monkeypatch.setattr(core, "utc_now", lambda: RELOJ)

    assert dashboard.main() == 0
    documento = salida.read_text(encoding="utf-8")
    assert documento.lstrip().startswith("<!DOCTYPE html>")
    assert '<html lang="es">' in documento
    assert 'name="viewport"' in documento
    assert "@media print" in documento
    assert '<section id="rm">' in documento
    assert '<section id="historial">' in documento
    assert '<section id="carga">' in documento
    assert '<script id="datos" type="application/json">' in documento
    assert 'JSON.parse(document.getElementById("datos").textContent)' in documento
    assert "🔥 2" in documento  # cabecera con la racha (RF-02)
    assert "http://" not in documento
    assert "<script src=" not in documento
    assert "fetch(" not in documento


# --- mensajes fijos de error, sin tocar el HTML (CL-9, CL-10, CL-12, CL-13) ---


@pytest.mark.parametrize(
    "caso, mensaje",
    [
        ("faltante", "No hay base: ejecuta el bot una vez para crearla."),
        ("v0", "La base no está inicializada: ejecuta el bot una vez."),
        ("v1", "La base está en v1: ejecuta el bot una vez para migrarla."),
        ("v3", "Versión de la base no soportada por este dashboard."),
    ],
)
def test_errores_fijos_dejan_el_html_previo_intacto(
    rutas, monkeypatch, capsys, caso, mensaje
):
    base, salida = rutas
    if caso != "faltante":
        _crear_con_version(base, int(caso[1]))
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text("<html>previo</html>", encoding="utf-8")

    assert dashboard.main() == 1
    assert capsys.readouterr().out.strip() == mensaje
    assert salida.read_text(encoding="utf-8") == "<html>previo</html>"


@pytest.mark.parametrize(
    "caso, mensaje",
    [
        ("faltante", "No hay base: ejecuta el bot una vez para crearla."),
        ("v0", "La base no está inicializada: ejecuta el bot una vez."),
        ("v1", "La base está en v1: ejecuta el bot una vez para migrarla."),
        ("v3", "Versión de la base no soportada por este dashboard."),
    ],
)
def test_errores_fijos_no_crean_el_html(rutas, monkeypatch, capsys, caso, mensaje):
    base, salida = rutas
    if caso != "faltante":
        _crear_con_version(base, int(caso[1]))

    assert dashboard.main() == 1
    assert capsys.readouterr().out.strip() == mensaje
    assert not salida.exists()
    assert not salida.with_name(salida.name + ".tmp").exists()


def test_version_v1_no_se_migra_nada(rutas, monkeypatch, capsys):
    base, salida = rutas
    _crear_con_version(base, 1)
    antes = hashlib.sha256(base.read_bytes()).hexdigest()

    assert dashboard.main() == 1
    assert hashlib.sha256(base.read_bytes()).hexdigest() == antes  # solo lectura
    assert not salida.exists()


def test_base_bloqueada_mensaje_sin_tocar_el_html_previo(
    rutas, monkeypatch, capsys
):
    base, salida = rutas
    _crear_v2(base, SESIONES)
    salida.write_text("<html>previo</html>", encoding="utf-8")
    sleeps = []
    monkeypatch.setattr(db, "_LOCK_TIMEOUT", 0.01)
    monkeypatch.setattr(db.time, "sleep", sleeps.append)
    bloqueo = sqlite3.connect(base, timeout=5)
    try:
        bloqueo.execute("BEGIN EXCLUSIVE")  # el bot escribiendo a la vez
        assert dashboard.main() == 1
        assert capsys.readouterr().out.strip() == core.DASH_DB_LOCKED
        assert salida.read_text(encoding="utf-8") == "<html>previo</html>"
        assert len(sleeps) == 2  # reintenta hasta agotar (CL-11)
    finally:
        bloqueo.rollback()
        bloqueo.close()
    assert not salida.with_name(salida.name + ".tmp").exists()


def test_base_bloqueada_no_crea_el_html(rutas, monkeypatch, capsys):
    base, salida = rutas
    _crear_v2(base, SESIONES)
    monkeypatch.setattr(db, "_LOCK_TIMEOUT", 0.01)
    monkeypatch.setattr(db.time, "sleep", lambda _segundos: None)
    bloqueo = sqlite3.connect(base, timeout=5)
    try:
        bloqueo.execute("BEGIN EXCLUSIVE")
        assert dashboard.main() == 1
        assert capsys.readouterr().out.strip() == core.DASH_DB_LOCKED
        assert not salida.exists()
    finally:
        bloqueo.rollback()
        bloqueo.close()


# --- escapado en dos capas (RF-06, CL-8) ---


def test_json_seguro_neutraliza_los_mayores_que():
    texto = dashboard._json_seguro({"exercise": HOSTIL})
    assert "\\u003c/script>" in texto
    assert "</script>" not in texto
    assert "<" not in texto
    assert json.loads(texto) == {"exercise": HOSTIL}  # el JSON sigue válido


def test_json_seguro_conserva_el_espanol_y_los_emojis():
    texto = dashboard._json_seguro({"generated": "Generado el… ñ 🔥"})
    assert "ñ 🔥" in texto  # ensure_ascii=False (RF-06)


def test_esc_convierte_entidades_en_texto_y_atributos():
    assert dashboard._esc(HOSTIL) == (
        "&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;"
    )
    assert dashboard._esc('<img src=x onerror=alert(1)>') == (
        "&lt;img src=x onerror=alert(1)&gt;"
    )
    assert dashboard._esc('comillas " y --') == "comillas &quot; y --"


def test_texto_hostil_escapado_en_las_dos_capas_del_html():
    documento = dashboard.render_dashboard(dict(PAYLOAD_ESPERADO, generated=HOSTIL))
    # Capa JSON: sin "<" literal, con \u003c.
    assert "\\u003c/script>\\u003cscript>alert(1)" in documento
    # Capa visible: entidades.
    assert "&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in documento


# --- privacidad y claridad del módulo (RNF-2, RNF-5) ---


def test_token_falso_del_entorno_no_aparece_en_el_html(rutas, monkeypatch, capsys):
    base, salida = rutas
    _crear_v2(base, SESIONES)
    monkeypatch.setenv("TELEGRAM_TOKEN", "123456:ABC-falso-token")

    assert dashboard.main() == 0
    documento = salida.read_text(encoding="utf-8")
    assert "123456:ABC-falso-token" not in documento
    assert "TELEGRAM_TOKEN" not in documento


def test_modulo_sin_bot_dotenv_ni_variables_de_entorno():
    fuente = Path(dashboard.__file__).read_text(encoding="utf-8").lower()
    assert "boxlog.bot" not in fuente
    assert "dotenv" not in fuente
    assert "getenv" not in fuente
    assert "environ" not in fuente
    assert "telegram" not in fuente


def test_rutas_por_defecto_bajo_data_gitignoreado():
    assert dashboard.DB_PATH == Path("data") / "boxlog.db"
    assert dashboard.OUTPUT_PATH == Path("data") / "dashboard.html"
    gitignore = Path(__file__).resolve().parents[1] / ".gitignore"
    lineas = [
        linea.strip()
        for linea in gitignore.read_text(encoding="utf-8").splitlines()
    ]
    assert "data/" in lineas


# --- escritura atómica (CL-16) ---


def test_fallo_en_el_render_no_toca_el_html_previo(rutas, monkeypatch):
    base, salida = rutas
    _crear_v2(base, SESIONES)
    salida.write_text("<html>previo</html>", encoding="utf-8")

    def render_fallido(_payload):
        raise RuntimeError("render roto")

    monkeypatch.setattr(dashboard, "render_dashboard", render_fallido)
    with pytest.raises(RuntimeError, match="render roto"):
        dashboard.main()
    assert salida.read_text(encoding="utf-8") == "<html>previo</html>"
    assert not salida.with_name(salida.name + ".tmp").exists()


def test_fallo_en_el_reemplazo_conserva_el_html_previo(rutas, monkeypatch):
    base, salida = rutas
    _crear_v2(base, SESIONES)
    salida.write_text("<html>previo</html>", encoding="utf-8")

    def reemplazo_fallido(_origen, _destino):
        raise OSError("disco lleno")

    monkeypatch.setattr(dashboard.os, "replace", reemplazo_fallido)
    with pytest.raises(OSError, match="disco lleno"):
        dashboard.main()
    assert salida.read_text(encoding="utf-8") == "<html>previo</html>"
    assert not salida.with_name(salida.name + ".tmp").exists()  # sin temporal


# --- historial completo en el payload y en el HTML (T4: RF-04, RF-05) ---


# Sesión cerrada del 16/10 21:00→22:11 UTC (1 h 11 min en local) con dos
# ejercicios: clean con par simple, par con rango y series sin plan; front
# squat con par simple y una serie sin plan (volumen con coma decimal).
SESION_CERRADA = {
    "id": 1,
    "started_at": "2026-10-16T21:00:00",
    "ended_at": "2026-10-16T22:11:00",
}

SERIES_S1 = [
    {
        "id": 1,
        "session_id": 1,
        "exercise": "clean",
        "real_weight_kg": 66.0,
        "reps": 3,
        "planned_weight_kg": 70.0,
        "planned_reps": 3,
    },
    {
        "id": 2,
        "session_id": 1,
        "exercise": "clean",
        "real_weight_kg": 52.0,
        "reps": 2,
        "planned_weight_kg": 80.0,
        "planned_reps": 2,
        "planned_max_kg": 85.0,
    },
    {"id": 3, "session_id": 1, "exercise": "clean", "real_weight_kg": 66.0, "reps": 2},
    {"id": 4, "session_id": 1, "exercise": "clean", "real_weight_kg": 60.0, "reps": 2},
    {
        "id": 5,
        "session_id": 1,
        "exercise": "front squat",
        "real_weight_kg": 90.0,
        "reps": 3,
        "planned_weight_kg": 88.0,
        "planned_reps": 3,
    },
    {"id": 6, "session_id": 1, "exercise": "front squat", "real_weight_kg": 85.5, "reps": 3},
]

# Cuatro sesiones: la más nueva cerrada, otra el mismo día (CL-7), una con
# marca UTC del 16/10 que es 15/10 en local (CL-6) y una abierta olvidada
# hace 5 días (CL-3).
SESIONES_T4 = [
    {"id": 1, "started_at": "2026-10-16T21:00:00", "ended_at": "2026-10-16T22:11:00"},
    {"id": 2, "started_at": "2026-10-16T12:00:00", "ended_at": "2026-10-16T13:00:00"},
    {"id": 3, "started_at": "2026-10-16T01:30:00", "ended_at": "2026-10-16T02:15:00"},
    {"id": 4, "started_at": "2026-10-11T23:35:00", "ended_at": None},
]


def _resumen_fin(sesion, series) -> list[str]:
    """Líneas que produciría /fin para esa sesión (misma traducción que cmd_fin)."""
    start = datetime.fromisoformat(sesion["started_at"]).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(sesion["ended_at"]).replace(tzinfo=timezone.utc)
    items = [
        {
            "exercise": serie["exercise"],
            "real_weight": serie["real_weight_kg"],
            "reps": serie["reps"],
            "planned_weight": serie.get("planned_weight_kg"),
            "planned_max_kg": serie.get("planned_max_kg"),
        }
        for serie in series
    ]
    return core.build_summary(start, end, items).split("\n")


def test_payload_sesion_cerrada_con_estructura_del_plan5(rutas, monkeypatch, capsys):
    base, salida = rutas
    _crear_v2(base, [SESION_CERRADA], SERIES_S1)
    monkeypatch.setattr(core, "utc_now", lambda: RELOJ)

    assert dashboard.main() == 0
    payload = _payload_del_html(salida.read_text(encoding="utf-8"))
    assert payload["streak"] == {"days": 1, "missing_today": False, "last": "16/10"}
    sesiones = payload["sessions"]
    assert len(sesiones) == 1
    assert list(sesiones[0]) == [
        "date",
        "open",
        "opened_at",
        "duration",
        "volume",
        "lines",
        "pairs",
    ]
    assert sesiones[0] == {
        "date": "16/10",
        "open": False,
        "opened_at": None,
        "duration": "1 h 11 min",
        "volume": "1080,5 kg",
        "lines": [
            "clean: 4 series · 9 repeticiones · volumen 554 kg · máx 66 kg",
            "front squat: 2 series · 6 repeticiones · volumen 526,5 kg · máx 90 kg",
        ],
        "pairs": ["70→66", "80-85→52", "88→90"],
    }


def test_duracion_volumen_y_lineas_iguales_a_los_de_fin(rutas, monkeypatch, capsys):
    base, salida = rutas
    _crear_v2(base, [SESION_CERRADA], SERIES_S1)
    monkeypatch.setattr(core, "utc_now", lambda: RELOJ)

    assert dashboard.main() == 0
    sesion = _payload_del_html(salida.read_text(encoding="utf-8"))["sessions"][0]

    lineas_fin = _resumen_fin(SESION_CERRADA, SERIES_S1)
    assert sesion["duration"] == lineas_fin[0].removeprefix("Duración: ")
    assert sesion["volume"] == lineas_fin[-1].removeprefix("Volumen total: ")
    assert sesion["lines"] == [
        linea for linea in lineas_fin[1:-1] if not linea.startswith("  plan→real:")
    ]
    # Los pares de /fin, aplanados en el mismo orden de grupos (plan §5).
    assert sesion["pairs"] == [
        par
        for linea in lineas_fin
        if linea.startswith("  plan→real:")
        for par in linea.removeprefix("  plan→real: ").split(", ")
    ]


def test_cabecera_y_lineas_iguales_a_historial(rutas, monkeypatch, capsys):
    base, salida = rutas
    _crear_v2(base, [SESION_CERRADA], SERIES_S1)
    monkeypatch.setattr(core, "utc_now", lambda: RELOJ)

    assert dashboard.main() == 0
    documento = salida.read_text(encoding="utf-8")
    connection = db.connect(base)
    try:
        texto_historial = commands.cmd_historial(connection, [])
    finally:
        connection.close()
    bloque = texto_historial.split("\n\n")[0].split("\n")
    assert bloque[0] == "16/10 · 1 h 11 min"  # misma cabecera que /historial
    assert f"<h3>{bloque[0]}</h3>" in documento
    for linea in bloque[1:]:  # mismas líneas por ejercicio, carácter a carácter
        assert f"<li>{linea}</li>" in documento


def test_orden_desc_abierta_olvidada_fecha_local_y_duplicados(
    rutas, monkeypatch, capsys
):
    base, salida = rutas
    _crear_v2(base, SESIONES_T4)
    monkeypatch.setattr(core, "utc_now", lambda: RELOJ)

    assert dashboard.main() == 0
    documento = salida.read_text(encoding="utf-8")
    payload = _payload_del_html(documento)
    assert payload["sessions"] == [
        {
            "date": "16/10",
            "open": False,
            "opened_at": None,
            "duration": "1 h 11 min",
            "volume": None,
            "lines": [],
            "pairs": [],
        },
        {
            "date": "16/10",
            "open": False,
            "opened_at": None,
            "duration": "1 h 0 min",
            "volume": None,
            "lines": [],
            "pairs": [],
        },
        {
            # CL-6: marca UTC del 16/10, día local 15/10.
            "date": "15/10",
            "open": False,
            "opened_at": None,
            "duration": "45 min",
            "volume": None,
            "lines": [],
            "pairs": [],
        },
        {
            # CL-3: abierta hace 5 días, marcada y sin duración.
            "date": "11/10",
            "open": True,
            "opened_at": "20:35",
            "duration": None,
            "volume": None,
            "lines": [],
            "pairs": [],
        },
    ]
    # CL-7: las dos sesiones del 16/10 aparecen ambas.
    assert [s["date"] for s in payload["sessions"]].count("16/10") == 2
    # CL-3: la abierta no infla la racha (16 y 15 nada más, no hasta el 11).
    assert payload["streak"] == {"days": 2, "missing_today": False, "last": "16/10"}
    assert payload["month_sessions"] == 4
    # Sesiones sin series → solo cabecera (sin volumen ni líneas).
    assert documento.count("<article>") == 4
    assert "Volumen total" not in documento
    assert "<h3>11/10 · abierta desde las 20:35</h3>" in documento
    assert "<h3>15/10 · 45 min</h3>" in documento


def test_pares_rango_un_valor_sin_plan_y_filas_v1_null(rutas, monkeypatch, capsys):
    base, salida = rutas
    sesion = {
        "id": 1,
        "started_at": "2026-10-16T12:00:00",
        "ended_at": "2026-10-16T13:00:00",
    }
    series = [
        # CL-14: migrada de v1, planned_reps y planned_max_kg en NULL → simple.
        {
            "id": 1,
            "session_id": 1,
            "exercise": "clean",
            "real_weight_kg": 98.0,
            "reps": 1,
            "planned_weight_kg": 96.0,
        },
        # Sin plan → no aporta par.
        {"id": 2, "session_id": 1, "exercise": "clean", "real_weight_kg": 66.0, "reps": 3},
        # Con rango planificado.
        {
            "id": 3,
            "session_id": 1,
            "exercise": "clean",
            "real_weight_kg": 52.0,
            "reps": 2,
            "planned_weight_kg": 80.0,
            "planned_max_kg": 85.0,
        },
    ]
    _crear_v2(base, [sesion], series)
    monkeypatch.setattr(core, "utc_now", lambda: RELOJ)

    assert dashboard.main() == 0
    documento = salida.read_text(encoding="utf-8")
    sesion_payload = _payload_del_html(documento)["sessions"][0]
    assert sesion_payload["pairs"] == ["96→98", "80-85→52"]
    assert sesion_payload["lines"] == [
        "clean: 3 series · 6 repeticiones · volumen 400 kg · máx 98 kg"
    ]
    assert "<p>plan→real: 96→98, 80-85→52</p>" in documento  # flecha → visible
    assert "Volumen total: 400 kg" in documento


def test_ejercicio_hostil_escapado_en_lineas_y_json(rutas, monkeypatch, capsys):
    base, salida = rutas
    sesion = {
        "id": 1,
        "started_at": "2026-10-16T12:00:00",
        "ended_at": "2026-10-16T13:00:00",
    }
    series = [
        {"id": 1, "session_id": 1, "exercise": HOSTIL, "real_weight_kg": 70.0, "reps": 3}
    ]
    _crear_v2(base, [sesion], series)
    monkeypatch.setattr(core, "utc_now", lambda: RELOJ)

    assert dashboard.main() == 0
    documento = salida.read_text(encoding="utf-8")
    payload = _payload_del_html(documento)
    assert payload["sessions"][0]["lines"] == [
        f"{HOSTIL}: 1 serie · 3 repeticiones · volumen 210 kg · máx 70 kg"
    ]
    # Capa JSON: sin "<" literal. Capa visible: entidades en la línea.
    assert "\\u003c/script>\\u003cscript>alert(1)" in documento
    assert (
        "&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;:"
        " 1 serie · 3 repeticiones · volumen 210 kg · máx 70 kg"
    ) in documento


def test_html_un_article_por_sesion_con_volumen_lineas_y_pares(
    rutas, monkeypatch, capsys
):
    base, salida = rutas
    _crear_v2(base, [SESION_CERRADA], SERIES_S1)
    monkeypatch.setattr(core, "utc_now", lambda: RELOJ)

    assert dashboard.main() == 0
    documento = salida.read_text(encoding="utf-8")
    assert documento.count("<article>") == 1
    assert "</article>" in documento
    assert "<h3>16/10 · 1 h 11 min</h3>" in documento
    assert "<p>Volumen total: 1080,5 kg</p>" in documento
    assert "<li>clean: 4 series · 9 repeticiones · volumen 554 kg · máx 66 kg</li>" in (
        documento
    )
    assert "<p>plan→real: 70→66, 80-85→52, 88→90</p>" in documento
