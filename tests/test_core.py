"""Tests de core: números, normalización y parseo de /log (RF-06, RF-09, RF-10, RF-11)."""

import pytest

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import boxlog.core as core_module
from boxlog.core import (
    LOCAL_UTC_OFFSET,
    PlanEntry,
    PlannedSet,
    build_summary,
    COMMAND_MENU,
    count_month,
    convert_percentages,
    convert_plan_entries,
    exercise_stat_line,
    format_duration,
    format_hoy_lines,
    format_kg,
    format_log_confirmation,
    format_plan_suffix,
    format_start_time,
    group_series_by_exercise,
    help_text,
    is_log_token,
    is_plan_token,
    is_today,
    local_date,
    max_load_points,
    normalize_exercise,
    parse_log_args,
    parse_number,
    parse_plan_entries,
    plan_real_pairs,
    percentage_table,
    round_half_kg,
    split_exercise_and_numbers,
    streak_days,
    to_local,
    usage_example,
    utc_now,
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


# --- split_exercise_and_numbers (RF-11) ---


def test_split_nombre_multipalabra_hasta_el_primer_numero():
    assert split_exercise_and_numbers(["front", "squat", "70", "80"]) == (
        "front squat",
        ["70", "80"],
    )


def test_split_normaliza_el_nombre():
    assert split_exercise_and_numbers(["Clean", "100"]) == ("clean", ["100"])


def test_split_sin_nombre_devuelve_none():
    assert split_exercise_and_numbers(["70", "80"]) is None
    assert split_exercise_and_numbers([]) is None


def test_split_sin_numeros_devuelve_none():
    assert split_exercise_and_numbers(["clean"]) is None
    assert split_exercise_and_numbers(["clean", "abc"]) is None


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


# --- zona horaria (RF-02, CL-12) ---


def test_local_utc_offset_es_utc_menos_tres_horas():
    assert LOCAL_UTC_OFFSET == timedelta(hours=-3)


def test_utc_now_devuelve_hora_consciente_en_utc():
    ahora = utc_now()
    assert ahora.tzinfo is not None
    assert ahora.utcoffset() == timedelta(0)


def test_to_local_resta_tres_horas():
    marca = datetime(2026, 10, 12, 23, 35, tzinfo=timezone.utc)
    local = to_local(marca)
    assert (local.day, local.hour, local.minute) == (12, 20, 35)


def test_to_local_cambia_el_dia_cerca_de_medianoche():
    # 01:00 UTC = 22:00 del día anterior en hora local.
    marca = datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)
    local = to_local(marca)
    assert (local.day, local.hour, local.minute) == (13, 22, 0)


def test_is_today_dentro_del_mismo_dia_local():
    # 01:00 UTC del 14 es 22:00 del 13 en local; a las 23:00 UTC del 13 sigue siendo "hoy" (CL-12).
    marca = datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)
    ahora = datetime(2026, 10, 13, 23, 0, tzinfo=timezone.utc)
    assert is_today(marca, ahora) is True


def test_is_today_distinto_dia_local():
    marca = datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)  # 13 local
    ahora = datetime(2026, 10, 14, 20, 0, tzinfo=timezone.utc)  # 14 local
    assert is_today(marca, ahora) is False


def test_is_today_acepta_marcas_naive_como_utc():
    # Todas las marcas de la base son UTC: una marca sin huso se interpreta como UTC (RF-02).
    assert is_today(datetime(2026, 10, 14, 1, 0), datetime(2026, 10, 13, 23, 0)) is True


# --- parse_plan_entries (RF-03, CL-13, CL-14, CL-15, CL-17, CL-18) ---


