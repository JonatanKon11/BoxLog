"""Lógica pura de BoxLog: parseo, validaciones, cálculos y formato de mensajes."""

import math
import re
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

# Argentina: UTC-3, sin horario de verano. Desfase fijo (RF-02, RNF-2): no se
# usa zoneinfo porque exigiría la dependencia tzdata en Windows.
LOCAL_UTC_OFFSET = timedelta(hours=-3)

# Solo notación decimal simple: opcional '-', dígitos y opcional parte decimal.
# Sin nan, inf ni notación científica (1e3).
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def parse_number(text: str) -> float:
    """Convierte un número decimal con coma o punto en float.

    Lanza ValueError si no es válido: no numérico, no finito (nan, inf)
    o en notación científica.
    """
    cleaned = text.strip().replace(",", ".")
    if not _NUMBER_RE.match(cleaned):
        raise ValueError(f"Número no válido: {text!r}")
    value = float(cleaned)
    if not math.isfinite(value):
        raise ValueError(f"Número no finito: {text!r}")
    return value


def normalize_exercise(text: str) -> str:
    """Normaliza el nombre de ejercicio: minúsculas y espacios múltiples colapsados."""
    return " ".join(text.lower().split())


def _is_number(text: str) -> bool:
    """¿El texto es un número decimal (coma o punto)?"""
    try:
        parse_number(text)
        return True
    except ValueError:
        return False


def _is_weight_reps(text: str) -> bool:
    """¿El texto tiene el formato <peso>x<repeticiones>?"""
    return text.replace("X", "x").count("x") == 1


def split_exercise_and_numbers(
    args: list[str], is_number=None
) -> tuple[str, list[str]] | None:
    """(ejercicio normalizado, números) hasta el primer argumento numérico (RF-11).

    El nombre del ejercicio son todas las palabras iniciales hasta el primer
    argumento numérico; el resto se devuelve como están. None si falta el
    nombre o no hay números. is_number permite reutilizar la separación en
    /log, cuyo "número" es <peso>x<repeticiones>.
    """
    if is_number is None:
        is_number = _is_number
    index = 0
    while index < len(args) and not is_number(args[index]):
        index += 1
    exercise = normalize_exercise(" ".join(args[:index]))
    numbers = args[index:]
    if not exercise or not numbers:
        return None
    return exercise, numbers


def parse_log_args(args: list[str]) -> tuple[str, float, int] | None:
    """Devuelve (ejercicio, peso, repeticiones) de /log, o None si el formato es inválido.

    Acepta la separadora en minúscula o mayúscula (84x5 y 84X5);
    las repeticiones deben ser enteras y se devuelven como int.
    """
    split = split_exercise_and_numbers(args, _is_weight_reps)
    if split is None:
        return None
    exercise, numbers = split
    if len(numbers) != 1:
        return None
    weight_text, reps_text = numbers[0].replace("X", "x").split("x")
    try:
        weight = parse_number(weight_text)
        reps = parse_number(reps_text)
    except ValueError:
        return None
    if weight <= 0 or reps <= 0 or not reps.is_integer():
        return None
    return exercise, weight, int(reps)


def format_kg(value: float) -> str:
    """Formatea kilos con coma decimal: 22.5 -> '22,5', 84.0 -> '84'."""
    return f"{value:g}".replace(".", ",")


_USAGE_EXAMPLES = {
    "perfil": "Usa /perfil 78 175",
    "rm": "Usa /rm clean 100",
    "hoy": "Usa /hoy clean 70 80 85",
    "log": "Usa /log clean 84x5",
    "inicio": "Usa /inicio (sin nada más)",
    "fin": "Usa /fin (sin nada más)",
    "rms": "Usa /rms (sin nada más)",
    "deshacer": "Usa /deshacer (sin nada más)",
}


NO_OPEN_SESSION = "No hay sesión abierta, envía /inicio"
NO_SERIES = "No hay series en esta sesión"


