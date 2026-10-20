# Plan 003 — UX del bot: menú, mensaje suelto, /historial y aviso de error (BoxLog v0.3)

Complementa a `spec.md` (spec.md manda en el QUÉ; este archivo solo define el CÓMO).

Sin dependencias nuevas, sin migración y sin tocar la base real: la 003 es lógica y
cableado sobre datos que ya existen.

## 1. Resumen de cambios por archivo

| Archivo | Funciones nuevas o modificadas | Por qué | RF |
|---|---|---|---|
| `boxlog/core.py` | **Nuevos:** `COMMAND_MENU` (constante única: 10 tuplas (comando, descripción ≤25 caracteres)), `is_log_token(texto)` (¿tiene forma de `<peso>x<repeticiones>`?), `exercise_stat_line(items)` (línea por ejercicio, extraída de `build_summary` con la misma salida) y las constantes de texto `INTERNAL_ERROR_TEXT`, `FREE_NO_SERIES`, `HISTORIAL_EMPTY`, `HISTORIAL_MAX_CHARS`. **Modificadas:** `help_text()` (construida desde `COMMAND_MENU`) y `_USAGE_EXAMPLES` (+ "historial"). | Toda la lógica nueva y todos los textos fijos viven en la capa pura (constitución 3). Solo se añade el import de `re`, ya presente. | RF-01, RF-02, RF-03, RF-04 |
| `boxlog/commands.py` | **Nuevas:** `cmd_free_text(connection, args)` (registro suelto, delegando en `cmd_log`) y `cmd_historial(connection, args)`. | Orquestación: valida con core, consulta con db, devuelve texto. Sin imports de la librería de Telegram (constitución 3). | RF-02, RF-03 |
| `boxlog/db.py` | **Nueva:** `get_recent_sessions(connection, closed_limit=5)` (sesión abierta primero, si la hay, y después las últimas cerradas de más reciente a más antigua), con el mismo patrón de consulta que las lecturas existentes. **Sin cambios de esquema.** | Solo lectura sobre `sessions` y reutilización de `list_series` (CL: /historial no cambia nada). | RF-03 |
| `boxlog/bot.py` | **Modificadas:** `dispatch` (cuando `command` es `None` llama a `cmd_free_text` con el texto crudo en `args`), el handler de texto libre (pasa el mensaje con `strip()`), `COMMANDS` (+ "historial") y `on_error` (aviso genérico en el chat si el error no es de red). **Nuevas:** `error_notice(error)` (puro, testeable sin red) y `publish_menu(app)` (publica el menú vía `post_init` con `try/except`: si falla, solo se loguea y el bot arranca igual). | La interfaz solo decide a qué comando enruta y qué error mostrar; nunca valida pesos ni compone respuestas (constitución 3). | RF-01, RF-02, RF-04 |
| `tests/` | `test_core.py` (constante del menú, `is_log_token`, `exercise_stat_line`, + test de help_text de la 001 actualizado), `test_commands.py` (`cmd_free_text`, `cmd_historial`), `test_db.py` (`get_recent_sessions`), `test_bot.py` (despacho con texto crudo, ajeno con suelto, `error_notice`, `publish_menu`, + 2 tests de la 001 adaptados), `test_e2e.py` (e2e del suelto con plan y tras /deshacer). | Tests primero (constitución 4). | Todos |

`requirements.txt`, `.gitignore` y `.env.example` **no cambian** (RNF-3: `re` es stdlib y el
menú usa el `set_my_commands` de python-telegram-bot ya instalado).

## 2. Constante única del menú y /ayuda (RF-01)

En `core.py`, una sola fuente de verdad compartida por `set_my_commands` (bot.py) y
`help_text()`:

```python
COMMAND_MENU: tuple[tuple[str, str], ...] = (
    ("perfil", "Peso (kg) y altura (cm)"),      # 23
    ("rm", "RM en kg de un ejercicio"),         # 24
    ("rms", "Lista los RM vigentes"),           # 21
    ("inicio", "Abre la sesión de entreno"),    # 25
    ("hoy", "Kilos por % de tu RM"),            # 20
    ("log", "Serie: peso kg x reps"),           # 21
    ("deshacer", "Borra la última serie"),      # 21
    ("historial", "Últimas sesiones"),           # 16
    ("fin", "Cierra y resume la sesión"),        # 25
    ("ayuda", "Lista de comandos"),             # 17
)
```

(Los números son la longitud en caracteres; todas ≤25, el límite de Telegram. El test de
sincronía la comprueba con `len()`, que cuenta los acentos como 1 carácter.)

