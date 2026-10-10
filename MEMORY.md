# MEMORY.md — BoxLog

## Estado actual
- Fase: spec. Ya existen `AGENTS.md`, `MEMORY.md`, `docs/constitution.md` y la spec 001 (`specs/001-strength-logging/spec.md`); todavía no hay código. Repo creado con primer commit.
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
- Todavía no hay aprendizajes de código; ir aquí los fallos y hallazgos de cada tarea.
- Evitar: token en el código o en git, datos personales en el repo, lógica de negocio dentro de los handlers.

## Próximos pasos
1. Resolver la duda abierta de la spec (unidades de altura) y escribir `plan.md` y `tasks.md` de la spec 001 (`specs/001-strength-logging/`).
2. Esquema SQLite: perfiles, ejercicios, RM + historial, sesiones, series.
3. Módulos `core` con cálculos (porcentajes de RM) y sus tests.
4. `commands` y `bot`: `/inicio`, `/fin`, `/hoy`, `/log`.
5. Más adelante: WOD (tipo, cap, tiempo real), calorías METs como estimación, audios, datos de Garmin.