def help_text() -> str:
    """Lista de comandos disponibles (RF-12)."""
    return (
        "Comandos disponibles:\n"
        "/perfil <peso> <altura> — guarda tu peso (kg) y altura (cm)\n"
        "/rm <ejercicio> <kg> — guarda el RM de un ejercicio\n"
        "/rms — lista los RM vigentes\n"
        "/inicio — abre la sesión\n"
        "/fin — cierra la sesión y muestra el resumen\n"
        "/hoy <ejercicio> <porcentajes...> — kilos por porcentaje de RM\n"
        "/log <ejercicio> <peso>x<repeticiones> — registra una serie\n"
        "/deshacer — borra la última serie"
    )


def usage_example(command: str) -> str:
    """Aviso de uso con un ejemplo real (RF-09).

    Comandos desconocidos o no reconocidos devuelven la lista (help_text).
    """
    key = command.strip().lstrip("/").lower()
    if key in _USAGE_EXAMPLES:
        return _USAGE_EXAMPLES[key]
    return help_text()


def validate_profile(weight: float, height: float) -> str | None:
    """Rangos del perfil (RF-01): 30–300 kg y 100–250 cm.

    Devuelve un aviso con el motivo y el ejemplo, o None si todo está bien.
    """
    if not 30 <= weight <= 300:
        return f"El peso tiene que estar entre 30 y 300 kg. {usage_example('perfil')}"
    if not 100 <= height <= 250:
        return f"La altura tiene que estar entre 100 y 250 cm. {usage_example('perfil')}"
    return None


def validate_rm(kg: float) -> str | None:
    """Rango del RM (RF-02): 1–500 kg. Aviso con motivo y ejemplo, o None."""
    if not 1 <= kg <= 500:
        return f"El RM tiene que estar entre 1 y 500 kg. {usage_example('rm')}"
    return None


def validate_percentages(pcts: list[float]) -> str | None:
    """Porcentajes de /hoy (RF-05): de 1 a 120, con decimales. Devuelve el aviso o None."""
    if pcts and all(1 <= p <= 120 for p in pcts):
        return None
    return usage_example("hoy")


# Valores del plan: <porcentaje>, <porcentaje>x<reps>, <mín>-<más> y <mín>-<más>x<reps>.
# El guion solo puede ir dentro, entre dos números; las reps son solo dígitos (CL-13, CL-14).
_PLAN_TOKEN_RE = re.compile(r"^(\d+(?:[.,]\d+)?)(?:-(\d+(?:[.,]\d+)?))?(?:x(\d+))?$")


class PlanEntry(NamedTuple):
    """Una entrada del plan de /hoy: porcentaje (o rango) y repeticiones opcionales (RF-03)."""

    pct_low: float
    pct_high: float | None
    reps: int | None


def _plan_grammar_error(token: str) -> str:
    """Aviso de gramática inválida con el valor ofensivo y un motivo específico (RF-09).

    Motivo deducible cuando se puede: "x" pegada mal, negativos y rangos incompletos;
    si no, "no se entiende". Todos terminan con un ejemplo de uso.
    """
    normalized = token.replace("–", "-").replace("X", "x")
    if normalized.startswith("-"):
        return f"'{token}' no es válido: no se aceptan negativos. {usage_example('hoy')}"
    if normalized == "x" or normalized.startswith("x") or normalized.endswith("x"):
        return f"'{token}' va pegada, sin espacios: 65x3"
    if normalized.endswith("-"):
        return f"'{token}' es un rango incompleto: 80-85"
    return f"'{token}' no se entiende. {usage_example('hoy')}"


