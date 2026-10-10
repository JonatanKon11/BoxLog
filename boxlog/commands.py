"""Orquestación de comandos: valida con core, persiste con db y devuelve el texto.

Sin dependencias externas: cada comando recibe la conexión y los argumentos.
"""

from boxlog import core, db


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
