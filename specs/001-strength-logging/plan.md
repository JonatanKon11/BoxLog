# Plan 001 — v0.1 Fuerza (BoxLog)

Complementa a `spec.md` (spec.md manda en el QUÉ; este archivo solo define el CÓMO).

## 1. Archivos y responsabilidades

| Archivo | Responsabilidad | RF |
|---|---|---|
| `boxlog/core.py` | Funciones puras: parseo y validación de argumentos, cálculos y formato de mensajes. Sin Telegram ni SQLite. | RF-01, RF-04, RF-05, RF-06, RF-09, RF-10, RF-11, RF-12 |
| `boxlog/db.py` | Todo el acceso a SQLite: crear esquema y consultas/escrituras. Sin lógica de negocio ni texto de respuesta. | RF-01, RF-02, RF-03, RF-04, RF-06, RF-07, RNF-3 |
| `boxlog/commands.py` | Orquestación por comando: valida con `core`, persiste con `db` y devuelve el texto de respuesta. Sin imports de Telegram. | RF-01 a RF-07, RF-09, RF-12 |
| `boxlog/bot.py` | Punto de entrada (`python -m boxlog.bot`): lee `.env`, registra handlers, filtra por Telegram ID y envía las respuestas. | RF-03 (registro), RF-08, RF-12, RNF-1 |
| `tests/test_core.py`, `tests/test_db.py`, `tests/test_commands.py`, `tests/test_bot.py` | Pruebas (ver §7). | Todos |
| `requirements.txt` | `python-telegram-bot`, `python-dotenv`, `pytest` (stack de la constitución, sin más dependencias). | Constitución 1 |
| `.env` (no git) | `TELEGRAM_TOKEN` y `OWNER_ID`. | RF-08, RNF-2 |
| `MEMORY.md` | Actualización final de estado y aprendizajes. | AGENTS (Forma de trabajar) |

`.gitignore` ya cubre `.env` y `data/`: no se modifica. No se crean más archivos.

## 2. Funciones puras de `core.py` (sin Telegram ni base de datos)

- `parse_number(text) -> float` — acepta coma y punto. *(RF-10)*
- `normalize_exercise(text) -> str` — minúsculas + colapsar espacios múltiples. *(RF-11)*
- `validate_profile(weight, height) -> str | None` — rangos 30–300 kg y 100–250 cm. *(RF-01, RF-09)*
- `validate_rm(kg) -> str | None` — rango 1–500 kg. *(RF-02, RF-09)*
- `validate_percentages(list) -> str | None` — 1–120, decimales. *(RF-05, RF-09)*
- `round_half_kg(kg) -> float` — redondeo al 0,5 kg más cercano. *(RF-05)*
- `convert_percentages(rm, pcts) -> list[float]` — `round_half_kg(rm * p / 100)`. *(RF-05)*
- `parse_log_args(args) -> (ejercicio, peso, reps) | None` — detecta `x` ausente/mal colocada, números ≤ 0, argumentos de más. *(RF-06, RF-09, RF-10, RF-11)*
- `format_kg(x) -> str` — coma decimal ("22,5"). *(RF-01, RNF-1)*
- `format_duration(seconds) -> str` — "1 h 23 min" / "45 min". *(RF-04)*
- `build_summary(start, end, series) -> str` — duración; por ejercicio: series, reps totales, volumen y máx. con peso **real**, pares `plan→real: …` solo de series con plan; volumen total; línea única si no hay series. *(RF-04, CL-5)*
- `format_log_confirmation(exercise, n, weight, reps, planned) -> str` — "<ejercicio> · serie N: <peso> kg × <reps>" con " (plan <kg>)" si hubo plan. *(RF-06)*
- `usage_example(command) -> str` — aviso de uso con ejemplo. *(RF-09, RNF-4)*
- `help_text() -> str` — lista de comandos. *(RF-12)*
- Textos fijos: aviso "No hay sesión abierta, envía /inicio", aviso de RM faltante, aviso de /deshacer sin series. *(RF-04, RF-05, RF-07, RNF-4)*

## 3. Esquema SQLite (`data/boxlog.db`)

`PRAGMA foreign_keys = ON` en cada conexión. Orden de creación: `profile`, `rm_history`, `sessions`, `plan_items`, `series`.