@pytest.mark.parametrize(
    "tokens,esperado",
    [
        (["70"], [(70.0, None, None)]),
        (["65x3"], [(65.0, None, 3)]),
        (["65X3"], [(65.0, None, 3)]),  # separadora en mayúscula (CL-18)
        (["80-85"], [(80.0, 85.0, None)]),
        (["80-85x1"], [(80.0, 85.0, 1)]),
        (["80–85x1"], [(80.0, 85.0, 1)]),  # en-dash aceptado como guion menos (CL-15)
        (["82,5"], [(82.5, None, None)]),
        (["82.5x3"], [(82.5, None, 3)]),
        (["1x3", "70x5", "85x3"], [(1.0, None, 3), (70.0, None, 5), (85.0, None, 3)]),
        (["80-85x2", "70", "90x1"], [(80.0, 85.0, 2), (70.0, None, None), (90.0, None, 1)]),
    ],
)
def test_parse_plan_entries_validas(tokens, esperado):
    entradas = parse_plan_entries(tokens)
    assert not isinstance(entradas, str)
    assert [(e.pct_low, e.pct_high, e.reps) for e in entradas] == esperado


def test_parse_plan_entries_reps_son_int():
    entradas = parse_plan_entries(["65x3"])
    assert not isinstance(entradas, str)
    assert isinstance(entradas[0].reps, int)


def test_parse_plan_entries_lista_larga_nueve_porcentajes():
    # La lista "70 80 85" repetida debe seguir dando nueve entradas simples, en orden (CL-1).
    tokens = "70 80 85 70 80 85 70 80 85".split()
    entradas = parse_plan_entries(tokens)
    assert not isinstance(entradas, str)
    assert [e.pct_low for e in entradas] == [70, 80, 85, 70, 80, 85, 70, 80, 85]
    assert all(e.pct_high is None and e.reps is None for e in entradas)


@pytest.mark.parametrize(
    "tokens,motivo,ofensor",
    [
        (["65", "x", "3"], "va pegada", "x"),  # CL-13: "65 x 3" llega como tokens sueltos
        (["x"], "va pegada", "x"),
        (["x3"], "va pegada", "x3"),  # empieza en x
        (["65x"], "va pegada", "65x"),  # termina en x
        (["-5"], "no se aceptan negativos", "-5"),  # CL-14
        (["-80-85"], "no se aceptan negativos", "-80-85"),
        (["80-"], "rango incompleto", "80-"),
        (["65x2,5"], "no se entiende", "65x2,5"),  # reps no enteras por gramática
        (["abs"], "no se entiende", "abs"),  # texto no numérico
        (["nan"], "no se entiende", "nan"),
        (["inf"], "no se entiende", "inf"),
        (["1e3"], "no se entiende", "1e3"),  # notación científica
        (["0"], "entre 1 y 120", None),
        (["121"], "entre 1 y 120", None),
        (["85-80"], "menor que el máximo", None),
        (["80-80"], "menor que el máximo", None),  # extremos iguales también son error
        (["65x0"], "entero", None),
    ],
)
def test_parse_plan_entries_error_con_motivo_y_ejemplo(tokens, motivo, ofensor):
    aviso = parse_plan_entries(tokens)
    assert isinstance(aviso, str)
    assert motivo in aviso
    if ofensor is not None:
        assert f"'{ofensor}'" in aviso  # el valor ofensivo, entre comillas
    # RF-09: siempre termina con un ejemplo (embebido: 65x3 / 80-85, o el aviso de uso)
    assert aviso.endswith(("65x3", "80-85")) or aviso.endswith(usage_example("hoy"))


@pytest.mark.parametrize(
    "tokens,esperado",
    [
        (["x"], "'x' va pegada, sin espacios: 65x3"),
        (["-5"], "'-5' no es válido: no se aceptan negativos. Usa /hoy clean 70 80 85"),
        (["80-"], "'80-' es un rango incompleto: 80-85"),
        (["abs"], "'abs' no se entiende. Usa /hoy clean 70 80 85"),
    ],
)
def test_parse_plan_entries_mensajes_de_gramatica_texto_exacto(tokens, esperado):
    assert parse_plan_entries(tokens) == esperado