def parse_plan_entries(tokens: list[str]) -> list[PlanEntry] | str:
    """Entradas del plan de /hoy a partir de sus valores, ya separados del nombre.

    Reutiliza los tokens que produce split_exercise_and_numbers en el comando. Cada
    valor se normaliza (en-dash "–" a "-", "X" a "x"; CL-15, CL-18) y se valida de
    izquierda a derecha en este orden: gramática → porcentajes 1–120 (ambos extremos
    del rango) → mínimo menor que máximo → repeticiones enteras ≥ 1. Solo se informa
    el primer error, con motivo y ejemplo (RF-09, CL-17); un valor inválido invalida
    toda la orden. Sin valores devuelve el aviso de uso de la 001. La conversión a
    kilos no se hace aquí.
    """
    if not tokens:
        return usage_example("hoy")
    entries: list[PlanEntry] = []
    for token in tokens:
        match = _PLAN_TOKEN_RE.match(token.replace("–", "-").replace("X", "x"))
        if match is None:
            return _plan_grammar_error(token)
        low_text, high_text, reps_text = match.groups()
        low = parse_number(low_text)
        high = parse_number(high_text) if high_text is not None else None
        if not 1 <= low <= 120 or (high is not None and not 1 <= high <= 120):
            return f"El porcentaje tiene que estar entre 1 y 120. {usage_example('hoy')}"
        if high is not None and high <= low:
            return (
                "El mínimo del rango tiene que ser menor que el máximo. "
                "Usa /hoy clean 80-85"
            )
        reps = int(reps_text) if reps_text is not None else None
        if reps is not None and reps < 1:
            return (
                "Las repeticiones tienen que ser un entero de 1 en adelante. "
                "Usa /hoy clean 65x3"
            )
        entries.append(PlanEntry(low, high, reps))
    return entries


class PlannedSet(NamedTuple):
    """Kilos de una entrada del plan ya convertidos con el RM (RF-03)."""

    weight_kg: float
    range_max_kg: float | None
    reps: int | None


def convert_plan_entries(rm: float, entries: list[PlanEntry]) -> list[PlannedSet]:
    """Kilos de cada entrada del plan con el RM vigente (RF-03, CL-16).

    Cada extremo de un rango se convierte y se redondea a 0,5 kg por separado
    (round_half_kg, empates hacia arriba); si tras redondear coinciden, la entrada
    se devuelve como valor único (sin rango). No valida: las entradas ya pasaron
    por parse_plan_entries.
    """
    sets: list[PlannedSet] = []
    for entry in entries:
        low = round_half_kg(rm * entry.pct_low / 100)
        high = None
        if entry.pct_high is not None:
            high = round_half_kg(rm * entry.pct_high / 100)
            if high == low:
                high = None
        sets.append(PlannedSet(low, high, entry.reps))
    return sets


def format_hoy_lines(entries: list[PlanEntry], sets: list[PlannedSet]) -> str:
    """Respuesta de /hoy: una línea por entrada, en el orden dado (RF-03, A-1, CL-19).

    Formatos: "70% → 84 kg", "65% × 3 → 52 kg", "80-85% → 64-68 kg" y
    "80-85% × 1 → 64-68 kg". El rango de % es el pedido; los kilos muestran el
    rango convertido o el valor único si el rango colapsó (CL-16).
    """
    lines = []
    for entry, planned in zip(entries, sets):
        pct = f"{format_kg(entry.pct_low)}%"
        if entry.pct_high is not None:
            pct = f"{format_kg(entry.pct_low)}-{format_kg(entry.pct_high)}%"
        reps = f" × {entry.reps}" if entry.reps is not None else ""
        kg = f"{format_kg(planned.weight_kg)} kg"
        if planned.range_max_kg is not None:
            kg = f"{format_kg(planned.weight_kg)}-{format_kg(planned.range_max_kg)} kg"
        lines.append(f"{pct}{reps} → {kg}")
    return "\n".join(lines)


def format_plan_suffix(
    planned_weight: float | None,
    planned_max_kg: float | None = None,
    planned_reps: int | None = None,
) -> str:
    """Sufijo del plan en la confirmación de /log (RF-04, A-1): '' cuando no hay plan.

    Formatos: " (plan 84)" sin reps (igual que la 001), " (plan 66 kg × 1)" con reps,
    " (plan 64-68 kg × 1)" con rango y reps y " (plan 64-68)" con rango sin reps.
    Los valores salen de la serie (planned_weight_kg, planned_max_kg, planned_reps),
    no de plan_items (A-3).
    """
    if planned_weight is None:
        return ""
    if planned_max_kg is not None:
        text = f"{format_kg(planned_weight)}-{format_kg(planned_max_kg)}"
    else:
        text = format_kg(planned_weight)
    if planned_reps is not None:
        return f" (plan {text} kg × {planned_reps})"
    return f" (plan {text})"