- `help_text()` pasa a construirse con una línea por entrada:
  `"Comandos disponibles:"` + `f"/{name} — {desc}"` → la ayuda y el menú muestran
  **exactamente** los mismos comandos con los mismos textos (test de sincronía trivial).
- `/start` sigue aliasando a `/ayuda` y no tiene entrada propia en el menú (decisión Q6).
- `publish_menu(app)` en bot.py llama a `app.bot.set_my_commands(core.COMMAND_MENU)` al
  arrancar (`Application.builder().post_init(publish_menu)`), envuelto en `try/except`:
  un fallo (p. ej. de red) se loguea con solo el tipo de excepción y **no impide que el
  bot arranque** (RNF-2 y §8, riesgo R5).
- Los ejemplos de uso concretos siguen llegando por los avisos de RF-09
  (`_USAGE_EXAMPLES`, que gana la entrada `"historial": "Usa /historial (sin nada más)"`).

## 3. Registro suelto (RF-02): token, ejercicio y reutilización de /log

**Reconocimiento puro en core** (dos regex, sin duplicar la validación de /log):

```python
_LOG_SHAPE_RE = re.compile(r"^[0-9]+([.,][0-9]+)?[xX][0-9]*([.,][0-9]+)?$")
_LOG_ALMOST_RE = re.compile(r"^[0-9A-Za-z.,]+[xX][0-9A-Za-z.,]+$")

def is_log_token(texto: str) -> bool:
    """¿Tiene forma de <peso>x<repeticiones> para el registro suelto (RF-02)?

    True si es la forma estricta de dos números, o si intenta serlo con letras
    ("1e3x5": notación científica, que se rechaza después con el aviso de RF-09,
    no como texto libre). El resto ("52x3?", "52x3.") no tiene forma y va a la
    ayuda (RF-12 modificado).
    """
    if _LOG_SHAPE_RE.match(texto):
        return True
    return bool(_LOG_ALMOST_RE.match(texto) and any(c.isalpha() for c in texto))
```

Tabla de decisiones (también test parametrizado):

| texto | `is_log_token` | resultado en el chat |
|---|---|---|
| `52x3` | True | serie con la mecánica de /log (CL-5/CL-7 según sesión) |
| `52,5X3` | True | serie; coma decimal y X mayúscula (CL-3) |
| `52x0` | True | aviso de RF-09 (reps) (CL-4) |
| `52x` | True | aviso de RF-09 (faltan reps) (CL-4) |
| `5x2,5` | True | aviso de RF-09 (reps no enteras) (CL-4) |
| `600x3` | True | aviso de RF-09 (peso fuera de rango) (CL-4) |
| `1e3x5` | True | aviso de RF-09 (notación científica) (CL-4) |
| `52x3?` | False | lista de comandos (CL-2) |
| `52x3.` | False | lista de comandos (CL-2) |
| `52 3` (con espacios internos) | False | lista de comandos (CL-1) |

**En commands.py, delegando en /log** (sin duplicar validaciones, RM, plan ni confirmación):

```python
def cmd_free_text(connection: sqlite3.Connection, args: list[str]) -> str:
    """Registro suelto (RF-02): un único token con forma de pesoxreps.

    Usa el ejercicio de la última serie de la sesión abierta y delega en cmd_log:
    misma validación, misma confirmación y mismo plan que /log (RF-06 de la 001).
    """
    if len(args) != 1 or not core.is_log_token(args[0]):
        return core.help_text()
    session = db.get_open_session(connection)
    if session is None:
        return core.NO_OPEN_SESSION                      # aviso de CL-2 (la 001)
    serie = db.get_last_series(connection, session["id"])
    if serie is None:
        return core.FREE_NO_SERIES                       # CL-6, sin adivinar
    return cmd_log(connection, [serie["exercise"], args[0]])
```

- `cmd_log` ya hace todo lo demás: sesión abierta → separar nombre/números →
  `parse_log_args` → `validate_rm_value`/`validate_reps` (avisos de RF-09 con motivo y
  ejemplo) → RM → `db.insert_series` (copia del plan) → confirmación. Por eso CL-3 y CL-4
  salen gratis y sin duplicar lógica.
- El ejercicio sale de `db.get_last_series` (ya lo usa `/deshacer`): "la última serie de
  la sesión abierta" (RF-02) y, tras un `/deshacer`, pasa a ser la anterior (CL-7) sin
  código nuevo.
- Orden de comprobaciones: forma → sesión → series → cmd_log. Un "52x0" sin sesión
  responde primero el aviso de CL-2, igual que /log en la 001.
