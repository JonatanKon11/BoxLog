# Plan 004 — Dashboard local de solo lectura (BoxLog v0.4)

Complementa a `spec.md` (spec.md manda en el QUÉ; este archivo solo define el CÓMO).

Sin dependencias nuevas (solo stdlib), sin migración, sin tocar la base real y sin
arrancar el bot: todo el desarrollo se prueba sobre bases temporales en `tmp_path`.
`requirements.txt`, `.gitignore` y `.env.example` **no cambian** (RNF-3); `data/` ya
está en `.gitignore` y por eso cubre el HTML generado.

## 1. Resumen de cambios por archivo

| Archivo | Funciones nuevas o modificadas | Por qué | RF |
|---|---|---|---|
| `boxlog/core.py` | **Nuevos (puros, sin `sqlite3`):** `local_date(marca)`, `streak_days(days, today)`, `count_month(dates, today)`, `max_load_points(rows)`, `percentage_table(rms)`, `plan_real_pairs(series)` (extraída de `build_summary`, con la misma salida), `dashboard_version_error(version)` (T2), `build_dashboard_payload(...)` (T3) y las constantes `DASH_DB_MISSING`, `DASH_DB_V0`, `DASH_DB_V1`, `DASH_DB_UNSUPPORTED`, `DASH_DB_LOCKED`, `DASH_GENERATED`, `DASH_NO_RM`. **Modificada:** `build_summary` (delega en `plan_real_pairs`; su texto no cambia). | Toda la lógica y los textos fijos viven en la capa pura (constitución 3) y el test de la 001 exige que `core.py` no importe `sqlite3`. | RF-02 a RF-06 |
| `boxlog/db.py` | **Nuevos:** `open_readonly(path)` (URI `file:///...?mode=ro` + `PRAGMA query_only`), `read_user_version(connection)`, `with_lock_retry(fn)` y las lecturas `read_sessions`, `read_series`, `read_rm_history`; se reutiliza `list_rms` (vigentes, orden alfabético). **Sin cambios de esquema, sin `init_schema`, sin commits.** | El acceso a datos queda en su capa (constitución 3), todo en modo solo lectura (RNF-1). | RF-01 |
| `boxlog/dashboard.py` | **Nuevo módulo:** `main()` (CLI sin argumentos, código de salida 0/1), `render_dashboard(payload)`, `_esc`, `_json_seguro`, `_svg_line`, `_escribir_atomico` y las rutas `DB_PATH`/`OUTPUT_PATH`. | Interfaz: solo orquesta — abrir, pedir el payload a core, renderizar, escribir y avisar por consola (constitución 3). No importa `boxlog.bot` ni `dotenv` (RNF-2). | RF-01, RF-06 |
| `tests/` | `test_core.py` (puras), `test_db.py` (solo lectura, versiones, lock), `test_dashboard.py` (**nuevo**: CLI, payload JSON, SVG, escapado, atómico) y `test_e2e.py` (T7: pipeline completo sobre una base de prueba en `tmp_path`). | Tests primero (constitución 4), sin navegador y sin red. | Todos |

## 2. Capa pura: `core.py` (RF-02, RF-03, RF-04, RF-05)

Funciones nuevas — todas reciben fechas/filas ya traídas por `db` y `today` como
parámetro (nada de reloj ni de conexión dentro):

