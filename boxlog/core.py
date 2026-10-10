"""Lógica pura de BoxLog: parseo, validaciones, cálculos y formato de mensajes."""


def parse_number(text: str) -> float:
    """Convierte un número con coma o punto en float. Lanza ValueError si no es válido."""
    return float(text.strip().replace(",", "."))


def normalize_exercise(text: str) -> str:
    """Normaliza el nombre de ejercicio: minúsculas y espacios múltiples colapsados."""
    return " ".join(text.lower().split())


def parse_log_args(args: list[str]) -> tuple[str, float, float] | None:
    """Devuelve (ejercicio, peso, repeticiones) de /log, o None si el formato es inválido."""
    if len(args) < 2:
        return None
    weight_reps = args[-1]
    if weight_reps.count("x") != 1:
        return None
    weight_text, reps_text = weight_reps.split("x")
    try:
        weight = parse_number(weight_text)
        reps = parse_number(reps_text)
    except ValueError:
        return None
    if weight <= 0 or reps <= 0:
        return None
    exercise = normalize_exercise(" ".join(args[:-1]))
    if not exercise:
        return None
    return exercise, weight, reps


def format_kg(value: float) -> str:
    """Formatea kilos con coma decimal: 22.5 -> '22,5', 84.0 -> '84'."""
    return f"{value:g}".replace(".", ",")
