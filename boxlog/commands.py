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
        desde = core.format_start_time(abierta["started_at"], datetime.now())
        return f"Sesión abierta desde {desde}. Ciérrala con /fin"
    session_id = db.open_session(connection)
    session = db.get_session(connection, session_id)
    a_las = core.format_start_time(session["started_at"], datetime.now())
    return f"Sesión iniciada a {a_las}"


def cmd_hoy(connection, args: list[str]) -> str:
    """/hoy <ejercicio> <porcentajes...> (RF-05): convierte el RM vigente y guarda el plan.

    Reemplaza el plan anterior de ese mismo ejercicio en la sesión (CL-4).
    """
    abierta = db.get_open_session(connection)
    if abierta is None:
        return core.NO_OPEN_SESSION
    split = core.split_exercise_and_numbers(args)
    if split is None:
        return core.usage_example("hoy")
    exercise, numbers = split
    try:
        pcts = [core.parse_number(text) for text in numbers]
    except ValueError:
        return core.usage_example("hoy")
    if core.validate_percentages(pcts):
        return core.usage_example("hoy")
    rm = db.get_rm(connection, exercise)
    if rm is None:
        return f"No tengo RM de {exercise}, cárgalo con /rm"
    kilos = core.convert_percentages(rm, pcts)
    db.replace_plan(connection, abierta["id"], exercise, kilos)
    return "\n".join(
        f"{core.format_kg(pct)}% → {core.format_kg(kg)} kg"
        for pct, kg in zip(pcts, kilos)
    )


def cmd_log(connection, args: list[str]) -> str:
    """/log <ejercicio> <peso>x<repeticiones> (RF-06): registra una serie en la sesión.

    El peso es el real; el planificado sale en orden del siguiente ítem no
    consumido de /hoy. Sin plan la serie se guarda igual (CL-3).
    """
    abierta = db.get_open_session(connection)
    if abierta is None:
        return core.NO_OPEN_SESSION
    parsed = core.parse_log_args(args)
    if parsed is None:
        return core.usage_example("log")
    exercise, weight, reps = parsed
    session_id = abierta["id"]
    number = db.count_series(connection, session_id, exercise) + 1
    plan_item = db.get_next_plan_item(connection, session_id, exercise)
    if plan_item is None:
        planned, plan_item_id = None, None
    else:
        planned, plan_item_id = plan_item["weight_kg"], plan_item["id"]
        db.consume_plan_item(connection, plan_item_id)
    db.insert_series(
        connection, session_id, exercise, weight, reps, planned, plan_item_id
    )
    return core.format_log_confirmation(exercise, number, weight, reps, planned)


def cmd_deshacer(connection, args: list[str]) -> str:
    """/deshacer (RF-07): borra la última serie de la sesión y libera su plan."""
    if args:
        return core.usage_example("deshacer")
    abierta = db.get_open_session(connection)
    if abierta is None:
        return core.NO_OPEN_SESSION
    serie = db.get_last_series(connection, abierta["id"])
    if serie is None:
        return core.NO_SERIES
    if serie["plan_item_id"] is not None:
        db.release_plan_item(connection, serie["plan_item_id"])
    db.delete_series(connection, serie["id"])
    weight = core.format_kg(serie["real_weight_kg"])
    return f"Borrada: {serie['exercise']} {weight}x{serie['reps']}"


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
    split = core.split_exercise_and_numbers(args)
    if split is None:
        return core.usage_example("rm")
    exercise, numbers = split
    if len(numbers) != 1:
        return core.usage_example("rm")
    try:
        kg = core.parse_number(numbers[0])
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
