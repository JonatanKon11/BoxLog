# BoxLog

Bot personal de Telegram para registrar sesiones de fuerza de CrossFit: perfil, RM por
ejercicio, series con peso planificado y real, y un resumen al cerrar la sesión.
Los datos viven en una base SQLite local (`data/boxlog.db`); no hay servidor ni nube.
Solo responde a un único usuario (tu ID de Telegram).

## Qué hace en v0.1

v0.1 es solo fuerza: kilos, series y repeticiones. Los porcentajes de /hoy salen del RM
vigente; los kilos se muestran siempre con coma decimal (22,5) y también se aceptan así
al escribirlos.

| Comando | Qué hace | Ejemplo real |
| --- | --- | --- |
| `/perfil <peso> <altura>` | Guarda tu peso (kg) y tu altura (cm) | `/perfil 78 175` → `Perfil guardado: 78 kg · 175 cm` |
| `/rm <ejercicio> <kg>` | Guarda el RM de un ejercicio (con historial) | `/rm clean 120` → `RM de clean guardado: 120 kg` |
| `/rms` | Lista los RM vigentes | `/rms` → `RM vigentes:` / `clean: 120 kg` / `front squat: 170 kg` |
| `/inicio` | Abre la sesión de entrenamiento | `/inicio` → `Sesión iniciada a las 20:35` |
| `/hoy <ejercicio> <porcentajes...>` | Convierte porcentajes del RM a kilos y guarda el plan | `/hoy clean 70 80 85` → `70% → 84 kg` / `80% → 96 kg` / `85% → 102 kg` |
| `/log <ejercicio> <peso>x<repeticiones>` | Registra una serie (el número es el peso real) | `/log clean 84x5` → `clean · serie 1: 84 kg × 5 (plan 84)` |
| `/deshacer` | Borra la última serie de la sesión | `/deshacer` → `Borrada: clean 95x3` |
| `/fin` | Cierra la sesión y muestra el resumen | `/fin` → `Duración: 45 min` / `clean: 2 series · 8 repeticiones · volumen 708 kg · máx 96 kg` / `  plan→real: 84→84, 96→96` / `Volumen total: 708 kg` |
| `/ayuda` | Muestra la lista de comandos (también `/start`) | `/ayuda` → la lista completa de la izquierda |

Un entrenamiento completo con esos ejemplos, en orden:

```
/inicio            → Sesión iniciada a las 20:35
/hoy clean 70 80 85 → 70% → 84 kg / 80% → 96 kg / 85% → 102 kg
/log clean 84x5    → clean · serie 1: 84 kg × 5 (plan 84)
/log clean 95x3    → clean · serie 2: 95 kg × 3 (plan 96)
/deshacer          → Borrada: clean 95x3
/log clean 96x3    → clean · serie 2: 96 kg × 3 (plan 96)
/fin               → … volumen 708 kg · máx 96 kg · plan→real: 84→84, 96→96
```

Además:

- Los ejercicios admiten varias palabras: `front squat`, `clean and jerk`, …
- Cada serie toma en orden el siguiente valor del plan de /hoy; si no hay plan (o ya se
  consumió todo), la serie se guarda igualmente sin peso planificado.
- El resumen de `/fin` agrupa por ejercicio y usa siempre el peso real para volumen y máximo.
- Fuera de rango o con formato inválido, el bot responde un solo aviso con el motivo y un
  ejemplo; sin sesión abierta responde `No hay sesión abierta, envía /inicio`.
- Solo contesta a su dueño: cualquier otro ID de Telegram se ignora sin responder.

## Novedades de v0.2: modelo de plan y zona horaria

`/hoy` acepta cuatro tipos de entrada, mezclables en el mismo mensaje; cada una define un
ítem del plan que `/log` consume en orden:

| Entrada | Significado | Respuesta |
| --- | --- | --- |
| `70` | 70 % del RM | `70% → 84 kg` |
| `65x3` | 65 % del RM, 3 repeticiones | `65% × 3 → 52 kg` |
| `80-85` | rango de 80 a 85 % del RM | `80-85% → 64-68 kg` |
| `80-85x1` | rango con repeticiones | `80-85% × 1 → 64-68 kg` |

- Ejemplos: `/hoy clean 70` · `/hoy clean 65x3` · `/hoy clean 80-85` ·
  `/hoy clean 80-85x1` · mezclado: `/hoy clean 70 65x3 80-85 80-85x1`.
- La confirmación de `/log` muestra el plan que consumió, con el signo × en todo:
  `/log clean 66x1` → `clean · serie 1: 66 kg × 1 (plan 64-68 kg × 1)`; y el resumen de
  `/fin` empareja plan y real, rango incluido: `plan→real: 64-68→66`.
- Los kilos o las reps reales distintos del plan se registran sin aviso: manda lo que
  escribes.
