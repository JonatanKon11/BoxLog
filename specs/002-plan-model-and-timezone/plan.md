# Plan 002 — Modelo de plan y zona horaria (BoxLog v0.2)

Complementa a `spec.md` (spec.md manda en el QUÉ; este archivo solo define el CÓMO).

*Notación: **(A-1)** … **(A-5)** marca los puntos ajustados por las decisiones del usuario
sobre las ambigüedades listadas en §7 (todas quedan resueltas).*

## 1. Resumen de cambios por archivo

| Archivo | Funciones nuevas o modificadas | Por qué | RF |
|---|---|---|---|
| `boxlog/core.py` | **Nuevo:** `LOCAL_UTC_OFFSET` (constante -3 h, comentada), `parse_plan_entries(tokens)` (parser puro de /hoy), `convert_plan_entries(rm, entries)` (kg por extremo + colapso), `format_plan_suffix(...)` (sufijo de plan en la confirmación de /log, con ×), `format_hoy_lines(entries, sets)` (respuesta de /hoy, con ×), helpers `utc_now()`/`to_local(dt)`/`is_today(...)`. **Modificadas:** `format_start_time` (marca UTC → hora local antes de comparar el día), `build_summary` (par con rango "64-68->66", leído de la serie). | Toda la lógica nueva es pura y testeable sin red ni base (constitución 3). **(A-1)** | RF-02, RF-03, RF-04, RF-05 |
| `boxlog/db.py` | **Nuevo:** `_migrate_v1_to_v2(connection, path)` (respaldo + ALTER + conversión de horas), `_backup_v1(connection, path)`. **Modificadas:** `_SCHEMA` (columnas v2 en el CREATE), `init_schema` (detecta versión y migra), `_now()` (hora **UTC** en vez de local; escribe `series.created_at`), `replace_plan` (recibe entradas con reps y rango), `get_next_plan_item` (devuelve también `reps` y `range_max_kg`), `insert_series` (**copia el plan a la serie**: `planned_reps` y `planned_max_kg`, además de `planned_weight_kg`), `list_series`/`get_last_series` (devuelven también `planned_reps` y `planned_max_kg` de la propia serie). | Esquema y persistencia; sin texto de respuesta (constitución 3). **(A-2, A-3)** | RF-01, RF-02, RF-04, RF-05, RF-06 |
| `boxlog/commands.py` | **Modificadas:** `cmd_hoy` (nuevo parser de entradas y respuesta por línea con ×), `cmd_log` (usa `format_plan_suffix` y pasa el plan completo a `insert_series`), `cmd_inicio` (marca UTC → local para mostrar) y `cmd_fin` (duración con fechas aware; los pares salen de los campos de la serie). | Orquestación: valida con core, persiste con db, devuelve texto. Sin imports de Telegram. | RF-02, RF-03, RF-04, RF-05 |
| `boxlog/bot.py` | **Sin cambios previstos.** Las firmas de los comandos son idénticas; el despacho, el dueño y el manejo de errores no deciden horas ni plan. | Separación de capas: nada nuevo en la interfaz (constitución 3). | — |
| `tests/` | `test_core.py` (parser, conversión, formatos con ×, zona horaria), `test_db.py` (esquema v2, escrituras, **migración**), `test_commands.py` (comandos con plan nuevo y horas locales, + actualización de tests de la 001 tocados por las enmiendas), `test_e2e.py` (ciclo con rango y reps). | Tests primero (constitución 4). | Todos |

`requirements.txt`, `.gitignore` y `.env.example` **no cambian** (RNF-2: sin dependencias
nuevas; `zoneinfo` queda descartado por exigir `tzdata` en Windows).

## 2. Diseño de la migración 1 → 2

Detección y ramas en `init_schema(connection)` (el `path` ya está en `connect`; se le pasa
a `init_schema` o se guarda en la conexión):