- `profile (id INTEGER PRIMARY KEY, weight_kg REAL, height_cm REAL, created_at TEXT)` — solo inserción; histórico de peso y altura, vigente = último `id` (igual que `rm_history`). *(RF-01)*
- `rm_history (id INTEGER PK, exercise TEXT, weight_kg REAL, created_at TEXT)` — RM vigente = último `id` del ejercicio *(RF-02)*.
- `sessions (id INTEGER PK, started_at TEXT, ended_at TEXT NULL)` — sesión abierta = `ended_at IS NULL`; al estar en disco sobrevive al reinicio *(RF-03, CL-11)*.
- `plan_items (id INTEGER PK, session_id INTEGER FK, exercise TEXT, position INTEGER, weight_kg REAL, consumed INTEGER DEFAULT 0)` — valores de `/hoy`; `position` da el orden, `consumed` la disponibilidad *(RF-05, RF-06, RF-07)*.
- `series (id INTEGER PK, session_id INTEGER FK, exercise TEXT, real_weight_kg REAL, reps INTEGER, planned_weight_kg REAL NULL, plan_item_id INTEGER NULL REFERENCES plan_items(id) ON DELETE SET NULL, created_at TEXT)` — orden por `id`; plan vacío = `NULL`; `plan_item_id` marca qué valor del plan consumió la serie *(RF-06, RF-07, RF-04)*.

Sin tabla de ejercicios (nombres normalizados en texto) ni de usuarios (un solo ID en `.env`). Migraciones futuras: `PRAGMA user_version` para conservar los datos *(RNF-3, constitución 5)*.

## 4. Algoritmos en pseudocódigo

**/hoy** *(RF-05, CL-2, CL-10, RF-09)*
```
si NO hay sesión abierta → aviso "No hay sesión abierta, envía /inicio"; FIN
si args inválidos (sin ejercicio, sin porcentajes, % fuera de 1–120) → aviso de uso; FIN
ejercicio ← normalize(args[0]); pcts ← parse_numbers(args[1:])
rm ← último rm_history de ejercicio
si no hay rm → aviso "No tengo RM de <ejercicio>, cárgalo con /rm"; FIN
kilos ← [round_half_kg(rm*p/100) para cada p]
borrar plan_items(sesión, ejercicio) e insertar kilos con consumed=0   // orden reiniciado
responder lista de kilos con format_kg
```

**/log** *(RF-06, CL-2, CL-3, RF-09, RF-10, RF-11)*
```
si NO hay sesión abierta → aviso RF-04; FIN
parsed ← parse_log_args(args)
si parsed es None → aviso de uso con ejemplo; FIN        // nunca se rechaza por falta de plan
ejercicio ← normalize; plan ← primer plan_items consumed=0 de (sesión, ejercicio)
planned ← plan.weight_kg si existe; si existe → consumed=1 y plan_item_id ← plan.id
si NO hay plan → planned ← NULL y plan_item_id ← NULL
n ← nº de series previas de ese ejercicio en la sesión + 1
INSERT en series(sesión, ejercicio, real=peso, reps, planned, plan_item_id)
responder format_log_confirmation(ejercicio, n, peso, reps, planned)
```

**/deshacer** *(RF-07, CL-2, CL-9)*
```
si NO hay sesión abierta → aviso RF-04; FIN
serie ← series de la sesión con id máximo
si no hay serie → aviso "No hay series en esta sesión"; FIN
si serie.plan_item_id NOT NULL y ese plan_item existe → consumed=0
   // si ya no existe (se repitió /hoy), no se restaura nada
DELETE serie
responder "Borrada: <ejercicio> <peso>x <reps>" (peso con coma decimal)
```

**/fin** *(RF-04, CL-2, CL-5, RNF-1)*
```
si NO hay sesión abierta → aviso "No hay sesión abierta, envía /inicio"; FIN
sesión.ended_at ← ahora; UPDATE sessions
series ← todas las series de la sesión ordenadas por id
si series vacías → cerrar sesión y responder "Sesión cerrada sin series"; FIN
responder build_summary(inicio, fin, series):
  duración ← format_duration(fin - inicio)
  por cada ejercicio (agrupado por nombre normalizado):
    nº series, reps ← Σ real reps, volumen ← Σ(real*reps), máx ← max(real)
    si alguna serie tiene planned → línea "plan→real: p1→r1, p2→r2" (solo esas series)
  al final: volumen total ← Σ volumen
```

## 5. Conexión de Telegram y restricción al ID