- Texto nuevo único: `core.FREE_NO_SERIES = "Aún no hay series en esta sesión. Registra
  una con /log <ejercicio> <peso>x<reps>"` (CL-6).

## 4. /historial (RF-03)

**db.get_recent_sessions(connection, closed_limit=5)**: dos SELECT en el estilo de las
lecturas existentes — la sesión abierta (`ended_at IS NULL`) y las últimas `closed_limit`
cerradas (`ORDER BY id DESC LIMIT ?`) — devueltas en ese orden. Los ejercicios de cada
sesión salen de `list_series` (ya existe y ya devuelve los campos de plan de la 002):
≤6 consultas extra, aceptadas por simplicidad frente a un JOIN (§9).

**commands.cmd_historial(connection, args)**:

1. Con argumentos → `core.usage_example("historial")` (CL-12, igual que /fin y /deshacer).
2. Sin sesiones → `core.HISTORIAL_EMPTY = "Aún no hay sesiones. Abre la primera con
   /inicio"` (CL-9).
3. Bloque por sesión:
   - Cabecera cerrada: `f"{to_local(inicio):%d/%m} · {core.format_duration(segundos)}"`
     con las marcas UTC parseadas y restadas igual que `cmd_fin` → "13/10 · 1 h 11 min".
   - Cabecera abierta (arriba, marcada): `f"{to_local(inicio):%d/%m} · abierta desde las
     {to_local(inicio):%H:%M}"` → "19/10 · abierta desde las 20:35" (CL-10). Horas en
     local siempre vía `to_local` (RF-02 de la 002).
   - Una línea por ejercicio con `core.exercise_stat_line(items)`:
     "clean: 2 series · 8 repeticiones · volumen 708 kg · máx 96 kg" — el mismo formato
     por ejercicio del resumen de /fin, **sin** pares plan→real (los añade aparte
     `build_summary`; aquí no se muestran, CL-14).
4. Tope (CL-11): los bloques se concatenan de más reciente a más antigua; si el mensaje
   supera `core.HISTORIAL_MAX_CHARS` (3800) se descarta la cerrada más antigua del
   conjunto y se reintenta. **Nunca** se parte en dos mensajes; siempre quedan la sesión
   abierta (si hay) y la más reciente. Fallback extremo en §9.

**Extracción sin romper la 001:** `core.exercise_stat_line(items)` se extrae del bucle de
`build_summary` con la **misma salida**; `build_summary` la usa y su texto no cambia (los
tests de resumen de la 001 y el e2e de la 002 siguen verdes sin tocarlos).

## 5. Aviso de error interno y publicación del menú (RF-04)

En bot.py, con la distinción en una función pura testeable sin red:

```python
def error_notice(error: BaseException) -> str | None:
    """Aviso genérico para el chat (RF-04): None si es de red/timeout (solo log)."""
    if isinstance(error, (NetworkError, TimedOut)):
        return None
    return core.INTERNAL_ERROR_TEXT
```

- `INTERNAL_ERROR_TEXT = "⚠️ Algo salió mal; no se ha perdido nada. Inténtalo de nuevo."`
  vive en core (texto fijo, puro y testeable).
- `on_error(update, context)`: **siempre** loguea con `format_error_log` (token redactado,
  como ahora); después `aviso = error_notice(context.error)` y, si hay aviso y existe
  `update.effective_message`, responde con `try/except` (un fallo de red al avisar no
  debe romper nada). El chat **nunca** ve `str(error)` ni traceback (RNF-2).
- Los errores de red/timeout siguen solo en el log (Q5): la librería reintenta sola y un
  aviso con la red caída también fallaría.
- `publish_menu(app)` (§2) se engancha con `post_init`; su `except` loguea un mensaje
  fijo con `type(exc).__name__` (sin `str(exc)`, RNF-2) y deja arrancar el bot.

## 6. Cambio de despacho y tests de la 001 que cambian

**La firma de `dispatch(user_id, owner_id, command, args, connection)` NO cambia**: solo
cambia el contrato de `args` cuando `command is None` — ahora lleva un único elemento, el
texto crudo del mensaje (con `strip()` aplicado por el handler):

```python
if user_id != owner_id:
    return None
if command is None:
    handler = commands.cmd_free_text
else:
    handler = COMMANDS.get(command)
    if handler is None:
        return core.usage_example(command)   # comandos desconocidos → lista (RF-12)
return handler(connection, args)
```

Tests de la 001 que cambian (lista ya fijada en la spec):

