"""Tests de core: números, normalización y parseo de /log (RF-06, RF-09, RF-10, RF-11)."""

import pytest

from datetime import datetime, timedelta
from pathlib import Path

import boxlog.core as core_module
from boxlog.core import (
    build_summary,
    convert_percentages,
    format_duration,
    format_kg,
    format_log_confirmation,
    format_start_time,
    help_text,
    normalize_exercise,
    parse_log_args,
    parse_number,
    round_half_kg,
    usage_example,
    validate_percentages,
    validate_profile,
    validate_rm,
)


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


@pytest.mark.parametrize("texto", ["nan", "inf", "-inf", "1e3", "1E3", "1e-3"])
def test_parse_number_rechaza_no_finitos_y_notacion_cientifica(texto):
    """RF-09: nan, inf y notación científica son formato inválido."""
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


def test_parse_log_args_repeticiones_son_int():
    resultado = parse_log_args(["clean", "84x5"])
    assert resultado is not None
    assert isinstance(resultado[2], int)


def test_parse_log_args_x_mayuscula():
    assert parse_log_args(["clean", "84X5"]) == ("clean", 84.0, 5)


def test_parse_log_args_x_mayuscula_con_peso_coma():
    assert parse_log_args(["clean", "84,5X3"]) == ("clean", 84.5, 3)


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
        ["clean", "84x5.5"],      # repeticiones no enteras
        ["clean", "84x5,5"],      # repeticiones no enteras con coma
        ["clean", "1e3x5"],       # notación científica
        ["clean", "nanx5"],       # no numérico
        ["clean", "84xinf"],      # no finito
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


# --- validate_profile (RF-01, RF-09) ---


def test_validate_profile_dentro_de_rango_devuelve_none():
    assert validate_profile(78, 175) is None
    assert validate_profile(30, 100) is None
    assert validate_profile(300, 250) is None
    assert validate_profile(78.5, 175) is None


@pytest.mark.parametrize(
    "peso, altura, motivo",
    [
        (29.9, 175, "El peso tiene que estar entre 30 y 300 kg."),
        (301, 175, "El peso tiene que estar entre 30 y 300 kg."),
        (78, 99, "La altura tiene que estar entre 100 y 250 cm."),
        (78, 251, "La altura tiene que estar entre 100 y 250 cm."),
    ],
)
def test_validate_profile_fuera_de_rango_devuelve_motivo_y_ejemplo(peso, altura, motivo):
    assert validate_profile(peso, altura) == f"{motivo} Usa /perfil 78 175"


# --- validate_rm (RF-02, RF-09) ---


def test_validate_rm_dentro_de_rango_devuelve_none():
    assert validate_rm(1) is None
    assert validate_rm(100) is None
    assert validate_rm(500) is None
    assert validate_rm(100.5) is None


@pytest.mark.parametrize("kg", [0, 0.9, 501])
def test_validate_rm_fuera_de_rango_devuelve_motivo_y_ejemplo(kg):
    assert validate_rm(kg) == "El RM tiene que estar entre 1 y 500 kg. Usa /rm clean 100"


# --- validate_percentages (RF-05, RF-09) ---


def test_validate_percentages_validos_devuelven_none():
    assert validate_percentages([70, 80, 85]) is None
    assert validate_percentages([70.5]) is None
    assert validate_percentages([1, 120]) is None


@pytest.mark.parametrize(
    "pcts",
    [[], [0.9], [121], [0], [-5], [70, 121]],
)
def test_validate_percentages_invalidos_devuelven_aviso_de_uso(pcts):
    aviso = validate_percentages(pcts)
    assert aviso is not None
    assert "hoy" in aviso


# --- usage_example (RF-09) ---


def test_usage_example_log_con_ejemplo_real():
    assert usage_example("log") == "Usa /log clean 84x5"


def test_usage_example_acepta_comando_con_barra():
    assert usage_example("/log") == usage_example("log")


@pytest.mark.parametrize(
    "comando, ejemplo",
    [
        ("perfil", "Usa /perfil 78 175"),
        ("rm", "Usa /rm clean 100"),
        ("hoy", "Usa /hoy clean 70 80 85"),
    ],
)
def test_usage_example_comandos_con_argumentos(comando, ejemplo):
    assert usage_example(comando) == ejemplo


@pytest.mark.parametrize("comando", ["inicio", "fin", "rms", "deshacer"])
def test_usage_example_comandos_sin_argumentos_aviso_corto(comando):
    assert usage_example(comando) == f"Usa /{comando} (sin nada más)"


def test_usage_example_comandos_conocidos_no_devuelven_la_lista_completa():
    for comando in ("perfil", "rm", "hoy", "log", "inicio", "fin", "rms", "deshacer"):
        assert "Comandos disponibles" not in usage_example(comando)


def test_usage_example_comando_desconocido_devuelve_la_lista_de_comandos():
    assert usage_example("esto_no_existe") == help_text()


# --- round_half_kg y convert_percentages (RF-05) ---


@pytest.mark.parametrize(
    "entrada, esperado",
    [(84.0, 84.0), (84.2, 84.0), (84.3, 84.5), (22.4, 22.5)],
)
def test_round_half_kg_al_medio_kilo_mas_cercano(entrada, esperado):
    assert round_half_kg(entrada) == esperado