- `bot.py`: `dotenv` carga `TELEGRAM_TOKEN` y `OWNER_ID` (nunca en código ni en git *(RNF-2)*); `Application.builder()…` y registro de handlers.
- **Restricción (RF-08, CL-7):** todos los handlers se registran con el filtro `filters.User(OWNER_ID)`; los mensajes de otro ID no entran en ningún handler → sin respuesta y sin escritura. Comprobación unitaria con función `is_owner(update)`.
- Cada `CommandHandler` llama a su función de `commands.py` con los argumentos ya separados y envía el `str` que devuelve *(RNF-1: los textos salen en español de `core.py`)*.
- `MessageHandler(filters.COMMAND, …)` → `help_text()` para comandos desconocidos *(RF-12, CL-12)*; `MessageHandler(filters.TEXT & ~filters.COMMAND, …)` → mensaje breve con la lista de comandos *(RF-12)*.
- Los handlers no calculan ni guardan: solo orquestan *(constitución 3)*.

## 6. Decisiones técnicas (y alternativa descartada)

1. **`sqlite3` de la estándar, sin ORM** — el stack mínimo lo prohíbe; descartado SQLAlchemy (dependencia nueva sin necesidad de la spec).
2. **Consumo del plan con flag `consumed` por fila** — hace trivial "reiniciar orden" (RF-05) y "devolver valor" en /deshacer (RF-07); descartado un contador `next_index` porque reemplazar el plan o deshacer desincronizaría el contador de las series ya guardadas.
3. **Plan guardado por sesión** — el plan muere al cerrar la sesión (RF-05) sin borrar nada (RNF-3); descartado plan global en memoria (no sobreviviría al reinicio y rompería CL-11).
4. **`exercise TEXT` normalizado en cada fila, sin tabla de ejercicios** — la spec no pide consultas por ejercicio; descartada tabla normalizada (complejidad innecesaria).
5. **Fechas como texto ISO 8601** — legibles y suficientes para duración; descartado timestamp entero (menos legible en revisión de datos).
6. **Redondeo con `math.floor(x*2+0.5)/2`** — mitades hacia arriba (123,25 → 123,5), como exige RF-05; descartado `round(x*2)/2` porque Python redondea al par y daba 123,0 en los empates, y `Decimal` sobra para kilos en float.
7. **Perfil con historial de solo inserción (igual que `rm_history`)** — RF-01 exige conservar el historial de peso y altura aunque no se consulte; descartada la fila única (no dejaría historial).
8. **Respuesta de dueño con `filters.User` en el propio handler** — un único punto de control; descartado un decorator propio (código extra sin necesidad).

## 7. Estrategia de tests (pytest, primero y en verde)

- **`tests/test_core.py`** — parseo de números (coma/punto), rangos de perfil/RM/porcentajes, `x` mal colocada y argumentos de más, normalización de nombres, redondeo a 0,5, formato de duración y de kg con coma, `build_summary` (volumen con peso real, pares plan→real, sesión vacía), confirmación de /log, `usage_example` y `help_text`. *(RF-01, RF-04, RF-05, RF-06, RF-09, RF-10, RF-11, RF-12)*
- **`tests/test_db.py`** — esquema sobre BD temporal (`tmp_path`) con `foreign_keys=ON`, RM vigente = último, perfil vigente = último id, sesión única abierta, persistencia tras cerrar y reabrir conexión (reinicio simulado), inserción/listado de series, reemplazo y consumo del plan, restauración del `plan_item_id` en /deshacer y caso de plan_item borrado (ON DELETE SET NULL). *(RF-01, RF-02, RF-03, RF-06, RF-07, CL-11, RNF-3)*
- **`tests/test_commands.py`** — cada comando por la vía feliz y todos los avisos: sin sesión (CL-2), /log sin plan (CL-3), /deshacer sin series (CL-9), /hoy sin RM (CL-10), formatos inválidos con un solo aviso de uso (RF-09), /rms vacío, /fin sin series (CL-5), ciclo completo /inicio → /hoy → /log → /deshacer → /fin con verificación del resumen y de la confirmación de /log. *(RF-01 a RF-07, CL-1 a CL-10)*
- **`tests/test_bot.py`** — `is_owner` con ID correcto e incorrecto y que el texto de comandos desconocidos es la lista de comandos; sin red real. *(RF-08, CL-7, RF-12, CL-12)*
- **Proceso:** tests escritos antes que el código, `python -m pytest` en verde antes de cada commit, sin token ni datos personales en el diff *(constitución 4 y 5; criterios de finalización de la spec)*.