1. `tests/test_bot.py::test_dispatch_texto_libre_devuelve_la_ayuda` (línea 69): pasa a
   cubrir el registro suelto (`["52x3"]` → serie; `["mañana hago 52x3"]` → ayuda) —
   RF-12 modificado por la 003.
2. `tests/test_bot.py::test_dispatch_persona_ajena_comando_desconocido_tampoco` (línea
   61): solo cambia la llamada por el contrato de `args`; la aserción (ajeno → silencio,
   RF-08) queda igual.
3. `tests/test_core.py::test_help_text_lista_todos_los_comandos_v01` (línea 818): /ayuda
   sale de la constante y gana /historial — RF-01 (T1).

Ningún otro test de la 001 cambia: los de /start y /ayuda comparan contra `help_text()`
dinámico y los de comando desconocido → ayuda siguen idénticos.

## 7. Estrategia de pruebas (pytest, primero y en verde)

Mismo patrón que la 002: en cada tarea se escriben los tests antes que el código, se
verifica el fallo y no se avanza hasta dejar `python -m pytest` completo en verde. Nada
requiere red: `publish_menu` y `on_error` se prueban con objetos falsos y con las clases
reales `NetworkError`/`TimedOut` de `telegram.error` (no lanzan por sí solas); las horas
del historial se fijan con monkeypatch de marcas UTC (patrón de la 002).

## 8. Orden de implementación y riesgos (cómo se prueba cada uno)

Orden (detalle en `tasks.md`): T1 menú + /ayuda → T2 registro suelto (core+commands) →
T3 /historial (db+commands) → T4 bot (texto crudo, historial cableado, aviso de error,
menú publicado) → T5 cierre (e2e + docs).

| # | Riesgo | Cómo se prueba |
|---|---|---|
| R1 | Registro accidental por texto que no es un registro (CL-1, CL-2) | Tests parametrizados de `is_log_token` y de `cmd_free_text` ("mañana hago 52x3" → ayuda; "52x3?" → ayuda; "52x3" → serie) + e2e de T5 |
| R2 | El cambio de despacho rompe tests de la 001 | Los 3 tests listados en §6 se adaptan con su motivo; el resto de la suite debe quedar verde sin tocarse |
| R3 | `help_text` cambia de redacción | Test de sincronía (menú == ayuda, ≤25 chars por descripción) + el test de help de la 001 actualizado; los tests dinámicos no se tocan |
| R4 | `on_error` con `update` None o `reply_text` que falla | `error_notice` puro (None para NetworkError/TimedOut) + `try/except` al responder; test con update falso sin mensaje y con reply que lanza |
| R5 | `set_my_commands` falla al arrancar | Test con app falsa cuyo `set_my_commands` lanza: `asyncio.run(publish_menu(...))` no propaga y se loguea el tipo de error → el bot arranca igual |
| R6 | /historial no cabe en un mensaje | Test con muchas sesiones largas: longitud ≤3800, sin partir, la sesión más reciente completa |
| R7 | Hora equivocada en /historial | Marcas UTC fijadas por monkeypatch → el texto muestra hora y fecha locales y duración correctas |

## 9. Supuestos y detalles menores

- El handler de texto libre pasa el mensaje con `strip()`: un "52x3 " con espacios
  finales registra; los espacios **internos** ("52 3", "52x3") siguen dando la ayuda
  (CL-1).
- `help_text` pierde los ejemplos de sintaxis ("<peso> <altura>") a cambio de ser
  exactamente el menú (misma fuente, RF-01); el uso concreto siguen dándolo los avisos de
  RF-09 ("Usa /log clean 84x5").
- /historial consulta una vez por sesión (N+1 con ≤6 sesiones) reutilizando
  `list_series`: más simple que un JOIN y sin riesgo de romper lecturas de la 001.
- Fallback de longitud: si una sola sesión superara los 3800 caracteres (improbable: la
  sesión tendría cientos de ejercicios), se envía esa sesión con "…" final; nunca dos
  mensajes.
- El menú se publica al arrancar (`post_init`); no hay refresh periódico ni se re-publica
  al cambiar comandos (solo al reiniciar el bot).
- "/historial 5" y demás argumentos de más usan el mismo aviso de RF-09 que /fin y
  /deshacer; la constante `_USAGE_EXAMPLES` es la fuente.
- El estado intermedio entre T1 y T4 es deliberado (patrón de la 002): /ayuda ya anuncia
  /historial antes de que T4 lo cable en `COMMANDS`; no se arranca el bot real en ese
  tramo.
