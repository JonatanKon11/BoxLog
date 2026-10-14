# MEMORY.md — BoxLog

## Estado actual
- Fase: 001-strength-logging cerrada (T1–T12 hechas + ajuste de T11 en `bot.py`). Spec viva actualizada; `core.py`, `db.py`, `commands.py` y `bot.py` completos; 245 tests en verde. Hay `.env` real local (ignorado por git) y los tests de config lo parchean con la fixture `sin_dotenv`.
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

## Próximos pasos
1. Commit de T1–T12 (spec 001 cerrada; no subir nunca `.env` ni `data/`).
2. Decidir la siguiente spec (v0.2: WOD, calorías METs como estimación, audios, datos de Garmin).