def test_parse_plan_entries_solo_el_primer_error_izquierda_a_derecha():
    # "130" (rango), "65x0" (reps) y "85-80" (invertido): solo se informa el primero (CL-17).
    aviso = parse_plan_entries(["130", "65x0", "85-80"])
    assert isinstance(aviso, str)
    assert "entre 1 y 120" in aviso
    assert "entero" not in aviso
    assert "menor que" not in aviso


def test_parse_plan_entries_orden_de_reglas_en_un_valor():
    # Gramática → porcentajes → mínimo<máximo → reps: "0x0" avisa del %, "85-80x0" del rango.
    assert "entre 1 y 120" in parse_plan_entries(["0x0"])
    assert "menor que" in parse_plan_entries(["85-80x0"])


def test_parse_plan_entries_sin_valores_devuelve_aviso_de_uso():
    assert parse_plan_entries([]) == usage_example("hoy")


def test_parse_plan_entries_reutiliza_split_exercise_and_numbers():
    # /hoy separa el nombre hasta el primer valor del plan (en T5 el splitter reconoce
    # también "65x3"); aquí los tokens llegan como los da split_exercise_and_numbers.
    split = split_exercise_and_numbers(["front squat", "70", "80-85x1"])
    assert split is not None
    ejercicio, tokens = split
    entradas = parse_plan_entries(tokens)
    assert ejercicio == "front squat"
    assert not isinstance(entradas, str)
    assert [(e.pct_low, e.pct_high, e.reps) for e in entradas] == [
        (70.0, None, None),
        (80.0, 85.0, 1),
    ]


def test_parse_plan_entries_espacios_como_en_log():
    # "/hoy clean 65 x 3": split deja los tokens sueltos y el "x" solo cae en la gramática (CL-13).
    split = split_exercise_and_numbers(["clean", "65", "x", "3"])
    assert split is not None
    _, tokens = split
    aviso = parse_plan_entries(tokens)
    assert isinstance(aviso, str)
    assert "'x' va pegada, sin espacios: 65x3" == aviso


# --- is_plan_token (T5: separación de /hoy con las cuatro sintaxis) ---


def test_is_plan_token_acepta_las_cuatro_sintaxis():
    # Los tokens que cmd_hoy le pasa al splitter (RF-03, CL-15, CL-18).
    for token in ("70", "77,5", "65x3", "65X3", "80-85", "80-85x1", "80–85", "80–85x1"):
        assert is_plan_token(token) is True, token


def test_is_plan_token_rechaza_lo_que_no_es_plan():
    # "-5" y "80-" no son valores: el comando los manda al parser (CL-14) o al nombre.
    for token in ("", "abc", "-5", "80-", "x3", "65 3", "84x5.5"):
        assert is_plan_token(token) is False, token


# --- format_start_time (RF-02, RF-03, CL-12) ---


def test_format_start_time_hoy_sin_fecha():
    # La marca de la base es UTC (RF-02): 23:35 UTC = 20:35 hora local (RF-03).
    ahora = datetime(2026, 10, 10, 21, 0)
    assert format_start_time("2026-10-10T23:35:00", ahora) == "las 20:35"


def test_format_start_time_otro_dia_con_fecha():
    ahora = datetime(2026, 10, 10, 9, 0)
    assert format_start_time("2026-10-09T23:35:00", ahora) == "el 09/10 a las 20:35"


def test_format_start_time_cerca_de_medianoche_utc_sigue_siendo_hoy():
    # CL-12: sesión a las 22:00 locales (01:00 UTC del día siguiente) es "hoy".
    ahora = datetime(2026, 10, 11, 1, 30)  # 01:30 UTC = 22:30 locales del 10/10
    assert format_start_time("2026-10-11T01:00:00", ahora) == "las 22:00"


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


def test_format_log_confirmation_con_rango_y_reps_del_plan():
    # RF-04, A-1: el sufijo del plan lleva rango y reps cuando la serie los trae.
    assert (
        format_log_confirmation("clean", 1, 82.0, 1, 64.0, 68.0, 1)
        == "clean · serie 1: 82 kg × 1 (plan 64-68 kg × 1)"
    )
    assert (
        format_log_confirmation("clean", 1, 66.0, 3, 65.0, None, 3)
        == "clean · serie 1: 66 kg × 3 (plan 65 kg × 3)"
    )


