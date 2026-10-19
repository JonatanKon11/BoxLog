# MEMORY.md — BoxLog

## Estado actual
- Fase: **002-plan-model-and-timezone COMPLETA** en la rama **spec-002** (los commits los hace el usuario). Tareas T1–T7 hechas; 361 tests en verde. Spec 001 cerrada (T1–T12); hay `.env` real local (ignorado por git) y los tests de config lo parchean con la fixture `sin_dotenv`.
- ⚠️ **La base real (`data/boxlog.db`) sigue en v1: se migra en el paso manual del usuario** — bot apagado → copia manual `data/boxlog.manual-backup.db` → arranque con el código nuevo (eso migra) → verificación de solo lectura. El ensayo sobre la copia (`data/boxlog.ensayo.db`, ya borrable) salió perfecto: 27 marcas +3 h exactas, 18 series con planned_* NULL, respaldo `.bak-v1` en v1 con los datos originales y la real intacta (mismo sha256).
- v0.2: modelo de plan (reps y rangos de porcentaje), todas las marcas en UTC (hora local UTC-3 fija, sin zoneinfo) y migración 1→2 con respaldo. Decisiones A-1 a A-5 ya resueltas en spec.md/plan.md de la 002.
- Nombre provisional: BoxLog. Destino: GitHub como portfolio.
- Uso inicial: solo yo; si funciona, se comparte.

## Decisiones (y por qué)
- **Nombre:** se mantiene "BoxLog" como provisional.
- **Python + SQLite:** simple, sin servidor, suficiente para un usuario.
- **python-telegram-bot:** librería madura para comandos de Telegram.
- **pytest:** tests desde el primer módulo.
- **Dependencias:** `venv` + `requirements.txt`.
- **Token:** archivo `.env` leído con `python-dotenv` (dependencia autorizada); `.env` va en `.gitignore`.
- **Comandos, no lenguaje natural:** predecible, fácil de testear y de documentar.
- **Estructura:** un paquete `boxlog/` con `core.py`, `db.py`, `commands.py` y `bot.py`, y tests en `tests/`.
- **Un solo usuario:** el bot solo responde a mi Telegram ID; la tabla de usuarios queda para cuando se comparta.
- **`/hoy` recibe porcentajes sin el símbolo:** `/hoy clean 70 80 85`.
- **Git:** `.gitignore` desde el inicio y primer commit antes de escribir código (hecho: `e272823`).
- **Método de trabajo:** Spec-Driven Development, tipo spec-anchored (la spec se mantiene viva).
- **v0.1 solo fuerza:** perfil (peso, altura), RM por ejercicio con historial, sesión con `/inicio` y `/fin`, `/hoy` (RM → kilos), `/log clean 84x5` (peso planificado y real).
- **Windows como entorno de desarrollo:** los comandos de la doc deben funcionar en Windows.