```python
def local_date(marca_utc: str) -> date:
    """Fecha local (UTC-3) de una marca UTC de la base (RF-02 de la 002)."""
    return to_local(datetime.fromisoformat(marca_utc)).date()

def streak_days(days: set[date], today: date) -> tuple[int, bool]:
    """(racha mostrada, falta_hoy). Un día cuenta si tiene sesión (CL-7); la racha
    corre desde hoy y, si hoy falta pero ayer hay, sigue viva (CL-5); si hoy ni
    ayer, 0 (CL-4). La sesión abierta solo aporta su día de inicio (CL-3)."""
    ayer = today - timedelta(days=1)
    if today in days:
        inicio, falta = today, False
    elif ayer in days:
        inicio, falta = ayer, True
    else:
        return 0, False
    n, d = 0, inicio
    while d in days:
        n += 1
        d -= timedelta(days=1)
    return n, falta

def count_month(dates: list[date], today: date) -> int:
    """Sesiones iniciadas en el mes en curso local; lista con duplicados (CL-7:
    dos sesiones el mismo día cuentan 2)."""
    return sum(1 for d in dates if (d.year, d.month) == (today.year, today.month))

def max_load_points(rows: list[dict]) -> dict[str, list[tuple[date, float]]]:
    """Un punto (fecha local, máx kg) por sesión y ejercicio, en el orden de la
    entrada (ya cronológico); los puntos los prepara el payload con las sesiones."""
    ...

_PERCENT_STEPS = tuple(range(50, 101, 5))     # 11 filas: 50, 55, … ,100 (RF-03)

def percentage_table(rms: list[tuple[str, float]]) -> tuple[list[str], list[list[float]]]:
    """(ejercicios, filas): porcentajes de 50 a 100 en pasos de 5 sobre cada RM,
    kilos redondeados a 0,5 con round_half_kg (RF-05 de la 001); sin RM no hay
    columna (el orden es el de list_rms, alfabético)."""
    ...

def plan_real_pairs(series: list[dict]) -> list[str]:
    """Pares plan→real (RF-05): la lógica EXACTA que hoy está dentro de
    build_summary, extraída con la misma técnica que exercise_stat_line (003);
    build_summary pasa a unir su resultado y su texto no cambia."""
    ...
```

- **Extracción sin romper /fin:** el `if` y el `f-string` de los pares se mueven
  tal cual de `build_summary` a `plan_real_pairs`; `build_summary` hace
  `"  plan→real: " + ", ".join(plan_real_pairs(series))` cuando hay pares. Los
  tests guardia de la spec (pares, rango, sin plan, migrada de v1, e2e) se quedan
  **sin tocarse**: si alguno cambia, la extracción está mal y se corrige el código.
- `dashboard_version_error(version) -> str | None`: `0 → DASH_DB_V0`, `1 →
  DASH_DB_V1`, `2 → None`, otro → `DASH_DB_UNSUPPORTED` (CL-9, CL-12, CL-13).
- **Traducción de clades de fila:** `db` devuelve nombres de la base
  (`real_weight_kg`, `started_at`…); el payload los traduce a los de `core`
  (`real_weight`, `planned_*`) igual que `cmd_fin` — el KeyError de la 003 enseña
  que este mapeo hay que probarlo (R10).
- `build_dashboard_payload(*, sessions, series, rm_history, rms, today, generated)`
  (T3): arma el diccionario del §5 con estas funciones; calcula duración de sesión
  cerrada con `format_duration` sobre marcas parseadas en UTC **aware** antes de
  restar (lección T5 de la 002) y la abierta con `duration: None` y `opened_at` en
  local.

## 3. Capa de datos: `db.py` solo lectura (RF-01, CL-9 a CL-13)

```python
_LOCK_TIMEOUT = 0.2      # segundos de espera por intento ante un lock

def open_readonly(path) -> sqlite3.Connection:
    """URI en solo lectura + query_only; NO crea carpetas ni archivos (a diferencia
    de connect) y NO llama init_schema (RNF-1)."""
    uri = Path(path).resolve().as_uri() + "?mode=ro"   # file:///C:/…/boxlog.db?mode=ro
    connection = sqlite3.connect(uri, uri=True, timeout=_LOCK_TIMEOUT)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection

def read_user_version(connection) -> int:
    """PRAGMA user_version (sin parámetros: no admite ?)."""

def with_lock_retry(fn, attempts=3, delay=0.05):
    """Reintenta ante OperationalError con "locked"/"busy" (el bot escribiendo,
    CL-11); cualquier otro error se propaga. El último error se eleva para que la
    CLI lo traduzca en DASH_DB_LOCKED. time.sleep se parchea en los tests."""
```

- **Control de versión antes de leer datos:** `dashboard_version_error` en el §2;
  el mensaje sale por consola y **no se genera el HTML** (los mensajes fijos están
  en la spec RF-01: faltante, v0, v1, desconocida, ocupada).
- Lecturas (sin `LIMIT` — a diferencia de `/historial` no hay tope —, sin commits,
  en el estilo de las lecturas existentes):

```python
def read_sessions(connection):    # SELECT * FROM sessions ORDER BY started_at DESC
def read_series(connection):      # SELECT * FROM series ORDER BY id
def read_rm_history(connection):  # SELECT exercise, weight_kg, created_at … ORDER BY id
```

- Se reutiliza `list_rms` (vigentes ya ordenados por ejercicio) en vez de sumar una
  consulta nueva.
- `foreign_keys` no hace falta (no se escribe); el resto de `PRAGMA` de escritura
  está prohibido — lo garantiza `query_only` y el test de hash.