# --- convert_plan_entries (RF-03, CL-16) ---


def test_convert_plan_entries_valor_solo():
    sets = convert_plan_entries(120, [PlanEntry(70.0, None, None)])
    assert [(s.weight_kg, s.range_max_kg, s.reps) for s in sets] == [(84.0, None, None)]


def test_convert_plan_entries_con_reps():
    sets = convert_plan_entries(120, [PlanEntry(65.0, None, 3)])
    assert [(s.weight_kg, s.range_max_kg, s.reps) for s in sets] == [(78.0, None, 3)]


def test_convert_plan_entries_rango_se_redondea_por_extremo():
    # RM 80 con 80-85% → 64 y 68 (caso de la spec).
    sets = convert_plan_entries(80, [PlanEntry(80.0, 85.0, None)])
    assert [(s.weight_kg, s.range_max_kg, s.reps) for s in sets] == [(64.0, 68.0, None)]


def test_convert_plan_entries_rango_colapsa_si_los_extremos_coinciden():
    # RM 50 con 80-80,2% → 40,0 y 40,0 → colapsa a valor único sin rango (CL-16).
    sets = convert_plan_entries(50, [PlanEntry(80.0, 80.2, None)])
    assert [(s.weight_kg, s.range_max_kg) for s in sets] == [(40.0, None)]


def test_convert_plan_entries_empate_de_redondeo_no_colapsa():
    # RM 50 con 80-80,5% → 40,0 y 40,5: 40,25 es empate y los empates van hacia arriba
    # (round_half_kg, RF-05 de la 001); no colapsan extremos distintos.
    sets = convert_plan_entries(50, [PlanEntry(80.0, 80.5, None)])
    assert [(s.weight_kg, s.range_max_kg) for s in sets] == [(40.0, 40.5)]


def test_convert_plan_entries_kilos_con_decimal_y_coma():
    # RM 32 con 70% → 22,4 → 22,5 kg (redondeo a 0,5).
    sets = convert_plan_entries(32, [PlanEntry(70.0, None, None)])
    assert [s.weight_kg for s in sets] == [22.5]
    assert format_kg(sets[0].weight_kg) == "22,5"


def test_convert_plan_entries_lista_larga_completa_y_en_orden():
    entries = parse_plan_entries("70 80 85 70 80 85 70 80 85".split())
    assert not isinstance(entries, str)
    sets = convert_plan_entries(100, entries)
    assert [s.weight_kg for s in sets] == [70, 80, 85, 70, 80, 85, 70, 80, 85]


# --- format_hoy_lines (RF-03, A-1, CL-19) ---


def test_format_hoy_lines_sin_reps():
    entries = [PlanEntry(70.0, None, None)]
    sets = [PlannedSet(84.0, None, None)]
    assert format_hoy_lines(entries, sets) == "70% → 84 kg"


def test_format_hoy_lines_con_reps():
    entries = [PlanEntry(65.0, None, 3)]
    sets = [PlannedSet(52.0, None, 3)]
    assert format_hoy_lines(entries, sets) == "65% × 3 → 52 kg"


def test_format_hoy_lines_con_rango():
    entries = [PlanEntry(80.0, 85.0, None)]
    sets = [PlannedSet(64.0, 68.0, None)]
    assert format_hoy_lines(entries, sets) == "80-85% → 64-68 kg"


def test_format_hoy_lines_con_rango_y_reps():
    entries = [PlanEntry(80.0, 85.0, 1)]
    sets = [PlannedSet(64.0, 68.0, 1)]
    assert format_hoy_lines(entries, sets) == "80-85% × 1 → 64-68 kg"