1. `version ← PRAGMA user_version`.
2. **`version == 0`** (base nueva): `executescript(_SCHEMA v2)` → `user_version = 2` → fin.
   Sin respaldo ni migración (CL-11).
3. **`version == 2`**: `executescript(_SCHEMA v2)` (no-op, `IF NOT EXISTS`) → fin
   (CL-10: no re-ejecuta nada ni recrea el respaldo).
4. **`version == 1`** → `_migrate_v1_to_v2(connection, path)`:

   a. **Respaldo**: si `<path>.bak-v1` no existe, crearlo con `connection.backup(dest)`
      (API de respaldo de SQLite; segura con la conexión abierta). Para `:memory:` se omite.
      Se hace **antes** de la transacción y solo una vez (idempotencia por existencia de
      archivo, además de por la versión).

   b. **Transacción**: `connection.execute("BEGIN IMMEDIATE")`. Nunca `executescript`
      aquí: emite un COMMIT implícito y rompería la atomicidad.

   c. **Esquema**: cuatro `ALTER TABLE ... ADD COLUMN` (permitidos dentro de la
      transacción): `plan_items.reps INTEGER`, `plan_items.range_max_kg REAL`,
      `series.planned_reps INTEGER`, `series.planned_max_kg REAL` (A-3). No se crea
      ninguna columna de hora: la marca de serie ya existe (A-2).

   d. **Horas a UTC (+3 h)**: recorrer en Python `sessions.started_at/ended_at`,
      `profile.created_at`, `rm_history.created_at` y `series.created_at` (A-2: las
      series existentes **conservan su hora**, convertida igual que las demás), con
      `datetime.fromisoformat(marca) + timedelta(hours=3)` y `UPDATE` por id; se
      conserva el formato ISO con "T" (descartado `datetime(x, '+3 hours')` de SQLite,
      que reescribe el formato y obligaría a tolerar dos dialectos). Son pocas filas
      (base personal).

   e. **`PRAGMA user_version = 2`** y `COMMIT`.

5. **Si falla a mitad** (paso c, d o e): `except → ROLLBACK → re-lanzar el error`. El
   `PRAGMA user_version` es transaccional en SQLite, así que la base queda **íntegra en
   v1** (sin columnas parciales ni horas a medias) y el respaldo ya existe para
   recuperación manual. El usuario puede reintentar: la migración se re-ejecuta entera.
6. **Idempotencia**: solo se entra en la rama 4 cuando `version == 1`; al terminar es 2,
   por lo que repetir la llamada cae en la rama 3. El respaldo no se recrea nunca si ya
   existe. Un segundo `+3 h` es imposible por diseño.
7. **Transición**: una sesión abierta en v1 tiene `started_at` local; la conversión la
   pone en UTC y, a partir de ahí, `_now()` escribe UTC: no queda mezcla de bases.

## 3. Parser de /hoy (función pura en `core.py`)

**Pseudocódigo:**

```
split ← split_exercise_and_numbers(args)             // reutilizado de la 001 (RF-11)
si split es None → aviso de uso; FIN
ejercicio, tokens ← split
entries, aviso ← parse_plan_entries(tokens)          // puro, sin RM ni sesión
si aviso → responder aviso (motivo + ejemplo); FIN   // nada se guarda
rm ← db.get_rm(ejercicio); si no hay rm → aviso "No tengo RM…"; FIN
sets ← convert_plan_entries(rm, entries)              // kg por extremo + colapso (CL-16)
db.replace_plan(sesión, ejercicio, sets)              // DELETE por sesión+ejercicio e INSERT con position, consumed=0 (orden reiniciado)
responder format_hoy_lines(tokens, sets)              // ver A-1
```

**Reglas de `parse_plan_entries(tokens)`: se procesa de izquierda a derecha y se para en
el primer token inválido**, devolviendo su aviso (motivo + ejemplo); no se informa ningún
otro error (A-4, CL-17). Para cada token, en este orden:

