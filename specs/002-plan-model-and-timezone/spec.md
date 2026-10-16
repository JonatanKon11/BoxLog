# Spec 002 — Modelo de plan y zona horaria (BoxLog v0.2)

## Contexto y objetivo
BoxLog registra sesiones de fuerza con un plan porcentual y series reales. Esta
especificación da el salto de v0.1 a v0.2 sin cambiar la interfaz: el plan pasa a poder
expresar repeticiones y rangos de porcentaje, todas las marcas de tiempo se guardan en
UTC para soportar análisis futuro, y la base existente migra sin perder nada. Es la base
sobre la que se apoyará una futura spec de dashboard (v0.3, fuera de alcance aquí).

## Alcance
Solo modelo de datos y su lógica asociada: sintaxis del plan en /hoy, consumo y
confirmación del plan con repeticiones/rangos, desviación en /fin, zona horaria de las
marcas y migración de la base de 1 a 2. No se añade ningún comando nuevo.

*Notación: **(A-1)** … **(A-5)** marca, dentro de los requisitos, los cambios de la
revisión que resolvió las ambigüedades A-1 a A-5 del `plan.md`.*

## Requisitos funcionales
- RF-01 Marca de serie: Cuando el sistema registra una serie (/log), deberá guardar junto
  a ella la marca de tiempo en que se registró, en UTC. **(A-2)**
  - CA: la marca usa el campo existente `series.created_at` (no se crea `logged_at` ni
    ninguna columna nueva para esto); desde la migración se rellena en UTC con el mismo
    formato ISO que el resto de marcas.
  - CA: las series existentes conservan su hora: la migración la convierte a UTC sumando
    3 horas como cualquier otra marca (RF-06); no se borra ni se inventa ningún dato.
- RF-02 Zona horaria: El sistema deberá guardar todas las marcas de tiempo en UTC y
  mostrarlas en hora local (UTC-3, Argentina, sin horario de verano).
  - CA: la conversión se hará con un desfase fijo de -3 horas, definido como constante
    con comentario en `core.py`; no se usan dependencias nuevas ni base de zonas.
  - CA: RF-03 de la spec 001 se mantiene: las horas seguirán mostrándose legibles
    ("las 20:35", "el 09/10 a las 20:35") y la duración de /fin no cambia de formato.
  - CA: la distinción de "hoy" de los mensajes de /inicio y /fin se decidirá en hora
    local, no en UTC: una sesión que empieza a las 22:00 hora local (01:00 UTC del día
    siguiente) se mostrará como de hoy (CL-12).
  - CA: las marcas existentes (sessions.started_at, sessions.ended_at, created_at de
    profile, rm_history y series) se convierten a UTC en la migración sumando 3 horas a
    la hora local almacenada. **(A-2)**
- RF-03 Plan con repeticiones y rangos: Cuando el usuario envía /hoy, el sistema deberá
  aceptar entradas de plan con el mismo orden que /log (valor x repeticiones):
  "65x3" (65% por 3 reps), "70" (70% sin reps), "80-85x1" (rango de 80 a 85% por 1 rep) y
  "80-85" (rango sin reps).
  - CA: cada entrada se convertirá a kilos con el RM vigente y el redondeo a 0,5 kg de la
    spec 001; el mínimo del rango se guarda en el peso planificado y el máximo en un campo
    nuevo (`range_max_kg`); las repeticiones van en un campo nuevo (`reps`), vacío cuando
    la entrada no las trae.
  - CA: el separador de rango es el guion menos "-" o el guion largo "–" (en-dash), que
    son equivalentes: "80-85x1" y "80–85x1" son el mismo plan; la salida usará siempre el
    guion menos.
  - CA: los porcentajes no admiten espacios internos ("65 x 3" no es una entrada válida,
    CL-13) y un signo menos en un porcentaje no forma rango: "-5", "80-" y "-80-85" se
    rechazan (CL-14).
  - CA: los porcentajes aceptan decimales con coma o punto y deben estar entre 1 y 120;
    en un rango el mínimo deberá ser menor que el máximo; las repeticiones deberán ser un
    entero mayor o igual a 1.
  - CA: cada extremo de un rango se convertirá a kilos y se redondeará a 0,5 kg por
    separado; si tras redondear ambos extremos coinciden, la entrada se guardará y
    mostrará como un valor único, sin rango (CL-16).
  - CA: fuera de esas reglas se aplica RF-09 con un aviso que indica el motivo y el
    ejemplo (p. ej. "El porcentaje tiene que estar entre 1 y 120. Usa /hoy clean 70 80 85").
  - CA: las entradas se procesan de izquierda a derecha y solo se avisa el **primer**
    error encontrado (con su motivo y ejemplo); no se lista ningún otro. **(A-4)**
  - CA: la separadora de repeticiones admite mayúscula o minúscula, como en /log:
    "65X3" = "65x3". **(A-5)**
  - CA: la respuesta tendrá una línea por entrada, con el mismo signo × que las
    confirmaciones de /log: sin reps "70% → 84 kg" (sin cambios de la 001), con reps
    "65% × 3 → 52 kg", con rango "80-85% × 1 → 64-68 kg" (o "80-85% → 64-68 kg" sin
    reps). **(A-1)**
  - CA: el resto de /hoy no cambia: sin sesión aviso de RF-04, sin RM aviso "No tengo RM…",
    repetir /hoy reemplaza el plan y reinicia el orden (RF-05 de la spec 001).