def test_format_hoy_lines_porcentaje_con_decimal_usa_coma():
    entries = [PlanEntry(77.5, None, None)]
    sets = [PlannedSet(62.0, None, None)]
    assert format_hoy_lines(entries, sets) == "77,5% → 62 kg"


def test_format_hoy_lines_kilos_con_decimal_usan_coma():
    entries = [PlanEntry(70.0, None, None)]
    sets = convert_plan_entries(32, entries)  # 22,4 → 22,5 kg
    assert format_hoy_lines(entries, sets) == "70% → 22,5 kg"


def test_format_hoy_lines_rango_colapsado_muestra_valor_unico():
    # Los % siguen mostrando el rango pedido; los kilos, el valor único colapsado (CL-16).
    entries = [PlanEntry(80.0, 80.2, None)]
    sets = convert_plan_entries(50, entries)
    assert format_hoy_lines(entries, sets) == "80-80,2% → 40 kg"


def test_format_hoy_lines_varias_lineas_en_orden():
    entries = parse_plan_entries(["70", "65x3", "80-85x1"])
    assert not isinstance(entries, str)
    sets = convert_plan_entries(100, entries)
    texto = format_hoy_lines(entries, sets)
    assert texto.splitlines() == [
        "70% → 70 kg",
        "65% × 3 → 65 kg",
        "80-85% × 1 → 80-85 kg",
    ]


# --- format_plan_suffix (RF-04, A-1) ---


@pytest.mark.parametrize(
    "planned,max_kg,reps,esperado",
    [
        (84.0, None, None, " (plan 84)"),  # igual que la 001
        (66.0, None, 1, " (plan 66 kg × 1)"),
        (64.0, 68.0, 1, " (plan 64-68 kg × 1)"),
        (64.0, 68.0, None, " (plan 64-68)"),  # rango sin reps no lleva kg
        (80.0, None, 3, " (plan 80 kg × 3)"),
        (22.5, None, None, " (plan 22,5)"),
        (22.5, None, 2, " (plan 22,5 kg × 2)"),
        (None, None, None, ""),  # sin plan no añade nada
        (None, None, 1, ""),  # rango sin plan (NULL) no muestra nada raro
        (None, 68.0, None, ""),
    ],
)
def test_format_plan_suffix(planned, max_kg, reps, esperado):
    assert format_plan_suffix(planned, max_kg, reps) == esperado


# --- pares con rango en build_summary (RF-05, A-3) ---


def test_build_summary_par_de_rango_desde_la_serie():
    series = [
        {
            "exercise": "front squat",
            "real_weight": 66,
            "reps": 2,
            "planned_weight": 64,
            "planned_max_kg": 68,
            "planned_reps": 2,
        }
    ]
    texto = build_summary(INICIO, INICIO + timedelta(minutes=10), series)
    assert "64-68→66" in texto


def test_build_summary_serie_v1_sin_maximo_da_par_simple():
    # Series existentes (sin planned_max_kg): el par sigue como en la 001 (CL-9).
    series = [
        {
            "exercise": "front squat",
            "real_weight": 66,
            "reps": 2,
            "planned_weight": 64,
        }
    ]
    texto = build_summary(INICIO, INICIO + timedelta(minutes=10), series)
    assert "64→66" in texto


def test_build_summary_maximo_sin_plan_no_da_par():
    # Dato imposible por esquema, pero la lectura no debe mostrar nada raro.
    series = [
        {
            "exercise": "front squat",
            "real_weight": 66,
            "reps": 2,
            "planned_weight": None,
            "planned_max_kg": 68,
        }
    ]
    texto = build_summary(INICIO, INICIO + timedelta(minutes=10), series)
    assert "plan→real" not in texto


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
        "/historial",  # 003 (RF-01): la ayuda gana /historial con el menú único
    ):
        assert comando in texto


# --- COMMAND_MENU y sincronización con /ayuda (RF-01, spec 003) ---


