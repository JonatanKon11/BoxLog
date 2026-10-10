# Tareas 001 — v0.1 Fuerza (BoxLog)

Ordenadas por dependencia. Tests primero: cada tarea de código empieza por escribir sus tests y no se avanza con `python -m pytest` en rojo (spec, criterios de finalización).

- [x] **T1. Preparación del proyecto** — sin RF (soporte; constitución 1)
  - Crear `.venv` (`python -m venv .venv`), `requirements.txt` con `python-telegram-bot`, `python-dotenv` y `pytest`, e instalar; crear la estructura vacía `boxlog/` (`core.py`, `db.py`, `commands.py`, `bot.py`) y `tests/`.
  - Hecho cuando: `pip install -r requirements.txt` instala las tres dependencias y `python -m pytest` recorre `tests/` sin errores de importación (aún 0 tests).

- [x] **T2. core: números, normalización y parseo de /log** — RF-06, RF-09 (parsing), RF-10, RF-11
  - Tests primero: coma/punto, `x` ausente o mal colocada, ceros/negativos, argumentos de más, mayúsculas y espacios múltiples.
  - Implementar `parse_number`, `normalize_exercise`, `parse_log_args`, `format_kg`.
  - Hecho cuando: `python -m pytest tests/test_core.py` en verde con los casos anteriores.

- [x] **T3. core: validaciones y textos de uso** — RF-01 (rangos), RF-02 (rango), RF-05 (validación de %), RF-09, RF-12
  - Tests primero: rangos 30–300 / 100–250, 1–500, porcentajes 1–120 con decimales, aviso de uso con ejemplo, lista de comandos.
  - Implementar `validate_profile`, `validate_rm`, `validate_percentages`, `usage_example`, `help_text`.
  - Hecho cuando: `python -m pytest tests/test_core.py` en verde.

- [x] **T4. core: conversión de /hoy, duración, resumen y confirmación de /log** — RF-04, RF-05, RF-06, CL-5
  - Tests primero: redondeo a 0,5 kg, `70 80 85` sobre un RM, duración "1 h 23 min" / "45 min", volumen y máx. con peso real, pares `plan→real` solo de series con plan, sesión vacía en una línea, confirmación de /log con y sin plan.
  - Implementar `round_half_kg`, `convert_percentages`, `format_duration`, `build_summary`, `format_log_confirmation`.
  - Hecho cuando: `python -m pytest tests/test_core.py` en verde y `core` no importa Telegram ni sqlite3.

- [ ] **T5. db: esquema, perfil y RM** — RF-01 (historial), RF-02, RNF-3 (base)
  - Tests primero: creación de tablas con `foreign_keys=ON`, perfil solo inserción (vigente = último id), RM vigente = último id del ejercicio, lista de RM vigentes vacía y con datos.
  - Implementar en `db.py`: esquema (`profile`, `rm_history`, `sessions`, `plan_items`, `series`), inserción de perfil y RM, consultas de vigentes.
  - Hecho cuando: `python -m pytest tests/test_db.py` en verde sobre una BD temporal de `tmp_path`.

- [ ] **T6. db: sesiones, plan y series** — RF-03, RF-05, RF-06, RF-07, CL-11
  - Tests primero: una única sesión abierta, cierre, persistencia al cerrar y reabrir la conexión (reinicio simulado), creación/reemplazo de plan_items con `consumed`, consumo en orden, series con `plan_item_id`, restauración al deshacer y caso plan_item borrado (SET NULL), borrado de la última serie.
  - Implementar las funciones de sesión, plan y series en `db.py`.
  - Hecho cuando: `python -m pytest tests/test_db.py` en verde.

- [ ] **T7. commands: /perfil, /rm y /rms** — RF-01, RF-02, RF-09, CL-6
  - Tests primero: carga y confirmación con coma decimal, fuera de rango → un solo aviso de uso, RM guardado y listado, /rms vacío sugiere /rm, funcionan sin sesión abierta.
  - Implementar los tres comandos en `commands.py` (core + db).
  - Hecho cuando: `python -m pytest tests/test_commands.py` en verde.

- [ ] **T8. commands: /inicio y /fin** — RF-03, RF-04, CL-1, CL-2, CL-5
  - Tests primero: apertura, aviso con fecha y sugerencia de /fin si ya estaba abierta, cierre con resumen completo (duración, series, reps, volumen real, máx., pares plan→real, volumen total), /fin sin sesión, sesión sin series.
  - Implementar `/inicio` y `/fin` en `commands.py`.
  - Hecho cuando: `python -m pytest tests/test_commands.py` en verde.

- [ ] **T9. commands: /hoy** — RF-05, CL-2, CL-4, CL-10
  - Tests primero: conversión con redondeo y respuesta con coma decimal, sin sesión → aviso RF-04, sin RM → aviso "No tengo RM…", repetir /hoy reemplaza el plan y reinicia el orden (series anteriores intactas), porcentaje fuera de rango → aviso de uso.
  - Implementar `/hoy` en `commands.py`.
  - Hecho cuando: `python -m pytest tests/test_commands.py` en verde.

- [ ] **T10. commands: /log y /deshacer** — RF-06, RF-07, CL-2, CL-3, CL-8, CL-9
  - Tests primero: serie con plan en orden y confirmación `serie N … (plan …)`, sin plan → `planned=NULL` sin error, sin sesión → aviso, formato inválido → un solo aviso de uso, /deshacer con y sin series, confirmación de lo borrado y plan_item liberado para la siguiente serie.
  - Implementar `/log` y `/deshacer` en `commands.py`.
  - Hecho cuando: `python -m pytest tests/test_commands.py` en verde.

- [ ] **T11. bot: conexión, dueño y comandos desconocidos** — RF-08, RF-12, CL-7, CL-12, RNF-1, RNF-2
  - Tests primero: `is_owner` con ID correcto y ajeno, texto de respuesta en español, comando desconocido y texto libre → lista de comandos; sin red real.
  - Implementar `bot.py`: `.env` (`TELEGRAM_TOKEN`, `OWNER_ID`), registro de handlers con `filters.User(OWNER_ID)`, fallbacks de comandos y texto.
  - Hecho cuando: `python -m pytest tests/test_bot.py` en verde y el diff no contiene el token (`.env` fuera de git).

- [ ] **T12. Prueba de punta a punta del ciclo completo** — RF-01 a RF-12, CL-1 a CL-12 (cierre de la spec)
  - Tests primero: un test de ciclo `/inicio → /hoy → /log → /log → /deshacer → /fin` con BD temporal que verifica la confirmación de cada /log, el plan aplicado en orden, el valor devuelto tras /deshacer y el resumen final (duración, volumen con peso real, pares plan→real, volumen total); más el recorrido de los avisos (sin sesión, formatos inválidos, ID ajeno ignorado).
  - Implementar solo los ajustes que destapen los tests.
  - Hecho cuando: `python -m pytest` completa en verde, todos los RF y CL de la spec tienen su test y el diff final no contiene token ni datos personales.
