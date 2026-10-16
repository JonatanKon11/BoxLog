"""Acceso a SQLite: esquema y consultas. Sin lógica de negocio ni texto de respuesta."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Orden de creación: sessions y plan_items antes de series (FKs).
# Esquema v2 (RF-06): plan con reps y rango, y el plan copiado a la serie (A-3).
_SCHEMA = """
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
    reps INTEGER,
    range_max_kg REAL,
    consumed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS series (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    exercise TEXT NOT NULL,
    real_weight_kg REAL NOT NULL,
    reps INTEGER NOT NULL,
    planned_weight_kg REAL,
    planned_reps INTEGER,
    planned_max_kg REAL,
    plan_item_id INTEGER REFERENCES plan_items(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);
"""

# Protección temporal: una base v1 (como la real) no se toca hasta la migración (T6).
_V1_ERROR = (
    "La base está en la versión 1: la migración a la versión 2 aún no está "
    "implementada (T6). No se abre para no dañarla."
)


def connect(path) -> sqlite3.Connection:
    """Abre la base de datos con las claves ajenas activadas (plan §3).

    Crea la carpeta contenedora si no existe (excepto en ":memory:").
    """
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_schema(connection: sqlite3.Connection) -> None:
    """Crea las tablas si no existen, en el esquema v2 (RF-06).

    Repetirlo no borra datos ni cambia la versión (RNF-3). Una base nueva nace
    en v2 (CL-11); una base en la versión 1 se rechaza con un error claro hasta
    que T6 implemente la migración, para no dañarla.
    """
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version == 1:
        raise RuntimeError(_V1_ERROR)
    connection.executescript(_SCHEMA)
    if version == 0:
        connection.execute("PRAGMA user_version = 2")
    connection.commit()


def _now() -> str:
    """Marca actual en UTC, en el mismo formato ISO que la 001, sin huso (RF-02).

    Convención de la 002: una marca sin huso en la base se interpreta como UTC
    (la convierte core._as_utc); el desfijo "+00:00" se omite para no cambiar el
    formato de texto que muestran los comandos hasta T5.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


# --- perfil (RF-01) ---


def save_profile(connection: sqlite3.Connection, weight_kg: float, height_cm: float) -> None:
    """Guarda una entrada nueva en el historial de perfil."""
    connection.execute(
        "INSERT INTO profile (weight_kg, height_cm, created_at) VALUES (?, ?, ?)",
        (weight_kg, height_cm, _now()),
    )
    connection.commit()


def get_profile(connection: sqlite3.Connection) -> dict | None:
    """Perfil vigente (el último cargado)."""
    row = connection.execute(
        "SELECT weight_kg, height_cm FROM profile ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


# --- RM (RF-02) ---


def save_rm(connection: sqlite3.Connection, exercise: str, weight_kg: float) -> None:
    """Guarda un RM nuevo; los anteriores se conservan en el historial."""
    connection.execute(
        "INSERT INTO rm_history (exercise, weight_kg, created_at) VALUES (?, ?, ?)",
        (exercise, weight_kg, _now()),
    )
    connection.commit()


def get_rm(connection: sqlite3.Connection, exercise: str) -> float | None:
    """RM vigente de un ejercicio (el último cargado), o None si no hay."""
    row = connection.execute(
        "SELECT weight_kg FROM rm_history WHERE exercise = ? ORDER BY id DESC LIMIT 1",
        (exercise,),
    ).fetchone()
    return row["weight_kg"] if row else None


def list_rms(connection: sqlite3.Connection) -> list[tuple[str, float]]:
    """RM vigente de cada ejercicio, ordenado por nombre."""
    rows = connection.execute(
        "SELECT exercise, weight_kg FROM rm_history"
        " WHERE id IN (SELECT MAX(id) FROM rm_history GROUP BY exercise)"
        " ORDER BY exercise"
    ).fetchall()
    return [(row["exercise"], row["weight_kg"]) for row in rows]


# --- sesiones (RF-03) ---


def open_session(connection: sqlite3.Connection) -> int | None:
    """Abre una sesión con marca de tiempo; devuelve su id o None si ya hay una abierta."""
    if get_open_session(connection) is not None:
        return None
    cursor = connection.execute(
        "INSERT INTO sessions (started_at, ended_at) VALUES (?, NULL)", (_now(),)
    )
    connection.commit()
    return cursor.lastrowid


def get_open_session(connection: sqlite3.Connection) -> dict | None:
    """La sesión abierta (ended_at IS NULL), o None. Como está en disco, sobrevive al reinicio."""
    row = connection.execute(
        "SELECT id, started_at FROM sessions WHERE ended_at IS NULL"
        " ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def get_session(connection: sqlite3.Connection, session_id: int) -> dict | None:
    """Datos de una sesión por id, o None si no existe."""
    row = connection.execute(
        "SELECT id, started_at, ended_at FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    return dict(row) if row else None


def close_session(connection: sqlite3.Connection, session_id: int) -> None:
    """Cierra la sesión poniendo ended_at (borrado por id, nunca tablas enteras)."""
    connection.execute(
        "UPDATE sessions SET ended_at = ? WHERE id = ?", (_now(), session_id)
    )
    connection.commit()


# --- plan por sesión (RF-05) ---


def replace_plan(
    connection: sqlite3.Connection, session_id: int, exercise: str, entries
) -> None:
    """Reemplaza el plan de un ejercicio de una sesión y reinicia el orden.

    El DELETE filtra siempre por sesión y ejercicio: no toca otros ejercicios
    ni otras sesiones (RF-05, CL-10). Cada entrada puede ser un número (solo
    peso, como en la 001) o un PlannedSet con weight_kg, range_max_kg y reps
    (RF-03).
    """
    connection.execute(
        "DELETE FROM plan_items WHERE session_id = ? AND exercise = ?",
        (session_id, exercise),
    )
    for position, entry in enumerate(entries, start=1):
        weight = getattr(entry, "weight_kg", None)
        if weight is None:
            weight = float(entry)
        connection.execute(
            "INSERT INTO plan_items (session_id, exercise, position, weight_kg,"
            " reps, range_max_kg, consumed) VALUES (?, ?, ?, ?, ?, ?, 0)",
            (
                session_id,
                exercise,
                position,
                weight,
                getattr(entry, "reps", None),
                getattr(entry, "range_max_kg", None),
            ),
        )
    connection.commit()


def get_next_plan_item(
    connection: sqlite3.Connection, session_id: int, exercise: str
) -> dict | None:
    """Primer plan_item sin consumir de ese ejercicio en la sesión, o None."""
    row = connection.execute(
        "SELECT id, position, weight_kg, reps, range_max_kg FROM plan_items"
        " WHERE session_id = ? AND exercise = ? AND consumed = 0"
        " ORDER BY position, id LIMIT 1",
        (session_id, exercise),
    ).fetchone()
    return dict(row) if row else None


def consume_plan_item(connection: sqlite3.Connection, plan_item_id: int) -> None:
    """Marca un plan_item como consumido por una serie."""
    connection.execute(
        "UPDATE plan_items SET consumed = 1 WHERE id = ?", (plan_item_id,)
    )
    connection.commit()


def release_plan_item(connection: sqlite3.Connection, plan_item_id: int) -> None:
    """Devuelve un plan_item a disponible (para /deshacer). Si ya se borró, no hace nada."""
    connection.execute(
        "UPDATE plan_items SET consumed = 0 WHERE id = ?", (plan_item_id,)
    )
    connection.commit()


# --- series (RF-06, RF-07) ---


def insert_series(
    connection: sqlite3.Connection,
    session_id: int,
    exercise: str,
    real_weight_kg: float,
    reps: int,
    planned_weight_kg: float | None,
    plan_item_id: int | None,
    planned_max_kg: float | None = None,
    planned_reps: int | None = None,
) -> int:
    """Guarda una serie y devuelve su id.

    El plan se copia a la propia serie (RF-04, A-3): planned_reps y
    planned_max_kg quedan NULL cuando no había plan o no tenía reps/rango.
    created_at es la hora de la serie, en UTC (RF-01, A-2).
    """
    cursor = connection.execute(
        "INSERT INTO series (session_id, exercise, real_weight_kg, reps,"
        " planned_weight_kg, planned_reps, planned_max_kg, plan_item_id, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            exercise,
            real_weight_kg,
            reps,
            planned_weight_kg,
            planned_reps,
            planned_max_kg,
            plan_item_id,
            _now(),
        ),
    )
    connection.commit()
    return cursor.lastrowid


def list_series(connection: sqlite3.Connection, session_id: int) -> list[dict]:
    """Series de una sesión en orden de registro (por id), con su plan copiado."""
    rows = connection.execute(
        "SELECT id, exercise, real_weight_kg, reps, planned_weight_kg,"
        " planned_reps, planned_max_kg, plan_item_id"
        " FROM series WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def count_series(
    connection: sqlite3.Connection, session_id: int, exercise: str
) -> int:
    """Nº de series previas de un ejercicio en la sesión."""
    return connection.execute(
        "SELECT COUNT(*) FROM series WHERE session_id = ? AND exercise = ?",
        (session_id, exercise),
    ).fetchone()[0]


def get_last_series(connection: sqlite3.Connection, session_id: int) -> dict | None:
    """Última serie de la sesión (la de id máximo), o None si no hay."""
    row = connection.execute(
        "SELECT id, exercise, real_weight_kg, reps, planned_weight_kg,"
        " planned_reps, planned_max_kg, plan_item_id"
        " FROM series WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    return dict(row) if row else None


def delete_series(connection: sqlite3.Connection, series_id: int) -> None:
    """Borra una serie por su id; nunca afecta a otras series ni sesiones."""
    connection.execute("DELETE FROM series WHERE id = ?", (series_id,))
    connection.commit()