def test_menu_del_bot_es_los_diez_comandos_v03():
    comandos = [nombre for nombre, _ in COMMAND_MENU]
    assert comandos == [
        "perfil",
        "rm",
        "rms",
        "inicio",
        "hoy",
        "log",
        "deshacer",
        "historial",
        "fin",
        "ayuda",
    ]
    assert len(set(comandos)) == len(comandos)  # sin duplicados


def test_menu_del_bot_descripciones_no_vacias_y_max_25_caracteres():
    for nombre, descripcion in COMMAND_MENU:
        assert descripcion, nombre  # no vacía
        assert descripcion == descripcion.strip(), nombre  # sin espacios sueltos
        assert len(descripcion) <= 25, nombre  # límite de Telegram (RF-01)


def test_menu_y_ayuda_comparten_comandos_y_descripciones():
    texto = help_text()
    assert texto.startswith("Comandos disponibles:")
    for nombre, descripcion in COMMAND_MENU:
        assert f"/{nombre} — {descripcion}" in texto  # mismo texto en los dos sitios
    assert texto.count("\n") == len(COMMAND_MENU)  # cabecera + una línea por comando


def test_usage_example_historial_aviso_corto_v03():
    assert usage_example("historial") == "Usa /historial (sin nada más)"


# --- is_log_token: forma del registro suelto (RF-02, spec 003) ---


@pytest.mark.parametrize(
    "texto",
    ["52x3", "52,5x3", "52.5X3", "100x1", "52x0", "52x", "x3", "-5x3", "52x3,5", "1e3x5"],
)
def test_is_log_token_con_forma_de_pesoxreps(texto):
    """Tiene forma de registro: lo registra o lo rechaza /log con su aviso (RF-09)."""
    assert is_log_token(texto) is True


@pytest.mark.parametrize(
    "texto",
    ["52x3?", "52x3.", "52 3", "mañana 52x3", "52x3 52x3", "hola", ""],
)
def test_is_log_token_texto_libre_no_tiene_forma(texto):
    """Sin forma de registro: va a la lista de comandos (RF-12 modificado)."""
    assert is_log_token(texto) is False


# --- group_series_by_exercise y exercise_stat_line (RF-03, spec 003) ---


def test_exercise_stat_line_con_el_mismo_formato_que_el_resumen():
    items = [
        {"exercise": "clean", "real_weight": 84.0, "reps": 5},
        {"exercise": "clean", "real_weight": 96.0, "reps": 3},
    ]
    assert (
        exercise_stat_line(items)
        == "clean: 2 series · 8 repeticiones · volumen 708 kg · máx 96 kg"
    )


def test_exercise_stat_line_serie_unica_y_sin_pares_de_plan():
    items = [
        {
            "exercise": "back squat",
            "real_weight": 100.0,
            "reps": 1,
            "planned_weight": 95.0,
            "planned_max_kg": 98.0,
        }
    ]
    linea = exercise_stat_line(items)
    assert linea == "back squat: 1 serie · 1 repetición · volumen 100 kg · máx 100 kg"
    assert "plan" not in linea  # los pares los añade build_summary, no la línea


def test_group_series_by_exercise_ordena_por_la_primera_serie():
    series = [
        {"exercise": "Clean", "real_weight": 84.0, "reps": 5},
        {"exercise": "back squat", "real_weight": 100.0, "reps": 2},
        {"exercise": "clean", "real_weight": 96.0, "reps": 3},
    ]
    grupos = group_series_by_exercise(series)
    assert [clave for clave, _ in grupos] == ["clean", "back squat"]
    assert [len(items) for _, items in grupos] == [2, 1]  # Clean y clean, juntos


# --- funciones puras del dashboard (T1, spec 004: RF-02, RF-03, RF-05) ---

HOY = date(2026, 10, 17)


