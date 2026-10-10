# Constitución de BoxLog

1. **Stack mínimo.** Python, SQLite, python-telegram-bot, pytest y python-dotenv. Dependencias nuevas solo con aprobación previa.
2. **Spec antes que código.** Las especificaciones viven en `specs/NNN-nombre/` con `spec.md`, `plan.md` y `tasks.md`; si no está en la spec, no se implementa y si el código lo hace, se refleja en la spec. `docs/` contiene solo la constitución.
3. **Lógica separada de la interfaz.** Los cálculos viven en `core.py` y el acceso a datos en `db.py`; `commands.py` y `bot.py` solo orquestan, sin lógica de negocio.
4. **Tests primero.** Se escriben antes que el código; no se avanza a la siguiente tarea con tests en rojo; `python -m pytest` en verde antes de cada commit.
5. **Datos y token protegidos.** El token solo en `.env`; `data/` y `.env` en `.gitignore`; nunca subir a git ni mostrar en logs el token, `.env` o datos personales (peso, altura, RM). El bot responde únicamente a mi Telegram ID; los entrenamientos nunca se pierden: todo cambio de esquema de SQLite conserva los datos existentes.
6. **Idioma.** Identificadores, módulos y nombres de archivo en inglés; mensajes al usuario, comentarios y documentación en español (kilos con coma decimal: 22,5).