@pytest.mark.parametrize(
    "entrada, esperado",
    [(123.25, 123.5), (123.75, 124.0), (124.25, 124.5)],
)
def test_round_half_kg_empates_hacia_arriba(entrada, esperado):
    """RF-05: los empates se redondean hacia arriba, no al par."""
    assert round_half_kg(entrada) == esperado


def test_convert_percentages_rm_100():
    assert convert_percentages(100, [70, 80, 85]) == [70.0, 80.0, 85.0]


def test_convert_percentages_redondea_a_medio_kilo():
    assert convert_percentages(100, [33.3]) == [33.5]


def test_convert_percentages_rm_con_decimal():
    assert convert_percentages(120, [70]) == [84.0]


# --- format_duration (RF-04) ---


def test_format_duration_minutos():
    assert format_duration(45 * 60) == "45 min"


def test_format_duration_hora_y_minutos():
    assert format_duration(83 * 60) == "1 h 23 min"


def test_format_duration_hora_completa():
    assert format_duration(3600) == "1 h 0 min"


# --- format_start_time (RF-03) ---


def test_format_start_time_hoy_sin_fecha():
    ahora = datetime(2026, 10, 10, 21, 0)
    assert format_start_time("2026-10-10T20:35:00", ahora) == "las 20:35"


def test_format_start_time_otro_dia_con_fecha():
    ahora = datetime(2026, 10, 10, 9, 0)
    assert format_start_time("2026-10-09T20:35:00", ahora) == "el 09/10 a las 20:35"


# --- build_summary (RF-04, CL-5) ---

INICIO = datetime(2026, 1, 5, 10, 0)


def test_build_summary_sesion_vacia_una_sola_linea():
    texto = build_summary(INICIO, INICIO + timedelta(minutes=45), [])
    assert texto == "Sesión cerrada sin series."
    assert "\n" not in texto


def test_build_summary_duración_volumen_real_y_total():
    series = [
        {"exercise": "clean", "real_weight": 84.0, "reps": 5, "planned_weight": None},
        {"exercise": "clean", "real_weight": 84.0, "reps": 5, "planned_weight": None},
    ]
    texto = build_summary(INICIO, INICIO + timedelta(minutes=83), series)
    assert "Duración: 1 h 23 min" in texto
    assert "clean: 2 series · 10 repeticiones · volumen 840 kg · máx 84 kg" in texto
    assert texto.splitlines()[-1] == "Volumen total: 840 kg"


def test_build_summary_duracion_menos_de_una_hora():
    series = [
        {"exercise": "front", "real_weight": 40.0, "reps": 3, "planned_weight": None},
    ]
    texto = build_summary(INICIO, INICIO + timedelta(minutes=45), series)
    assert "Duración: 45 min" in texto


def test_build_summary_pares_plan_real_solo_series_con_plan():
    series = [
        {"exercise": "clean", "real_weight": 82.0, "reps": 5, "planned_weight": 84.0},
        {"exercise": "clean", "real_weight": 96.0, "reps": 5, "planned_weight": 96.0},
        {"exercise": "clean", "real_weight": 90.0, "reps": 5, "planned_weight": None},
        {"exercise": "front", "real_weight": 40.0, "reps": 3, "planned_weight": None},
    ]
    texto = build_summary(INICIO, INICIO + timedelta(minutes=45), series)
    assert "plan→real: 84→82, 96→96" in texto
    assert texto.count("plan→real") == 1  # front no tiene series con plan


def test_build_summary_peso_maximo_usa_peso_real():
    series = [
        {"exercise": "clean", "real_weight": 82.0, "reps": 5, "planned_weight": 100.0},
    ]
    texto = build_summary(INICIO, INICIO + timedelta(minutes=45), series)
    assert "máx 82 kg" in texto
    assert "máx 100" not in texto


def test_build_summary_singular_1_serie_1_repeticion():
    series = [
        {"exercise": "clean", "real_weight": 84.0, "reps": 1, "planned_weight": None},
    ]
    texto = build_summary(INICIO, INICIO + timedelta(minutes=10), series)
    assert "clean: 1 serie · 1 repetición · volumen 84 kg · máx 84 kg" in texto


# --- format_log_confirmation (RF-06) ---


def test_format_log_confirmation_sin_plan():
    assert (
        format_log_confirmation("clean", 1, 84.0, 5, None)
        == "clean · serie 1: 84 kg × 5"
    )


def test_format_log_confirmation_con_plan():
    assert (
        format_log_confirmation("clean", 2, 82.0, 5, 84.0)
        == "clean · serie 2: 82 kg × 5 (plan 84)"
    )


def test_format_log_confirmation_peso_con_coma_decimal():
    assert (
        format_log_confirmation("front", 1, 42.5, 3, None)
        == "front · serie 1: 42,5 kg × 3"
    )


# --- separación de capas (constitución 3) ---


def test_core_no_importa_telegram_ni_sqlite():
    fuente = Path(core_module.__file__).read_text(encoding="utf-8").lower()
    assert "telegram" not in fuente
    assert "sqlite" not in fuente


# --- help_text (RF-12) ---


def test_help_text_lista_todos_los_comandos_v01():
    texto = help_text()
    for comando in (
        "/perfil",
        "/rm",
        "/rms",
        "/inicio",
        "/fin",
        "/hoy",
        "/log",
        "/deshacer",
    ):
        assert comando in texto
