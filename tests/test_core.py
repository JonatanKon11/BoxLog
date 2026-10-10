"""Tests de core: números, normalización y parseo de /log (RF-06, RF-09, RF-10, RF-11)."""

import pytest

from boxlog.core import format_kg, normalize_exercise, parse_log_args, parse_number


# --- parse_number (RF-10) ---


def test_parse_number_con_punto():
    assert parse_number("84.5") == 84.5


def test_parse_number_con_coma():
    assert parse_number("84,5") == 84.5


def test_parse_number_entero():
    assert parse_number("84") == 84


@pytest.mark.parametrize("texto", ["", "abc", "84,5.5", "12kg"])
def test_parse_number_invalido_lanza_value_error(texto):
    with pytest.raises(ValueError):
        parse_number(texto)


# --- normalize_exercise (RF-11) ---


def test_normalize_exercise_a_minusculas():
    assert normalize_exercise("Clean") == "clean"


def test_normalize_exercise_espacios_extremos():
    assert normalize_exercise("clean  ") == "clean"


def test_normalize_exercise_colapsa_espacios_multiples():
    assert normalize_exercise("  Clean   Jerk ") == "clean jerk"


def test_normalize_exercise_mismo_ejercicio_con_variaciones():
    assert normalize_exercise("Clean") == normalize_exercise("clean  ")


# --- parse_log_args (RF-06, RF-09, RF-10, RF-11) ---


def test_parse_log_args_valido():
    assert parse_log_args(["clean", "84x5"]) == ("clean", 84.0, 5.0)


def test_parse_log_args_peso_con_coma():
    assert parse_log_args(["clean", "84,5x3"]) == ("clean", 84.5, 3.0)


def test_parse_log_args_normaliza_ejercicio():
    assert parse_log_args(["Clean", "84x5"]) == ("clean", 84.0, 5.0)


def test_parse_log_args_ejercicio_varias_palabras():
    assert parse_log_args(["clean", "and", "jerk", "84x5"]) == (
        "clean and jerk",
        84.0,
        5.0,
    )


@pytest.mark.parametrize(
    "args",
    [
        [],                       # sin argumentos
        ["clean"],                # falta peso y repeticiones
        ["clean", "845"],         # falta la x (falta de repeticiones)
        ["clean", "x5"],          # x mal colocada
        ["clean", "84x"],         # sin repeticiones
        ["clean", "84x5x2"],      # x repetida
        ["clean", "0x5"],         # peso cero
        ["clean", "-84x5"],       # peso negativo
        ["clean", "84x0"],        # repeticiones cero
        ["clean", "84x-3"],       # repeticiones negativas
        ["clean", "84x5", "extra"],  # argumentos de más
        ["", "84x5"],             # ejercicio vacío
    ],
)
def test_parse_log_args_invalido_devuelve_none(args):
    assert parse_log_args(args) is None


# --- format_kg (RF-01, RNF-1) ---


def test_format_kg_con_coma_decimal():
    assert format_kg(22.5) == "22,5"


def test_format_kg_entero_sin_decimales():
    assert format_kg(84) == "84"
    assert format_kg(84.0) == "84"


def test_format_kg_dos_decimales():
    assert format_kg(84.25) == "84,25"