## 4. Interfaz: `boxlog/dashboard.py` (RF-01, RF-06)

Rutas propias (no importa `bot.py` por RNF-2; mismo supuesto de cwd que
`python -m boxlog.bot`):

```python
DB_PATH = Path("data") / "boxlog.db"
OUTPUT_PATH = Path("data") / "dashboard.html"

def main(argv=None) -> int:
    """0 = generado; 1 = mensaje fijo en consola y el HTML existente intacto."""
    try:
        connection = db.open_readonly(DB_PATH)
        try:
            error = core.dashboard_version_error(db.read_user_version(connection))
            if error:
                print(error); return 1
            payload = _leer_payload(connection)      # lecturas + build_dashboard_payload
        finally:
            connection.close()
        html = render_dashboard(payload)
        _escribir_atomico(OUTPUT_PATH, html)
    except sqlite3.OperationalError as exc:          # sin base / lock persistente
        print(_mensaje_de(exc)); return 1
    print(core.DASH_GENERATED.format(ruta=OUTPUT_PATH.as_posix(),
                                     n=len(payload["sessions"])))
    return 0
```

- **Flujo completo en un solo intento de lectura** (payload → render → escritura),
  envuelto en `with_lock_retry` para abrir y leer (CL-11).
- **Mensajes:** solo los fijos de la spec (`DASH_DB_*` y `DASH_GENERATED`);
  cualquier otro error se propaga con su traceback en consola (desarrollador) sin
  tocar el HTML — no se inventan textos nuevos.
- **Escapado en dos capas:**

```python
def _esc(texto) -> str:
    return html.escape(str(texto), quote=True)       # texto visible y atributos

def _json_seguro(payload) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
```

  El JSON va en `<script id="datos" type="application/json">…</script>` y el JS
  solo hace `JSON.parse(document.getElementById("datos").textContent)`; reemplazar
  el `<` mata `</script>` en cualquier variante (CL-8).
- **Escritura atómica (CL-16):** escribir en `data/dashboard.html.tmp` y
  `os.replace(tmp, OUTPUT_PATH)`; si algo falla, se borra el temporal y el HTML
  anterior queda intacto.
- **SVG a mano:**

```python
def _svg_line(puntos: list[tuple[str, float]], etiqueta: str) -> str:
    """viewBox fijo (p. ej. 0 0 640 240): 0 puntos → ""; 1 → solo <circle>;
    ≥2 → <polyline> + <circle>s. x por índice (los puntos ya vienen cronológicos),
    y escalado min..max con margen; si max == min, línea central (sin división
    por cero). Ejes y etiquetas en español; los kg se formatean con format_kg."""
```

- **CSS inline mobile-first** (viewport, contenedor, tarjetas, `.racha` en grande)
  con `@media print { .controles { display: none; } }` para guardar como PDF sin
  el selector (RF-06).
- **JS mínimo (T6):** todos los `<g data-exercise="…">` del gráfico de carga van
  pre-renderizados en el HTML (el SVG es testeable sin JS) y el script solo
  alterna la visibilidad según el `<select>`; sin frameworks, sin `fetch`, sin CDN.

## 5. Esquema del payload JSON

Claves en **inglés** (identificadores, constitución 6), valores de presentación en
**español** ya formateados (coma decimal, `dd/mm`, textos de /fin); los kg viajan
como **número** solo donde el SVG necesita escalar y se formatean al renderizar.

```json
{
  "generated": "16/10/2026 21:04",
  "streak": {"days": 12, "missing_today": false, "last": "16/10"},
  "month_sessions": 8,
  "rm_current": [{"exercise": "clean", "kg": 120}],
  "rm_evolution": [{"exercise": "clean", "points": [["01/09", 115], ["15/09", 120]]}],
  "percent_table": {"exercises": ["clean", "front squat"],
                    "steps": [50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100],
                    "values": [[60, 85], [66, 93.5], "…", [120, 170]]},
  "sessions": [
    {"date": "16/10", "open": false, "opened_at": null, "duration": "45 min",
     "volume": "499,5 kg",
     "lines": ["clean: 4 series · 9 repeticiones · volumen 499,5 kg · máx 66 kg"],
     "pairs": ["70→66", "80-85→52"]},
    {"date": "16/10", "open": true, "opened_at": "20:35", "duration": null,
     "volume": "84 kg", "lines": ["clean: 1 serie · 3 repeticiones · volumen 84 kg · máx 84 kg"],
     "pairs": []}
  ],
  "max_load": {"clean": [["16/10", 66], ["18/10", 70]]}
}
```