@pytest.mark.parametrize(
    "marca, esperado",
    [
        ("2026-10-17T01:30", date(2026, 10, 16)),  # 01:30 UTC = 22:30 local del 16
        ("2026-10-17T01:30Z", date(2026, 10, 16)),  # lo mismo con la marca en Z
        ("2026-10-16T23:30Z", date(2026, 10, 16)),  # 20:30 local, mismo día
        ("2026-10-17T03:00", date(2026, 10, 17)),  # 03:00 UTC = 00:00 local, mismo día
        ("2026-11-01T01:00", date(2026, 10, 31)),  # 01:00 UTC del 1/11 = 31/10 local
        ("2026-11-01T03:00", date(2026, 11, 1)),  # ya es noviembre en local
        ("2026-10-16T12:00", date(2026, 10, 16)),
    ],
)
def test_local_date_marca_utc_es_fecha_local(marca, esperado):
    """CL-6: el día se decide en local (UTC-3), nunca en UTC."""
    assert local_date(marca) == esperado


@pytest.mark.parametrize(
    "dias, esperado",
    [
        (set(), (0, False)),  # base vacía
        ({HOY}, (1, False)),  # solo hoy
        (
            {HOY - timedelta(days=2), HOY - timedelta(days=1), HOY},
            (3, False),  # 3 días consecutivos terminados hoy
        ),
        (
            {HOY, HOY - timedelta(days=1), HOY - timedelta(days=3)},
            (2, False),  # hueco de un día: la racha no lo salta
        ),
        (
            {HOY - timedelta(days=1), HOY - timedelta(days=2), HOY - timedelta(days=4)},
            (2, True),  # hueco detrás de ayer: viva hasta ayer, sin saltarlo
        ),
        ({HOY - timedelta(days=1)}, (1, True)),  # hoy sin entrenar y ayer sí: viva
        ({HOY - timedelta(days=3)}, (0, False)),  # hoy ni ayer: racha 0
        ({HOY, HOY - timedelta(days=2)}, (1, False)),  # hueco justo detrás de hoy
    ],
)
def test_streak_days(dias, esperado):
    """(racha, falta_hoy): consecutivos desde hoy o ayer (RF-02, CL-4, CL-5)."""
    assert streak_days(dias, HOY) == esperado


def _dias_de_sesiones(marcas: list[str]) -> set[date]:
    """El set que arma el payload: fecha local de inicio de cada sesión (CL-3)."""
    return {local_date(m) for m in marcas}


def test_racha_dos_sesiones_el_mismo_dia_cuentan_una_vez():
    dias = _dias_de_sesiones(["2026-10-17T11:00", "2026-10-17T19:00"])
    assert len(dias) == 1
    assert streak_days(dias, HOY) == (1, False)


def test_racha_sesion_abierta_de_hoy_cuenta():
    dias = _dias_de_sesiones(["2026-10-17T14:00"])  # abierta hoy
    assert streak_days(dias, HOY) == (1, False)


def test_racha_sesion_abierta_olvidada_no_arrasra():
    # Abierta hace 5 días: cuenta solo su día de inicio; ayer sí entrené.
    dias = _dias_de_sesiones(["2026-10-12T09:00", "2026-10-16T18:00"])
    assert streak_days(dias, HOY) == (1, True)  # no arrastra 12→17
    # Solo la olvidada y nada reciente: la racha no se infla.
    assert streak_days(_dias_de_sesiones(["2026-10-12T09:00"]), HOY) == (0, False)


@pytest.mark.parametrize(
    "marcas, esperado",
    [
        ([], 0),
        (
            ["2026-10-17T11:00", "2026-10-17T19:00", "2026-10-20T11:00"],
            3,  # duplicados: dos sesiones un mismo día cuentan dos
        ),
        (["2026-11-01T01:00"], 1),  # 01:00 UTC del 1/11 sigue siendo 31/10 local
        (["2026-11-01T03:00"], 0),  # 03:00 UTC del 1/11 ya es noviembre
        (["2026-09-30T12:00", "2026-11-01T12:00"], 0),  # meses contiguos, no cuentan
    ],
)
def test_count_month(marcas, esperado):
    """Mes en curso local por fecha de inicio, con duplicados (RF-02, CL-6, CL-7)."""
    dias = [local_date(m) for m in marcas]
    assert count_month(dias, HOY) == esperado


