"""Tests del dashboard local: payload, CLI, render y escapado (spec 004, T3)."""

import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import boxlog.dashboard as dashboard
from boxlog import core, db

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
    {"date": "16/10", "open": True, "opened_at": "20:35", "duration": None},
    {"date": "16/10", "open": False, "opened_at": None, "duration": "45 min"},
    {"date": "15/10", "open": False, "opened_at": None, "duration": "1 h 0 min"},
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


def _crear_v2(base, sesiones=()):
    """Base v2 real creada con init_schema y las sesiones sembradas."""
    connection = db.connect(base)
    db.init_schema(connection)
    for fila in sesiones:
        connection.execute(
            "INSERT INTO sessions (id, started_at, ended_at) VALUES (?, ?, ?)",
            (fila["id"], fila["started_at"], fila["ended_at"]),
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
    payload = core.build_dashboard_payload(SESIONES, RELOJ, HOY)
    assert payload == PAYLOAD_ESPERADO


def test_build_dashboard_payload_base_vacia():
    payload = core.build_dashboard_payload([], RELOJ, HOY)
    assert payload == {
        "generated": "16/10/2026 21:04",
        "streak": {"days": 0, "missing_today": False, "last": None},
        "month_sessions": 0,
        "sessions": [],
    }


def test_build_dashboard_payload_usa_today_inyectado():
    # Sesión del 16/10 y "hoy" = 17/10: racha viva con aviso (CL-5).
    payload = core.build_dashboard_payload([SESIONES[0]], RELOJ, date(2026, 10, 17))
    assert payload["streak"] == {"days": 1, "missing_today": True, "last": "16/10"}
    assert payload["month_sessions"] == 1


def test_build_dashboard_payload_no_consulta_el_reloj(monkeypatch):
    monkeypatch.setattr(core, "utc_now", lambda: pytest.fail("no debe usar el reloj"))
    core.build_dashboard_payload([], RELOJ, HOY)


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
    assert '<ul class="sesiones">' not in documento
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