- `sessions` en orden `started_at` descendente (la abierta olvidada aparece por su
  fecha, CL-3); `lines` salen de `group_series_by_exercise` + `exercise_stat_line`
  (mismo formato que /fin) y `pairs` de `plan_real_pairs` (RF-05).
- `percent_table.values[fila][columna]` es el kg redondeado a 0,5 (número); la
  celda "%" y la coma las pone el render.
- `max_load` solo incluye ejercicios con series (CL-15); `rm_current` solo con RM
  vigente.
- Estados vacíos: `sessions: []` con `streak.days: 0` (CL-1) — el HTML se genera
  igual, con los textos de la spec.

## 6. Estructura de la plantilla

`render_dashboard(payload) -> str` (puro: entra el dict, sale el HTML completo):

```html
<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BoxLog — dashboard</title>
<style> … mobile-first … .racha { font-size: 3rem; }
        @media print { .controles { display: none; } } … </style></head>
<body><main>
  <header>
    <h1>BoxLog</h1>
    <p class="generado">Generado el 16/10/2026 a las 21:04</p>
    <p class="racha">🔥 12</p>                 <!-- o 0 + "Último entreno: 16/10" -->
    <p>Sesiones del mes: 8</p>                  <!-- o aviso "Hoy aún no entrenas; …" -->
  </header>
  <section id="rm">      <!-- vigentes, SVGs de evolución, tabla 50–100 % -->
  <section id="historial"> <!-- <article> por sesión: fecha, duración, líneas, pares -->
  <section id="carga">   <!-- <select class="controles"> + <svg> con <g data-exercise> -->
</main>
<script id="datos" type="application/json">{…}</script>
<script> /* solo: JSON.parse + toggle del select */ </script>
</body></html>
```

Todo texto dinámico pasa por `_esc` (también dentro de atributos: `value`,
`data-exercise`); los estados vacíos usan `HISTORIAL_EMPTY` (reutilizado) y
`DASH_NO_RM = "Aún no hay RM. Guarda uno con /rm <ejercicio> <kg>"`.

## 7. Estrategia de pruebas (pytest, sin navegador)

Mismo patrón que la 002/003: tests antes que código, rojo verificado y
`python -m pytest` completo en verde al final de cada tarea. Nada requiere red, el
bot ni un navegador:

- **Puras (test_core):** tabla parametrizada de `streak_days` (vacío, {hoy},
  {ayer}, tres seguidos, hueco, {ayer, antayer} sin hoy, dos días con hueco en
  medio), `local_date` con marcas alrededor de la medianoche UTC (01:30Z → día
  local anterior), `count_month` con duplicados y mes contiguo, `percentage_table`
  (11 filas, redondeos 0,5 con RM 80/120, sin RM → sin columnas) y
  `plan_real_pairs` (mismos textos que /fin; sin plan → lista vacía; `planned_*`
  NULL → par simple).
- **Solo lectura (test_db):** hash del archivo antes/después de generar (patrón
  T7 de la 002), `INSERT`/`UPDATE` que fallan por `query_only`, mensajes de
  versión 0/1/2/otro, base inexistente → error de apertura, lock determinista con
  otra conexión en `BEGIN EXCLUSIVE` (→ `DASH_DB_LOCKED`, con `sleep` parcheado)
  y reintento con una `fn` falsa que falla 2 veces y pasa a la 3ª.
- **Render (test_dashboard):** se extrae el `<script id="datos"
  type="application/json">` con regex (el `\u003c` impide que el `</script>` de un
  nombre hostil cierre el bloque antes de tiempo) y se compara con `json.loads`;
  se cuentan `<svg`, `<circle>`, `<polyline>` y `<g data-exercise>` para 0, 1 y 2
  puntos; nombre hostil (`</script><script>…`, comillas) → `\u003c/script` en el
  JSON y entidades en texto y atributos; token falso en el entorno → ausente del
  HTML; sin `http://`, sin `<script src=`; `@media print` presente; fallo simulado
  de escritura → el HTML previo intacto y sin `.tmp` residual.