1. **Gramática** (tras normalizar en-dash "–" → "-" en el token y `X` → `x`; A-5: "65X3"
   ≡ "65x3", CL-18): cada token debe cumplir `^(\d+(?:[.,]\d+)?)(?:-(\d+(?:[.,]\d+)?))?(?:x(\d+))?$`.
   - "65 x 3" (espacios) → no casa → CL-13.
   - "-5", "80-", "-80-85" → no casan (el guion solo puede ir **dentro**, entre dos
     números) → CL-14.
   - `65x2,5` → la reps del grupo 3 solo admite dígitos → no casa.
   - Aviso: `"Entrada de plan no válida. Usa /hoy clean 65x3 o /hoy clean 80-85"`.
2. **Rango de porcentajes** 1–120 (cada extremo; decimales con coma o punto vía
   `parse_number`) → `"El porcentaje tiene que estar entre 1 y 120. Usa /hoy clean 70 80 85"`.
3. **Rango invertido**: extremo izquierdo < derecho → `"El mínimo del rango tiene que ser
   menor que el máximo. Usa /hoy clean 80-85"`.
4. **Repeticiones**: presencia ⇒ entero ≥ 1 → `"Las repeticiones tienen que ser un entero
   de 1 en adelante. Usa /hoy clean 65x3"`.

Devuelve `list[PlanEntry(pct_low, pct_high | None, reps | None)]`. Un token inválido
invalida toda la ordenada (RF-09: un solo aviso, nada se guarda).

**`convert_plan_entries(rm, entries)`**: para cada entrada, `low ← round_half_kg(rm *
pct_low / 100)` y, si hay extremo alto, `high ← round_half_kg(rm * pct_high / 100)`
(**por separado**, CL-16); si `high == low` → se guarda como valor único
(`range_max_kg = NULL`). Devuelve `list[PlannedSet(weight_kg, range_max_kg, reps)]`.

**Interacción con el plan existente**: `replace_plan` conserva su contrato (DELETE
filtrado por `session_id` + `exercise`, `position` de 1 en 1, `consumed = 0`); solo
amplía las columnas que inserta. El consumo en `/log` **no cambia**: un ítem por `/log`,
en orden; `get_next_plan_item` pasa a devolver `reps` y `range_max_kg` y
`insert_series` **copia el plan a la serie** (`planned_weight_kg` ya existente y las
nuevas `planned_reps`/`planned_max_kg`, vacías si no había plan o no tenía reps/rango;
A-3), de modo que `/fin` (y el futuro dashboard) leen de la serie sin tocar
`plan_items`. La confirmación se arma con `format_plan_suffix` (`(plan 84)`, con ×:
`(plan 66 kg × 1)`, `(plan 64-68 kg × 1)`, `(plan 64-68)`; A-1). `/deshacer` libera el
ítem por id, igual que hoy (CL-8).

**Respuesta de /hoy** (`format_hoy_lines`, A-1, CL-19): una línea por entrada, en el
orden dado, con el mismo signo × que las confirmaciones de /log:

- sin reps: `70% → 84 kg` (sin cambios de la 001);
- con reps: `65% × 3 → 52 kg`;
- con rango: `80-85% × 1 → 64-68 kg` (o `80-85% → 64-68 kg` sin reps).

La salida usa siempre el guion menos (CL-15), incluso si la entrada vino con en-dash.

## 4. Zona horaria

- **Constante** en `core.py`: `LOCAL_UTC_OFFSET = timedelta(hours=-3)` con comentario
  *"Argentina, UTC-3, sin horario de verano; desfase fijo, sin zoneinfo (tzdata en
  Windows)"* (RF-02, RNF-2).
- **Helpers puros en `core.py`**: `utc_now()` (aware, UTC), `to_local(dt)` (`dt +
  LOCAL_UTC_OFFSET`), `is_today(dt, now)` (compara fechas **ya convertidas a local**,
  CL-12). `db._now()` pasa a `datetime.now(timezone.utc).isoformat(timespec="seconds")`.
