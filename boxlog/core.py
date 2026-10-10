"""Lógica pura de BoxLog: parseo, validaciones, cálculos y formato de mensajes."""

import math
import re
from datetime import datetime

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


def parse_log_args(args: list[str]) -> tuple[str, float, int] | None:
    """Devuelve (ejercicio, peso, repeticiones) de /log, o None si el formato es inválido.

    Acepta la separadora en minúscula o mayúscula (84x5 y 84X5);
    las repeticiones deben ser enteras y se devuelven como int.
    """
    if len(args) < 2:
        return None
    weight_reps = args[-1].replace("X", "x")
    if weight_reps.count("x") != 1:
        return None
    weight_text, reps_text = weight_reps.split("x")
    try:
        weight = parse_number(weight_text)
        reps = parse_number(reps_text)
    except ValueError:
        return None
    if weight <= 0 or reps <= 0 or not reps.is_integer():
        return None
    exercise = normalize_exercise(" ".join(args[:-1]))
    if not exercise:
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
    (None si no tuvo plan). El volumen y el peso máximo usan siempre el peso real.
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
        pairs = [
            (item["planned_weight"], item["real_weight"])
            for item in items
            if item.get("planned_weight") is not None
        ]
        if pairs:
            pairs_text = ", ".join(
                f"{format_kg(planned)}→{format_kg(real)}" for planned, real in pairs
            )
            lines.append(f"  plan→real: {pairs_text}")
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
