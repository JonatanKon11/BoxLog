"""Acceso a SQLite: esquema y consultas. Sin lógica de negocio ni texto de respuesta."""

import sqlite3
from datetime import datetime
from pathlib import Path

# Orden de creación: sessions y plan_items antes de series (FKs).
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
    """Crea las tablas si no existen. Repetirlo no borra datos ni cambia la versión (RNF-3)."""
    connection.executescript(_SCHEMA)
    if connection.execute("PRAGMA user_version").fetchone()[0] == 0:
        connection.execute("PRAGMA user_version = 1")
    connection.commit()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


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
    connection: sqlite3.Connection, session_id: int, exercise: str, weights: list[float]
) -> None:
    """Reemplaza el plan de un ejercicio de una sesión y reinicia el orden.

    El DELETE filtra siempre por sesión y ejercicio: no toca otros ejercicios
    ni otras sesiones (RF-05, CL-10).
    """
    connection.execute(
        "DELETE FROM plan_items WHERE session_id = ? AND exercise = ?",
        (session_id, exercise),
    )
    for position, weight in enumerate(weights, start=1):
        connection.execute(
            "INSERT INTO plan_items (session_id, exercise, position, weight_kg, consumed)"
            " VALUES (?, ?, ?, ?, 0)",
            (session_id, exercise, position, weight),
        )
    connection.commit()


def get_next_plan_item(
    connection: sqlite3.Connection, session_id: int, exercise: str
) -> dict | None:
    """Primer plan_item sin consumir de ese ejercicio en la sesión, o None."""
    row = connection.execute(
        "SELECT id, position, weight_kg FROM plan_items"
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
) -> int:
    """Guarda una serie y devuelve su id."""
    cursor = connection.execute(
        "INSERT INTO series (session_id, exercise, real_weight_kg, reps,"
        " planned_weight_kg, plan_item_id, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            exercise,
            real_weight_kg,
            reps,
            planned_weight_kg,
            plan_item_id,
            _now(),
        ),
    )
    connection.commit()
    return cursor.lastrowid


def list_series(connection: sqlite3.Connection, session_id: int) -> list[dict]:
    """Series de una sesión en orden de registro (por id)."""
    rows = connection.execute(
        "SELECT id, exercise, real_weight_kg, reps, planned_weight_kg, plan_item_id"
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
        "SELECT id, exercise, real_weight_kg, reps, planned_weight_kg, plan_item_id"
        " FROM series WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    return dict(row) if row else None


def delete_series(connection: sqlite3.Connection, series_id: int) -> None:
    """Borra una serie por su id; nunca afecta a otras series ni sesiones."""
    connection.execute("DELETE FROM series WHERE id = ?", (series_id,))
    connection.commit()