- **Puntos donde hoy se muestran horas** (todos quedan en local):
  1. `cmd_inicio` — confirmación "Sesión iniciada a las 20:35" y aviso "Sesión abierta
     desde …": `core.format_start_time(marca_utc, now)` interpreta la marca como UTC,
     la pasa a local y compara el día con `now` **también en local** (CL-12: 01:00 UTC
     = 22:00 del día anterior → "hoy").
  2. `cmd_fin` — duración: `datetime.fromisoformat(started_at)` (UTC aware) contra
     `utc_now()`; solo resta, así que el formato "1 h 23 min" no cambia.
  3. `build_summary` — solo recibe la duración ya calculada; no ve husos.
- Ningún otro módulo muestra horas (bot.py solo envía el texto que recibe).

## 5. Estrategia de pruebas (pytest, primero y en verde)

- **`tests/test_core.py` (nuevos):** parser de entradas — mixtas (CL-1), espacios
  "65 x 3" (CL-13), signo menos "-5"/"80-"/"-80-85" (CL-14), en-dash "80–85x1" (CL-15),
  coma decimal "1x82,5", rangos invertidos y reps inválidas, mayúscula "65X3" (A-5,
  CL-18) y primer-error-de-izquierda-a-derecha "130 65x0 85-80" (A-4, CL-17);
  `convert_plan_entries` con redondeo por extremo y colapso (CL-16, ej. RM 100 y
  "80,2-80,4x1" → 80 único); `format_plan_suffix` con sus cuatro variantes y
  `format_hoy_lines` con los tres formatos y × (A-1, CL-19); `build_summary` con par
  "64-68->66" leído de la serie; zona horaria — marca UTC
  "2026-10-14T01:00:00+00:00" con `now` local 14/10 23:00 → es "hoy" (CL-12), conversión
  -3 h y `format_start_time` sobre marcas UTC.
- **`tests/test_db.py` (nuevos):** base fresca → columnas v2 presentes y
  `user_version = 2` sin respaldo (CL-11); **migración desde una base v1 sintética**
  (DDL de la 001 + perfil, RM, dos sesiones, plan con `consumed` y series con horas
  locales) → existe `<path>.bak-v1`, `user_version = 2`, columnas nuevas, todas las horas
  +3 h **incluido `series.created_at`** (A-2) y todos los datos intactos (RNF-1, RF-06);
  segunda ejecución → no-op y respaldo sin recrear (CL-10); **fallo simulado** con un
  `CREATE TRIGGER ... RAISE(ABORT)` que rompa un UPDATE → `ROLLBACK` total: versión sigue
  en 1 y sin columnas parciales; `replace_plan` con entradas; `insert_series` copia el
  plan a la serie (`planned_reps`/`planned_max_kg` rellenados o NULL, A-3) y las series v1
  las dejan NULL (CL-9); `:memory:` sin respaldo.
- **`tests/test_commands.py`:** `cmd_hoy` con las cuatro sintaxis, cada aviso (motivo +
  ejemplo), primero-error (CL-17) y la respuesta con × (CL-19), `cmd_log` con plan de
  reps/rango (confirmación con × y copia del plan a la serie), `cmd_fin` con par de rango
  leído de la serie, `cmd_inicio`/`cmd_fin` con marcas UTC cercanas a la medianoche
  (CL-12). **Tests de la 001 a actualizar por las enmiendas:** los de horas
  (`format_start_time` recibe marcas UTC y devuelve igual de legible), los de respuesta de
  `/hoy` (solo si el texto cambia por ×/formato; los porcentajes simples no cambian) y
  cualquier aserción de `user_version = 1`.
- **`tests/test_e2e.py`:** el ciclo completo actual debe seguir en verde sin cambios de
  texto (entradas simples); se le añade una pasada con "80-85x1" y su confirmación.