- **E2E (T7, test_e2e):** base de prueba real en `tmp_path` construida con los
  escritores del propio bot (`init_schema` + `/rm`, `/inicio`, `/hoy`, `/log`,
  `/deshacer`, `/fin` con el reloj fijado, patrón 002) y después el pipeline
  completo del dashboard sobre ella: payload coherente (racha, mes, sesiones con
  pares, RM con evolución, tabla, carga), hash de la base intacto y nombre hostil
  insertado vía `/log` escapado en el HTML final.

## 8. Orden de implementación y riesgos (cómo se prueba cada uno)

Orden (detalle en `tasks.md`): T1 core puro → T2 db solo lectura → T3 CLI + payload
+ HTML mínimo → T4 historial y pares → T5 racha/mes/RM → T6 gráfico con selector y
CSS de impresión → T7 cierre (e2e + docs + ensayo manual).

| # | Riesgo | Cómo se prueba |
|---|---|---|
| R1 | Extraer `plan_real_pairs` cambia la salida de /fin | Tests guardia de la spec intactos (pares, rango, sin plan, migrada v1, e2e); si cambian, se corrige el código, no el test |
| R2 | `core.py` importa `sqlite3` | `test_core_no_importa_telegram_ni_sqlite`; el payload recibe filas ya leídas |
| R3 | Inyección por nombre de ejercicio (HTML, atributos o JSON) | Nombre hostil en las tres capas: `\u003c` en el JSON, entidades en texto y en `value`/`data-exercise` |
| R4 | El dashboard escribe la base | `mode=ro` + `query_only`; hash antes/después; `INSERT` que debe fallar |
| R5 | Migración accidental (`init_schema`) | `user_version` se lee en solo lectura y corta antes de leer datos; mensaje de v1 → sin HTML; test: la versión 1 no cambia |
| R6 | Lock con el bot corriendo | `with_lock_retry` (fn falsa: 2 fallos → éxito; lock real con `BEGIN EXCLUSIVE` → `DASH_DB_LOCKED`) + ensayo manual con el bot vivo |
| R7 | HTML a medias | Escritura atómica (`tmp` + `os.replace`); fallo simulado → el anterior intacto y sin `.tmp` |
| R8 | Fecha UTC confundida con local | `local_date` vía `to_local`; tests con marcas alrededor de la medianoche (patrón de la 002) |
| R9 | Gráficos con 0, 1 o 2 puntos | Conteo de `circle`/`polyline` en el HTML; `max == min` sin división por cero |
| R10 | Desajuste de claves de fila (`real_weight_kg` vs `real_weight`) | El payload traduce igual que `cmd_fin`; el e2e de T7 con escritores reales lo delata |
| R11 | Base vacía rompe el render | Estados vacíos + test con base recién creada (0 sesiones, 0 RM) que genera el HTML igual |
| R12 | Token o `.env` dentro del HTML | `dashboard.py` no importa `dotenv` ni `boxlog.bot`; test con token falso en el entorno → ausente |

## 9. Supuestos y detalles menores

- stdlib solamente: `sqlite3`, `json`, `html`, `pathlib`, `datetime`, `time`, `os`.
  Nada de `fetch` (CORS en `file://`): los datos viajan incrustados.
- `dashboard.py` define sus propias `DB_PATH`/`OUTPUT_PATH` y no importa `bot.py`
  (RNF-2); se ejecuta desde la raíz del proyecto, igual que `python -m boxlog.bot`.
- Las sesiones se ordenan por `started_at` descendente; la abierta olvidada queda
  por su fecha, no forzada arriba (diferencia deliberada con /historial, CL-3).
- El dashboard no consulta `plan_items`: los pares salen de los `planned_*` de
  `series`, igual que /fin.
- Coordenadas del SVG por índice de punto (no hay que parsear fechas en el
  render); el eje X muestra las fechas de los extremos.
- `DASH_GENERATED` se imprime con `OUTPUT_PATH.as_posix()` → "data/dashboard.html"
  aunque el sistema use contrabarras.
- No hay tope de sesiones ni de tamaño del HTML (uso local, RF-04); el JSON puede
  crecer con los años sin problema práctico.
- Estado intermedio deliberado (patrón 002/003): desde T3 ya sale un HTML
  generable; en ningún tramo se arranca el bot ni se abre `data/boxlog.db` real —
  los tests usan `tmp_path` y la base real solo en el ensayo manual de T7.
- README ("Novedades de v0.4" + roadmap), `AGENTS.md` (módulo y comando nuevos,
  **sin pasar de 40 líneas**) y `MEMORY.md` se cierran en T7.
