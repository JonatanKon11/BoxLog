# MEMORY.md — BoxLog

## Estado actual
- Fase: 002-plan-model-and-timezone activa en la rama **spec-002** (sin commits: los hace el usuario). Tareas T1–T4 hechas de T1–T7; 329 tests en verde. Spec 001 cerrada (T1–T12); hay `.env` real local (ignorado por git) y los tests de config lo parchean con la fixture `sin_dotenv`.
- ⚠️ **NO arrancar el bot sobre la base real con el código de spec-002 hasta T6/T7**: `init_schema` rechaza una base v1 con error claro (protección temporal), y mientras tanto las marcas se guardan en UTC sin conversión de muestra (T5 hará el cableado local) — el ensayo de migración es T7, con el bot apagado y copia de seguridad manual.
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
- T4 de la 002: cambiar `_now()` a UTC no rompe la 001 si se devuelve **sin sufijo de huso** (mismo formato ISO; convención "marca sin huso = UTC" de `core._as_utc`): `cmd_fin` resta `datetime.now()` naive y un "+00:00" causaría TypeError. Es un estado intermedio (las horas no se muestran en local hasta T5) — por eso el aviso de no arrancar el bot. Y al testear `insert_series` con `plan_item_id` hay que crear el ítem de verdad o la FK de `series` revienta.

## Próximos pasos
1. Seguir la 002 en spec-002: T5 (commands: /hoy, /log, /inicio, /fin + ajuste de format_start_time + splitter de /hoy con is_number propio), T6 (migración 1→2 y retirada de la protección v1), T7 (ensayo sobre copia + e2e + README + MEMORY y paso manual del usuario con el bot apagado).
2. Commits de la 002 por el usuario al cerrarla; nunca subir `.env` ni `data/`.
