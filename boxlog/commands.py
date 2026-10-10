"""Orquestación de comandos: valida con core, persiste con db y devuelve el texto.

Sin dependencias externas: cada comando recibe la conexión y los argumentos.
"""

from datetime import datetime

from boxlog import core, db


def cmd_inicio(connection, args: list[str]) -> str:
    """/inicio (RF-03): abre una sesión; con una ya abierta solo avisa (CL-1)."""
    if args:
        return core.usage_example("inicio")
    abierta = db.get_open_session(connection)
    if abierta is not None:
        desde = abierta["started_at"].replace("T", " ")
        return f"Sesión abierta desde {desde}. Ciérrala con /fin"
    session_id = db.open_session(connection)
    session = db.get_session(connection, session_id)
    return f"Sesión iniciada {session['started_at']}"


def cmd_fin(connection, args: list[str]) -> str:
    """/fin (RF-04): cierra la sesión y responde el resumen de core (CL-2, CL-5)."""
    if args:
        return core.usage_example("fin")
    abierta = db.get_open_session(connection)
    if abierta is None:
        return core.NO_OPEN_SESSION
    series = db.list_series(connection, abierta["id"])
    db.close_session(connection, abierta["id"])
    summary_series = [
        {
            "exercise": serie["exercise"],
            "real_weight": serie["real_weight_kg"],
            "reps": serie["reps"],
            "planned_weight": serie["planned_weight_kg"],
        }
        for serie in series
    ]
    start = datetime.fromisoformat(abierta["started_at"])
    return core.build_summary(start, datetime.now(), summary_series)


def cmd_perfil(connection, args: list[str]) -> str:
    """/perfil <peso> <altura> (RF-01): guarda el perfil; funciona con sesión abierta o no (CL-6)."""
    if len(args) != 2:
        return core.usage_example("perfil")
    try:
        weight = core.parse_number(args[0])
        height = core.parse_number(args[1])
    except ValueError:
        return core.usage_example("perfil")
    aviso = core.validate_profile(weight, height)
    if aviso:
        return aviso
    db.save_profile(connection, weight, height)
    return f"Perfil guardado: {core.format_kg(weight)} kg · {core.format_kg(height)} cm"


def cmd_rm(connection, args: list[str]) -> str:
    """/rm <ejercicio> <kg> (RF-02): guarda el RM vigente; el nombre se normaliza (RF-11)."""
    if len(args) != 2:
        return core.usage_example("rm")
    exercise = core.normalize_exercise(args[0])
    if not exercise:
        return core.usage_example("rm")
    try:
        kg = core.parse_number(args[1])
    except ValueError:
        return core.usage_example("rm")
    aviso = core.validate_rm(kg)
    if aviso:
        return aviso
    previous = db.get_rm(connection, exercise)
    db.save_rm(connection, exercise, kg)
    text = f"RM de {exercise} guardado: {core.format_kg(kg)} kg"
    if previous is not None:
        text += f" (antes {core.format_kg(previous)} kg)"
    return text


def cmd_rms(connection, args: list[str]) -> str:
    """/rms (RF-02): lista los RM vigentes; vacío → sugiere /rm."""
    if args:
        return core.usage_example("rms")
    rms = db.list_rms(connection)
    if not rms:
        return core.usage_example("rm")
    lines = ["RM vigentes:"] + [
        f"{exercise}: {core.format_kg(kg)} kg" for exercise, kg in rms
    ]
    return "\n".join(lines)