- RF-04 Confirmación de /log con plan: Cuando una serie toma su plan del /hoy vigente, la
  confirmación de /log mostrará el plan con sus repeticiones cuando las tenga.
  - CA: sin reps el formato sigue siendo "(plan 84)"; con reps será "(plan 66 kg × 1)"; con
    rango, "(plan 64-68 kg × 1)" (o "(plan 64-68)" si no hay reps); si el rango se colapsó
    a un único valor (RF-03), se mostrará como plan simple (p. ej. "(plan 80 kg × 1)").
    **(A-1: se usa ×, unificando la "x" de la revisión inicial)**
  - CA: al registrar la serie, el plan se **copia a la propia serie**: `planned_reps` y
    `planned_max_kg` (vacíos si no había plan o si el plan no tenía reps/rango); /fin y el
    futuro dashboard leen de la serie, sin depender de `plan_items`. Las series existentes
    quedan con ambos campos vacíos. **(A-3)**
  - CA: el consumo del plan no cambia: una entrada del plan corresponde a un /log, en
    orden; aunque las repeticiones reales no coincidan con las del plan (plan de 3 reps,
    real de 5), la serie se guarda igual y sin aviso.
- RF-05 Desviación con rangos: En el resumen de /fin, el par plan→real de una serie cuyo
  plan fue un rango se mostrará informativo.
  - CA: el par será "<mín>-<máx>→<real>" (p. ej. "64-68→66", con la misma flecha "→" de
    la 001); no se evalúa si el real
    cayó dentro del rango. Se construye desde los campos copiados en la serie
    (`planned_weight_kg` + `planned_max_kg`), no de `plan_items` (A-3); una serie sin
    plan copiado sigue mostrando su par actual o nada, como la 001.
  - CA: el resto del resumen (volumen con peso real, máximo, volumen total, duración) no
    cambia.
- RF-06 Migración de la base: El sistema deberá migrar la base existente de la versión 1
  a la versión 2 conservando todos los datos.
  - CA: el esquema 2 añade a `plan_items` las columnas `reps` (entero, vacío si no aplica)
    y `range_max_kg` (decimal, vacío si no aplica), y a `series` las columnas
    `planned_reps` (entero) y `planned_max_kg` (decimal), ambas vacías para las series ya
    existentes. No se crea ninguna columna de hora: la marca de serie ya existe
    (`series.created_at`, RF-01). **(A-2, A-3)**
  - CA: la migración se ejecutará solo cuando `PRAGMA user_version` sea 1; será
    idempotente (repetirla no cambia nada) y ocurrirá dentro de una transacción.
  - CA: antes de migrar, el sistema creará una copia de seguridad automática de la base
    (mismo directorio, sufijo ".bak-v1"); la copia no se recrea si ya existe.
  - CA: la migración convierte a UTC todas las marcas existentes, sin excepción:
    sessions.started_at y sessions.ended_at, los created_at de profile y de rm_history y
    el created_at de series (RF-01, RF-02); no se tocan datos fuera de esa conversión y de
    las columnas nuevas. **(A-2)**

## Requisitos no funcionales
- RNF-1 Durabilidad: los entrenamientos, RM y perfil existentes no se pierden bajo ningún
  escenario de esta versión; hay test que lo prueba desde una base v1 sintética con datos.
- RNF-2 Sin dependencias nuevas: la conversión de zona se hace con aritmética de horas;
  `requirements.txt` no cambia.
- RNF-3 Claridad: todo aviso de RF-03 indica el motivo y qué enviar a continuación.
- RNF-4 Idioma: mensajes en español con kilos y horas legibles, sin formato interno de la
  base (los textos de confirmación son de la spec 001 con el signo × unificado en lo que
  muestra el plan, RF-04).

## Casos límite
- CL-1 /hoy con entrada mixta ("70 65x3 80-85x1 80-85"): todas las entradas se procesan
  y el plan se guarda en ese orden.
- CL-2 /hoy con rango invertido ("85-80") o repeticiones no enteras o menores que 1
  ("65x0", "65x2,5") → aviso con motivo y ejemplo; no se guarda nada.
- CL-3 /hoy con porcentaje fuera de rango en cualquier entrada ("130", "0x3") → aviso con
  motivo y ejemplo; no se guarda nada.