def round_half_kg(kg: float) -> float:
    """Redondea al 0,5 kg más cercano, con los empates hacia arriba (RF-05)."""
    return math.floor(kg * 2 + 0.5) / 2


def convert_percentages(rm: float, pcts: list[float]) -> list[float]:
    """Kilos equivalentes a cada porcentaje del RM, redondeados a 0,5 kg (RF-05)."""
    return [round_half_kg(rm * p / 100) for p in pcts]


def format_duration(seconds: float) -> str:
    """Duración como '1 h 23 min' o, si dura menos de una hora, '45 min' (RF-04)."""
    total_minutes = int(seconds) // 60
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min"


def utc_now() -> datetime:
    """Hora actual consciente en UTC: la única base con la que se trabaja (RF-02)."""
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    """Interpreta una marca sin huso como UTC (todas las marcas de la base son UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_local(dt: datetime) -> datetime:
    """Convierte una marca UTC a hora local (UTC-3; RF-02)."""
    return _as_utc(dt) + LOCAL_UTC_OFFSET


def is_today(mark: datetime, now: datetime) -> bool:
    """¿La marca cae en el día local de ahora? (CL-12: el día se decide en local)."""
    return to_local(mark).date() == to_local(now).date()


def format_start_time(started_at: str, now: datetime) -> str:
    """Hora legible de apertura de sesión (RF-03).

    'las 20:35' si empezó hoy; 'el 09/10 a las 20:35' si empezó otro día.
    started_at es la marca ISO de la base de datos; now permite testear.
    """
    start = datetime.fromisoformat(started_at)
    hora = f"{start:%H:%M}"
    if start.date() == now.date():
        return f"las {hora}"
    return f"el {start:%d/%m} a las {hora}"


def build_summary(start: datetime, end: datetime, series: list[dict]) -> str:
    """Resumen de la sesión (RF-04).

    Cada serie es un dict con exercise, real_weight, reps y planned_weight
    (None si no tuvo plan); con planned_max_kg (plano de la serie, A-3) el par
    plan→real se muestra como "64-68→66" (RF-05). El volumen y el peso máximo
    usan siempre el peso real.
    """
    if not series:
        return "Sesión cerrada sin series."
    lines = [f"Duración: {format_duration((end - start).total_seconds())}"]
    order: list[str] = []
    grouped: dict[str, list[dict]] = {}
    for item in series:
        key = normalize_exercise(item["exercise"])
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(item)
    total_volume = 0.0
    for key in order:
        items = grouped[key]
        count = len(items)
        reps = sum(int(item["reps"]) for item in items)
        volume = sum(float(item["real_weight"]) * int(item["reps"]) for item in items)
        max_weight = max(float(item["real_weight"]) for item in items)
        total_volume += volume
        serie_word = "serie" if count == 1 else "series"
        rep_word = "repetición" if reps == 1 else "repeticiones"
        lines.append(
            f"{key}: {count} {serie_word} · {reps} {rep_word} · "
            f"volumen {format_kg(volume)} kg · máx {format_kg(max_weight)} kg"
        )
        pairs = []
        for item in items:
            if item.get("planned_weight") is None:
                continue
            real = format_kg(item["real_weight"])
            planned_max = item.get("planned_max_kg")
            if planned_max is not None:
                pairs.append(
                    f"{format_kg(item['planned_weight'])}-{format_kg(planned_max)}→{real}"
                )
            else:
                pairs.append(f"{format_kg(item['planned_weight'])}→{real}")
        if pairs:
            lines.append(f"  plan→real: {', '.join(pairs)}")
    lines.append(f"Volumen total: {format_kg(total_volume)} kg")
    return "\n".join(lines)


def format_log_confirmation(
    exercise: str, n: int, weight: float, reps: int, planned: float | None
) -> str:
    """Confirmación de /log (RF-06): '<ejercicio> · serie N: <peso> kg × <reps>'."""
    text = f"{exercise} · serie {n}: {format_kg(weight)} kg × {reps}"
    if planned is not None:
        text += f" (plan {format_kg(planned)})"
    return text
