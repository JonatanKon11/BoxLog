# MEMORY.md — BoxLog

## Estado actual
- Fase: en implementación. Spec, plan y tasks listos (plan §6.6 ajustado al redondeo real); T1–T4 hechas, `core.py` completo (parseo, validaciones, avisos, conversión a 0,5 kg con mitades hacia arriba, duración, resumen y confirmación de /log): 95 tests en verde. Repo creado con primer commit.
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
- `round()` de Python redondea al par (banker's rounding): para el redondeo a 0,5 kg con mitades hacia arriba usar `math.floor(x * 2 + 0.5) / 2` (RF-05).
- `float()` de Python acepta `nan`, `inf` y notación científica (`1e3`): validar antes con regex de solo decimal simple (RF-09). Las repeticiones de /log se devuelven como `int` y la separadora `x`/`X` se normaliza antes de partir.
- Evitar: token en el código o en git, datos personales en el repo, lógica de negocio dentro de los handlers.

## Próximos pasos
1. Implementar T5 de `tasks.md` (db: esquema, perfil y RM).
2. Esquema SQLite: perfiles, ejercicios, RM + historial, sesiones, series.
3. Módulos `core` con cálculos (porcentajes de RM) y sus tests.
4. `commands` y `bot`: `/inicio`, `/fin`, `/hoy`, `/log`.
5. Más adelante: WOD (tipo, cap, tiempo real), calorías METs como estimación, audios, datos de Garmin.
