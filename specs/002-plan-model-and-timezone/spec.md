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

## Requisitos funcionales
- RF-01 Marca de serie: Cuando el sistema registra una serie (/log), deberá guardar junto
  a ella la marca de tiempo en que se registró, en UTC.
  - CA: el nuevo campo es `series.logged_at`; se rellena en cada /log con la hora UTC del
    momento, en el mismo formato ISO que el resto de marcas.
  - CA: las series existentes (creadas antes de esta versión) quedarán con `logged_at`
    vacío; no se inventa ningún dato para ellas.
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
    profile y rm_history) se convierten a UTC en la migración sumando 3 horas a la hora
    local almacenada.
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
  - CA: el resto de /hoy no cambia: sin sesión aviso de RF-04, sin RM aviso "No tengo RM…",
    repetir /hoy reemplaza el plan y reinicia el orden (RF-05 de la spec 001).
- RF-04 Confirmación de /log con plan: Cuando una serie toma su plan del /hoy vigente, la
  confirmación de /log mostrará el plan con sus repeticiones cuando las tenga.
  - CA: sin reps el formato sigue siendo "(plan 84)"; con reps será "(plan 66 kg x 1)"; con
    rango, "(plan 64-68 kg x 1)" (o "(plan 64-68)" si no hay reps); si el rango se colapsó
    a un único valor (RF-03), se mostrará como plan simple (p. ej. "(plan 80 kg x 1)").
  - CA: el consumo del plan no cambia: una entrada del plan corresponde a un /log, en
    orden; aunque las repeticiones reales no coincidan con las del plan (plan de 3 reps,
    real de 5), la serie se guarda igual y sin aviso.
- RF-05 Desviación con rangos: En el resumen de /fin, el par plan→real de una serie cuyo
  plan fue un rango se mostrará informativo.
  - CA: el par será "<mín>-<máx>-><real>" (p. ej. "64-68->66"); no se evalúa si el real
    cayó dentro del rango.
  - CA: el resto del resumen (volumen con peso real, máximo, volumen total, duración) no
    cambia.
- RF-06 Migración de la base: El sistema deberá migrar la base existente de la versión 1
  a la versión 2 conservando todos los datos.
  - CA: el esquema 2 añade a `plan_items` las columnas `reps` (entero, vacío si no aplica)
    y `range_max_kg` (decimal, vacío si no aplica), y a `series` la columna `logged_at`
    (texto, vacío para lo ya existente).
  - CA: la migración se ejecutará solo cuando `PRAGMA user_version` sea 1; será
    idempotente (repetirla no cambia nada) y ocurrirá dentro de una transacción.
  - CA: antes de migrar, el sistema creará una copia de seguridad automática de la base
    (mismo directorio, sufijo ".bak-v1"); la copia no se recrea si ya existe.
  - CA: la migración convierte a UTC todas las marcas existentes, sin excepción:
    sessions.started_at y sessions.ended_at y también los created_at de profile y de
    rm_history (RF-02); no se tocan datos fuera de esa conversión y de las columnas nuevas.

## Requisitos no funcionales
- RNF-1 Durabilidad: los entrenamientos, RM y perfil existentes no se pierden bajo ningún
  escenario de esta versión; hay test que lo prueba desde una base v1 sintética con datos.
- RNF-2 Sin dependencias nuevas: la conversión de zona se hace con aritmética de horas;
  `requirements.txt` no cambia.
- RNF-3 Claridad: todo aviso de RF-03 indica el motivo y qué enviar a continuación.
- RNF-4 Idioma: mensajes en español con kilos y horas legibles, sin formato interno de la
  base (los textos de confirmación son de la spec 001 más los matices de RF-04/RF-05).

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
  65x5) → serie guardada igual, sin aviso; la confirmación muestra "(plan 65 kg x 3)".
- CL-7 /log sin plan o con plan agotado → sin cambios (spec 001, CL-3).
- CL-8 /deshacer de una serie con plan de rango o con reps → se libera esa entrada del
  plan exactamente como con el plan simple.
- CL-9 Series antiguas (anteriores a la migración): `logged_at` vacío y su planificado
  intacto; /fin de una sesión vieja muestra los pares como hasta ahora.
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
  separado (RM 100, plan "80,2-80,4x1" → ambos extremos 80 kg); si tras redondear
  coinciden, la entrada se guarda y se muestra como un valor único sin rango.

## Fuera de alcance
- Dashboard o cualquier lectura agregada de `data/boxlog.db` (v0.3).
- Menú de comandos, botones, mensaje suelto "52x3", /historial y respuesta de error
  interno (spec 003 posterior).
- Editar o borrar series distintas de la última; ver el historial de RM.
- Acumular repeticiones reales para completar las del plan; avisar por desviación de reps.
- Zonas horarias múltiples, horario de verano y configuración del desfase por usuario.
- WOD, calorías, audios y datos de Garmin (specs futuras).

## Preguntas abiertas
- Ninguna. Tras la revisión quedaron resueltos y escritos en los RF/CL: el cambio de día
  por UTC se decide en hora local (CL-12), el en-dash se acepta como guion menos (CL-15),
  el redondeo de extremos puede colapsar el rango a valor único (CL-16) y la migración
  cubre también los created_at de profile y rm_history (RF-06). No queda ninguna decisión
  pendiente para escribir plan.md y tasks.md.

## Criterios de finalización
- Tests primero: se escriben antes que el código; no se avanza con tests en rojo;
  `python -m pytest` en verde antes de cada commit.
- Test de migración que arranca desde una base v1 sintética con perfil, RM, sesiones,
  plan y series, y verifica que todo sobrevive y que las horas quedan convertidas.
- Todos los RF y CL cubiertos con pruebas automatizadas.
- Verificación final: sin token ni datos personales en el diff; la base real del usuario
  tiene copia de seguridad antes de la primera migración.
