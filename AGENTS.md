# AGENTS.md — BoxLog

Bot de Telegram personal para registrar entrenamientos de crossfit. Portfolio para GitHub.

## Stack y estructura
- Python, SQLite, python-telegram-bot y pytest en Windows; paquete único `boxlog/` con `core.py` (cálculos puros), `db.py` (acceso a datos), `commands.py` (comandos) y `bot.py` (arranque y wiring). Tests en `tests/`.
- La lógica vive en `core` y `db`; la interfaz solo orquesta.

## Comandos
- Entorno e instalación: `python -m venv .venv` (activar `.venv\Scripts\activate`), luego `pip install -r requirements.txt`.
- Tests: `python -m pytest` · Bot: `python -m boxlog.bot`.

## Convenciones
- Archivos, funciones y variables en inglés; comentarios y docs en español; código claro y breve.
- Mensajes al usuario en español; kilos con coma decimal (22,5).
- Sin claves en el código: el token va en variable de entorno `.env` (nunca en git).

## Reglas de dominio
- v0.1: `/perfil`, `/rm`, `/inicio`, `/fin`, `/hoy`, `/log`. Comandos con formato fijo, no lenguaje natural.
- Una serie por mensaje: `/log clean 84x5` guarda peso planificado y peso real.
- La sesión se abre con `/inicio` y se cierra con `/fin`; de ahí sale la duración.
- `/hoy` convierte porcentajes del RM a kilos; RM y perfil (peso, altura) tienen historial.
- v0.1 solo fuerza; calorías siempre como estimación.

## Forma de trabajar
1. **Al empezar:** leer `MEMORY.md`, `docs/constitution.md` y la spec activa (`specs/NNN-*/`) antes de tocar código.
2. Implementar lo mínimo de la tarea, con tests.
3. **Al terminar:** actualizar `MEMORY.md` (estado, decisiones, aprendizajes, próximos pasos).

## Límites
- **Siempre:** token fuera del código y de git · tests en pytest · `data/` y `.env` en `.gitignore` · mantener `MEMORY.md` al día.
- **Pregunta antes:** añadir dependencias · cambiar la estructura del paquete · tocar el modelo de datos de SQLite · enviar el perfil o los RM fuera de la base local · mostrarlos en logs.
- **Nunca:** subir claves, `.env` o datos personales a git · inventar decisiones sin registrarlas.
- El perfil (peso y altura) y los RM son datos que el proyecto guarda por diseño: no preguntes por ellos.

## Memoria
- `MEMORY.md`: leer al empezar y actualizar al terminar cada tarea.

## Verificación
- `pytest` en verde antes de dar una tarea por terminada; revisar que no haya token ni datos personales en el diff.