- CL-4 /hoy sin sesión abierta o sin RM del ejercicio → avisos de la spec 001, sin cambios.
- CL-5 Repetir /hoy en la misma sesión → el plan (con reps y rangos) se reemplaza y el
  orden se reinicia; las series ya guardadas conservan su planificado original.
- CL-6 /log cuyo plan traía reps distintas a las reales (plan "65x3", /log squat snatch
  65x5) → serie guardada igual, sin aviso; la confirmación muestra "(plan 65 kg × 3)" y
  la serie guarda `planned_reps = 3` (A-1, A-3).
- CL-7 /log sin plan o con plan agotado → sin cambios (spec 001, CL-3).
- CL-8 /deshacer de una serie con plan de rango o con reps → se libera esa entrada del
  plan exactamente como con el plan simple.
- CL-9 Series antiguas (anteriores a la migración): `created_at` convertido a UTC
  conservando su hora real (+3 h), `planned_reps` y `planned_max_kg` vacíos y su
  planificado intacto; /fin de una sesión vieja muestra los pares como hasta ahora.
  **(A-2, A-3)**
- CL-10 Migración repetida o sobre una base ya en la versión 2 → no hace nada, no recrea
  la copia de seguridad.
- CL-11 Base nueva (carpeta sin datos): se crea directamente en la versión 2, sin copia
  de seguridad ni migración.
- CL-12 Cambio de día por UTC: una sesión que empieza a las 22:00 hora local (01:00 UTC
  del día siguiente) se mostrará como "hoy" en los mensajes de /inicio y /fin; la
  comparación de día se hace en hora local, no en UTC (habrá un test con una marca UTC
  cercana a la medianoche).
- CL-13 Espacios en la sintaxis de /hoy: "65 x 3" no se acepta → aviso con motivo y
  ejemplo del formato correcto ("65x3"); no se guarda nada.
- CL-14 Signo menos: "-5", "80-" y "-80-85" se rechazan con aviso que indica el motivo;
  no se interpretan como porcentaje negativo ni como rango.
- CL-15 Guion largo: el en-dash "–" se acepta como equivalente al guion menos en
  rangos ("80–85x1" = "80-85x1"); la salida siempre usa el guion menos.
- CL-16 Redondeo de rangos: cada extremo se convierte a kilos y se redondea a 0,5 kg por
  separado (RM 100, plan "80,1-80,2x1" → ambos extremos 80 kg, colapsa); si tras
  redondear coinciden, la entrada se guarda y se muestra como un valor único sin rango.
  Un empate exacto (p. ej. 40,25 kg, a medio camino entre 40 y 40,5) redondea hacia
  arriba, igual que en la 001 (RF-05): por eso "80-80,5%" sobre RM 50 da 40 y 40,5 y no
  colapsa.
- CL-17 Varias entradas inválidas ("130 65x0 85-80"): se avisa solo el **primer** error de
  izquierda a derecha, con su motivo y ejemplo; no se guarda nada. **(A-4)**
- CL-18 Reps en mayúscula: "65X3" se acepta igual que "65x3" (y "80-85X1" = "80-85x1").
  **(A-5)**
- CL-19 Respuesta de /hoy con los tres formatos: "70% → 84 kg" (sin cambios de la 001),
  "65% × 3 → 52 kg" (con reps) y "80-85% × 1 → 64-68 kg" (con rango), una línea por
  entrada en el orden dado. **(A-1)**

## Fuera de alcance
- Dashboard o cualquier lectura agregada de `data/boxlog.db` (v0.3).
- Menú de comandos, botones, mensaje suelto "52x3", /historial y respuesta de error
  interno (spec 003 posterior).
- Editar o borrar series distintas de la última; ver el historial de RM.
- Acumular repeticiones reales para completar las del plan; avisar por desviación de reps.
- Zonas horarias múltiples, horario de verano y configuración del desfase por usuario.
- WOD, calorías, audios y datos de Garmin (specs futuras).

## Preguntas abiertas
- Ninguna. Las ambigüedades A-1 a A-5 del plan quedaron resueltas por el usuario y
  reflejadas en los RF/CL marcados: respuesta de /hoy con × y sus tres formatos (A-1,
  CL-19), `series.created_at` como marca de serie convertida a UTC sin columna nueva
  (A-2, RF-01), plan copiado a la serie en `planned_reps`/`planned_max_kg` (A-3, RF-04),
  primer error de izquierda a derecha (A-4, CL-17) y "65X3" en mayúscula (A-5, CL-18).
  No queda ninguna decisión pendiente.

## Criterios de finalización
- Tests primero: se escriben antes que el código; no se avanza con tests en rojo;
  `python -m pytest` en verde antes de cada commit.
- Test de migración que arranca desde una base v1 sintética con perfil, RM, sesiones,
  plan y series, y verifica que todo sobrevive y que las horas quedan convertidas.
- Todos los RF y CL cubiertos con pruebas automatizadas.
- Verificación final: sin token ni datos personales en el diff; la base real del usuario
  tiene copia de seguridad antes de la primera migración.