- **`tests/test_bot.py`:** sin cambios previstos.
- Proceso: tests antes que código, `python -m pytest` en verde, sin token ni datos
  personales en el diff (constitución 4 y 5).

## 6. Orden de implementación (de menor a mayor riesgo) y riesgos

1. `core`: constante y helpers de zona horaria + tests (puro, cero riesgo).
2. `core`: `parse_plan_entries`, `convert_plan_entries`, `format_plan_suffix`, par con
   rango en `build_summary` + tests.
3. `db` (base fresca): `_SCHEMA` v2, `_now()` en UTC, `replace_plan`/`get_next_plan_item`/
   `insert_series`/`list_series` ampliados + tests sobre `tmp_path`.
4. `commands`: cablear `/hoy`, `/log`, `/inicio`, `/fin` + actualizar los tests de la 001
   afectados por las enmiendas.
5. `db` (**riesgo alto, al final**): `_migrate_v1_to_v2` con respaldo, transacción y test
   de fallo; ejecutar sobre una copia real de `data/boxlog.db` antes que sobre la original.
6. E2E + suite completa + `MEMORY.md`.

**Riesgos:**
- `executescript` hace COMMIT implícito → la migración debe usar `BEGIN IMMEDIATE` a
  mano; si no, un fallo a mitad dejaría la base a medias (mitigado + test de fallo).
- Conversión doble de horas si la migración corriera dos veces → imposible por
  `user_version` dentro de la misma transacción; el respaldo tampoco se recrea.
- Mezcla de marcas naive/UTC durante el corte de despliegue (mitigada: la migración
  convierte todo lo previo, incluido `series.created_at`, antes de que `_now()` escriba
  UTC).
- Unificación del signo × en lo que muestra el plan (A-1): puede tocar tests de la 001
  que esperen "x"; se actualizan a × y se revisa el README.
- Orden de validaciones: un token que rompa varias reglas a la vez (p. ej. "130-140x0")
  debe dar un único aviso estable — el primero de izquierda a derecha (A-4, CL-17).
- El respaldo ocupa el doble del tamaño de la base en `data/` (ignorado por git).
- El ensayo de migración sobre la copia real (T-final) exige el bot apagado para no
  escribir sobre una base en transición.

## 7. Puntos de la spec que el plan descubre ambiguos — RESUELTOS

Decisiones del usuario, aplicadas a `spec.md` y a este plan (marcadas **A-n**):

- **A-1 Formato de la respuesta de /hoy — resuelto:** sin reps responde como hoy
  (`70% → 84 kg`); con reps `65% × 3 → 52 kg`; con rango `80-85% × 1 → 64-68 kg`. Se usa
  el signo × de las confirmaciones de /log (la "x" de la revisión inicial se unifica).
  Aplicado también a `format_plan_suffix` (CL-6, CL-19).
- **A-2 `series.created_at` — resuelto:** **no** se añade `logged_at`. La migración
  convierte `series.created_at` a UTC (+3 h, como el resto de marcas) y esa es la hora
  de cada serie; desde la migración se escribe en UTC. Las series existentes **sí**
  conservan su hora (convertida). RF-01 y CL-9 corregidos.
- **A-3 Rango en /fin tras repetir /hoy — resuelto:** al registrar una serie con /log el
  plan se copia a la propia serie (`series.planned_reps`, `series.planned_max_kg`, ambas
  vacías si no había plan o no tenía reps/rango). `/fin` y el futuro dashboard leen de
  la serie, sin depender de `plan_items`. Las series existentes quedan en NULL. La
  migración añade columnas a `plan_items` **y** a `series`; el test de migración lo
  verifica.
- **A-4 Orden de validaciones — resuelto:** las entradas se procesan de izquierda a
  derecha y solo se avisa el **primer** error (con su motivo y ejemplo); nada se guarda
  (CL-17).
- **A-5 Reps en mayúscula — resuelto:** se acepta "65X3" (≡ "65x3"), como en /log;
  se normaliza `X` → `x` en la gramática (CL-18).