## Aprendizajes y errores a evitar
- `round()` de Python redondea al par (banker's rounding): para el redondeo a 0,5 kg con mitades hacia arriba usar `math.floor(x * 2 + 0.5) / 2` (RF-05).
- `PRAGMA user_version` no admite parámetros (`?`); fijarlo con `PRAGMA user_version = 1` solo cuando está en 0, para no pisar migraciones futuras.
- El test de "sin Telegram" lee el código fuente en minúsculas: los docstrings no deben mencionar la palabra "telegram" (rompieron el test de commands.py).
- Regla de seguridad del proyecto: todo DELETE en SQLite filtra por `session_id` + `exercise` o por `series.id`; el `ON DELETE SET NULL` de `plan_items` deja `planned_weight_kg` intacto, por lo que /deshacer no pierde el peso planificado aunque se repita /hoy.
- `float()` de Python acepta `nan`, `inf` y notación científica (`1e3`): validar antes con regex de solo decimal simple (RF-09). Las repeticiones de /log se devuelven como `int` y la separadora `x`/`X` se normaliza antes de partir.
- Evitar: token en el código o en git, datos personales en el repo, lógica de negocio dentro de los handlers.
- En python-telegram-bot 22.8, `filters.COMMAND` es una instancia (no se invoca): para lista de comandos usar `filters.Command([...])`; la decisión dueño/desconocido vive en `bot.dispatch`, separada de los handlers.
- `load_dotenv()` de python-dotenv busca subiendo desde la ubicación del módulo que lo llama (aquí `boxlog/bot.py`), no desde el directorio de trabajo: en tests hay que parchear `bot.load_dotenv`, un `chdir` no aísla.
- Sin `add_error_handler`, python-telegram-bot imprime el traceback completo ("No error handlers are registered") por cada reintento de red: registrar uno y decidir el texto con `bot.format_error_log(error, token)` (NetworkError/TimedOut → una línea; resto → completo; token redactado siempre).
- T1 de la 002: no cambiar la semántica de una función que otra capa aún usa con el contrato viejo (`core.format_start_time` sigue recibiendo marcas locales hasta T5, cuando db escribe UTC y commands se cablea); si no, la suite se rompe sin motivo y hay que tocar tests de otra tarea. Respetar el orden de riesgo del plan §6 (helpers puros primero).
- T2 de la 002: `split_exercise_and_numbers` con su `is_number` por defecto solo reconoce números simples — "65x3" es sintaxis de /log y caería dentro del nombre del ejercicio; /hoy (T5) debe pasarle un `is_number` propio que acepte tokens del plan, sin duplicar la lógica de separación. El parser de entradas con gramática por regex hace caer solos CL-13 ("65 x 3" como tokens sueltos) y CL-14 (guion fuera de posición); primera-error-de-izquierda-a-derecha sale naturalmente con `return` dentro del bucle.
- Ajuste 2 de T2: en errores de gramática, mostrar el valor ofensivo entre comillas y el motivo deducible (x pegada, negativo, rango incompleto, "no se entiende") en vez de un mensaje genérico; los tests que comparaban el substring "no válida" se actualizaron a los motivos específicos y se añadió un test de texto exacto por variante. Cuando un mensaje ya trae su ejemplo embebido ("65x3", "80-85"), no duplicar "Usa /hoy…".
- T3 de la 002: verificar siempre la aritmética de los ejemplos de spec/tareas — "RM 50 con 80-80,5% → 40 y 40" era falso (40,25 es empate y los empates van hacia arriba → 40,5, no colapsa); el colapso real necesita extremos más juntos (80-80,2 → 40 y 40). El ejemplo de CL-16 ("RM 100, 80,2-80,4 → ambos 80") también era incorrecto: ya se corrigió en la spec ("80,1-80,2x1 → ambos 80 kg, colapsa" + nota de empates). La 001 usa "→" (U+2192) en /hoy y en los pares de /fin, no "->" ASCII: la spec y el plan ya quedaron unificados. `build_summary` ganó el par con rango leyendo `planned_max_kg` opcional del dict de la serie sin cambiar su firma (commands.py intacto).
- T4 de la 002: cambiar `_now()` a UTC no rompe la 001 si se devuelve **sin sufijo de huso** (mismo formato ISO; convención "marca sin huso = UTC" de `core._as_utc`): `cmd_fin` resta `datetime.now()` naive y un "+00:00" causaría TypeError. Es un estado intermedio hasta T5 — por eso el aviso de no arrancar el bot. Y al testear `insert_series` con `plan_item_id` hay que crear el ítem de verdad o la FK de `series` revienta.
- T5 de la 002: al cablear horas, todos los tests que simulaban marcas de la base deben pasar a escribir UTC (`20:35 locales → 20:35 − LOCAL_UTC_OFFSET`) y a leer la hora del texto vía `to_local(marca)`, nunca del trozo HH:MM de la marca (con marcas UTC eso muestra la hora equivocada). `split_exercise_and_numbers` con `is_number=is_plan_token` resuelve solo la separación nombre/valores; los errores (gramática, % fuera de rango) quedan en `parse_plan_entries`, que ya devuelve primer-error con motivo+ejemplo — por eso "0"/"121" dejaron de dar aviso de uso (RF-09/CL-17). `cmd_fin` mezcla marcas naive y `utc_now()` aware: marcar `start` con `tzinfo=timezone.utc` antes de restar.
- T6 de la 002: en una migración, la ruta del respaldo sale mejor de `PRAGMA database_list` (la guarda SQLite en la propia conexión) que de un parámetro nuevo: cambia la firma de `init_schema` y de todos sus llamadores. Nunca `executescript` dentro de la transacción (emite COMMIT implícito); `BEGIN IMMEDIATE` + `ALTER` + `UPDATE` a mano y `connection.rollback()` en el `except` sí garantizan que un `RAISE(ABORT)` de un trigger deje la base entera en v1. El `PRAGMA user_version = 2` dentro de la transacción es lo que hace la migración idempotente: protege contra el doble +3 h. Detalle fácil de pasar por alto: un respaldo que falle a mitad hay que borrarlo, porque el "solo si no existe" lo dejaría bloqueando los intentos siguientes.
- T7 de la 002: el ensayo sobre una copia de la base real confirma lo que los tests ya cubrían (27 marcas +3 h, planned_* NULL, respaldo íntegro) y añade dos lecciones: una base real antigua no tiene sesiones abiertas, así que el ciclo de prueba necesita `/inicio` antes de `/hoy`; y conviene hashear la base real antes y después del ensayo para demostrar que no se tocó (copy2 no modifica el origen, pero el hash lo prueba). El volumen del resumen de /fin hay que calcularlo bien en los tests: 57×4 + 55×2 + 67 + 66×2 = 537, no 437.

## Próximos pasos
1. Cierre de la 002 por el usuario: paso manual con el bot apagado (copia `data/boxlog.manual-backup.db` → arranque que migra la base real → verificación de solo lectura) y commits de la rama spec-002; nunca subir `.env` ni `data/`.
2. Después, la spec que el usuario abra (quedaron para la 003: menú con botones, historial de /hoy y dashboard).