def test_percentage_table_11_filas_y_dos_columnas():
    columnas, filas = percentage_table([("clean", 120.0), ("front squat", 80.0)])
    assert columnas == ["clean", "front squat"]  # el orden de la entrada
    assert len(filas) == 11  # 50 % a 100 % en pasos de 5
    assert filas[0] == [60.0, 40.0]  # 50 %
    assert filas[4] == [84.0, 56.0]  # 70 %
    assert filas[-1] == [120.0, 80.0]  # 100 %


def test_percentage_table_redondea_a_un_medio_kilo():
    # RM 81: mitades exactas y residuos al 0,5 más cercano, empates hacia arriba.
    _, filas = percentage_table([("clean", 81.0)])
    assert [fila[0] for fila in filas] == [
        40.5, 44.5, 48.5, 52.5, 56.5, 61.0, 65.0, 69.0, 73.0, 77.0, 81.0,
    ]


def test_percentage_table_sin_rm_no_hay_tabla():
    assert percentage_table([]) == ([], [])


def test_percentage_table_solo_los_ejercicios_recibidos():
    # El payload pasa solo los ejercicios con RM vigente (CL-15): no se inventa
    # ninguna columna.
    columnas, filas = percentage_table([("clean", 120.0)])
    assert columnas == ["clean"]
    assert len(filas) == 11
    assert all(len(fila) == 1 for fila in filas)


def test_max_load_points_sin_puntos():
    assert max_load_points([]) == {}


def test_max_load_points_un_punto():
    filas = [{"date": date(2026, 10, 16), "exercise": "clean", "max_kg": 66.0}]
    assert max_load_points(filas) == {"clean": [(date(2026, 10, 16), 66.0)]}


def test_max_load_points_varios_puntos_por_ejercicio():
    filas = [
        {"date": date(2026, 10, 16), "exercise": "clean", "max_kg": 66.0},
        {"date": date(2026, 10, 16), "exercise": "front squat", "max_kg": 80.0},
        {"date": date(2026, 10, 18), "exercise": "clean", "max_kg": 70.0},
    ]
    assert max_load_points(filas) == {
        "clean": [(date(2026, 10, 16), 66.0), (date(2026, 10, 18), 70.0)],
        "front squat": [(date(2026, 10, 16), 80.0)],
    }


def _fila_serie(real, planned, max_kg=None, reps=5, planned_reps=None):
    return {
        "exercise": "clean",
        "real_weight": real,
        "reps": reps,
        "planned_weight": planned,
        "planned_max_kg": max_kg,
        "planned_reps": planned_reps,
    }


@pytest.mark.parametrize(
    "series, esperado",
    [
        ([_fila_serie(52.0, 80.0, max_kg=85.0, planned_reps=1)], ["80-85→52"]),  # rango
        ([_fila_serie(66.0, 70.0)], ["70→66"]),  # un solo valor
        ([_fila_serie(82.0, 84.0)], ["84→82"]),  # con reps: no se muestran
        ([_fila_serie(52.5, 70.0)], ["70→52,5"]),  # coma decimal (RF-01)
        ([_fila_serie(98.0, 96.0)], ["96→98"]),  # fila v1: reps y máx en NULL
        ([_fila_serie(84.0, None)], []),  # sin plan no aporta par
        ([{"real_weight": 66.0, "planned_weight": 70.0}], ["70→66"]),  # dict mínimo
        (
            [
                _fila_serie(66.0, 70.0),
                _fila_serie(52.0, None),
                _fila_serie(52.0, 80.0, max_kg=85.0),
            ],
            ["70→66", "80-85→52"],  # solo las que tienen plan, en orden
        ),
    ],
)
def test_plan_real_pairs(series, esperado):
    """Misma lógica que la línea de /fin (RF-05): extraída, no reimplementada."""
    assert plan_real_pairs(series) == esperado