- Se aceptan también en-dash (`80–85x1`) y `X` mayúscula (`65X3`); el primer error de
  izquierda a derecha se responde con el motivo y un ejemplo, sin tocar la base.

**Zona horaria.** Hora fija de Argentina, UTC-3 (sin horario de verano). La base guarda
siempre UTC y los mensajes muestran hora local; "hoy" se decide en hora local, así que
una sesión que empieza a las 22:00 sigue apareciendo como de hoy.

**Migración automática.** Al arrancar, `init_schema` mira `PRAGMA user_version`: una base
de la v0.1 (versión 1) se migra sola a la 2. Primero crea la copia de seguridad
`data/boxlog.db.bak-v1` (si ya existe, no se vuelve a crear ni se sobrescribe); después,
dentro de una transacción, añade las columnas de plan (`reps`, `range_max_kg`,
`planned_reps`, `planned_max_kg`) y convierte todas las marcas existentes a UTC sumando
3 horas. Si algo falla se deshace todo y la base queda como estaba, con el respaldo
disponible. Una carpeta sin datos nace directamente en la versión 2, sin copia.
(Decisión de cierre: migrar con el bot apagado y con una copia manual previa propia.)

## Instalación y arranque (Windows)

1. **Clona el repo y crea el entorno virtual** (desde la raíz del proyecto):

   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Crea el archivo de configuración**:

   ```powershell
   Copy-Item .env.example .env
   ```

   Edita `.env` y rellena las dos variables:

   - `TELEGRAM_TOKEN`: crea el bot en Telegram hablando con **@BotFather** → `/newbot` →
     copia el token que te dé.
   - `OWNER_ID`: tu ID numérico de Telegram; pídelo a **@userinfobot** en Telegram y copia
     el número.

   El archivo `.env` está en `.gitignore`: nunca se sube a git y el token no aparece en el
   código. No lo compartas.

3. **Arranca el bot**:

   ```powershell
   python -m boxlog.bot
   ```

   Abre tu bot en Telegram y escribe `/ayuda`. Para pararlo, `Ctrl+C`.

   Si falta alguna variable en `.env`, el bot no arranca y te dice cuál falta.

## Tests

```powershell
.venv\Scripts\activate
python -m pytest
```

Son tests de pytest sobre bases temporales (`tmp_path`): no usan red ni token real, y
comprueban desde la lógica pura (parseo, redondeo, resumen) hasta un recorrido completo
de punta a punta (`tests/test_e2e.py`) pasando por la base de datos y por el despacho de
comandos de `bot.dispatch`.

## Estructura del proyecto

```
boxlog/
  core.py      # lógica pura: parseo, validaciones, cálculos y textos de los mensajes
  db.py        # acceso a datos SQLite: esquema, perfil, RM, sesiones, plan y series
  commands.py  # orquestación: valida con core, guarda con db y devuelve la respuesta
  bot.py       # cableado con Telegram: .env, filtro por dueño y despacho a commands
tests/         # tests de cada capa + test de punta a punta (test_e2e.py)
specs/         # especificaciones vivas de cada funcionalidad (001-strength-logging/, 002-plan-model-and-timezone/)
docs/          # constitution.md: reglas del proyecto
data/          # base de datos SQLite (en .gitignore)
.env           # token y ID (en .gitignore; plantilla en .env.example)
```

La separación tiene un motivo: `core` no depende de nada externo, `db` encapsula todo lo
de SQLite y `commands` no importa Telegram — recibe una conexión y argumentos y devuelve
texto. Así la lógica de entrenamiento se prueba sin red, sin token y sin instalar el bot;
`bot.py` es solo la parte que habla con Telegram.

## Cómo está desarrollado

Spec-Driven Development: cada funcionalidad se especifica antes de codificar, en
`specs/NNN-*/` (`spec.md` con los requisitos y criterios, `plan.md` con la arquitectura y
`tasks.md` con las tareas ordenadas por dependencia), con `docs/constitution.md` como
reglas del proyecto. Trabajo con tests primero: se escribe el test, se ve fallar y
después se implementa lo mínimo para que pase. La spec se mantiene viva y se ajusta
cuando la realidad destapa algo (por ejemplo, el redondeo a 0,5 kg con mitades hacia
arriba).

## Roadmap

- **v0.2 (hecha, spec 002)** — modelo de plan (reps y rangos de porcentaje) y zona horaria UTC-3.
- **v0.3** — WOD (tipo, cap, tiempo real) y calorías como estimación.
- **v0.4** — Registro por audio.
- **v0.5** — Análisis de datos de Garmin.

## Nota

Proyecto personal hecho como portfolio: herramienta de uso propio (un solo usuario, datos
locales) y referencia de formas de trabajo (spec-driven, tests primero, separación de
capas). No es un producto para terceros.
