# Spec 004 — Dashboard local de solo lectura (BoxLog v0.4)

## Contexto y objetivo
BoxLog acumula datos desde la v0.1 (perfil, RM con historial, sesiones con plan y
series) y en la v0.3 mejoró la UX del bot. Esta especificación añade una vista de
conjunto: un dashboard local, de solo lectura, inspirado en un diario de
entrenamiento que se abre con doble clic — racha de días entrenados en grande con 🔥,
RM con su evolución, historial de sesiones de más reciente a más antigua y plan contra
real dentro de cada sesión. Sin servidor, sin instalación y sin librerías: un comando
de Python genera un único archivo HTML autocontenido. El bot y la base no cambian.

## Alcance
Comando generador con acceso solo lectura (RF-01), cabecera con racha y sesiones del
mes (RF-02), sección de RM con evolución y tabla de porcentajes (RF-03), historial con
gráfico de carga máxima por ejercicio (RF-04), plan contra real por sesión (RF-05) y
el documento HTML autocontenido y a prueba de inyección (RF-06). No se cambia el
esquema de la base (sin migración), no se cambia ningún comando del bot y no se
añaden dependencias.

*Notación: al igual que la 003, esta spec no lleva notación de revisión (A-x): las
seis preguntas abiertas del análisis y el añadido de impresión se resolvieron con el
usuario antes de escribirla y quedan reflejados en los RF/CL y en los supuestos.*

## Requisitos funcionales
- RF-01 Comando generador: El sistema deberá generar `data/dashboard.html` con
  `python -m boxlog.dashboard`, leyendo `data/boxlog.db` en modo solo lectura.
  - CA: el archivo es único y autocontenido: CSS y JS inline, datos incrustados como
    JSON y gráficos en SVG dibujados a mano; sin servidor, sin red y sin librerías.
    Se regenera simplemente volviendo a ejecutar el comando.
  - CA: la base jamás se escribe: la conexión usa URI en modo `mode=ro`, no se llama
    `init_schema`, no hay migraciones ni `PRAGMA` de escritura. Un test hashea la base
    antes y después de generar y otro comprueba que un `INSERT` falla en esa conexión.
  - CA: antes de generar se lee `PRAGMA user_version`: 2 → genera; 1 → mensaje
    "La base está en v1: ejecuta el bot una vez para migrarla." y no genera; 0 →
    "La base no está inicializada: ejecuta el bot una vez." y no genera; otro valor →
    "Versión de la base no soportada por este dashboard." y no genera.
  - CA: base inexistente → mensaje "No hay base: ejecuta el bot una vez para crearla."
    y no se crea el archivo de base (la apertura en solo lectura no crea archivos).
  - CA: si la base está ocupada (el bot escribiendo a la vez) se reintenta con espera
    breve unos pocos intentos; si persiste → mensaje "La base está ocupada (el bot
    escribiendo): inténtalo de nuevo en unos segundos." y no se toca el HTML existente.
  - CA: la escritura del HTML es completa y atómica (archivo temporal y reemplazo):
    un fallo a mitad no deja el archivo a medias.
  - CA: el módulo no importa `boxlog.bot` ni `dotenv` ni lee ninguna variable de
    entorno: con un token presente en el entorno, su valor no puede aparecer en el
    HTML (test).
  - CA: al terminar imprime en consola, en español, la ruta y el recuento:
    "Dashboard generado: data/dashboard.html (N sesiones)."
- RF-02 Racha y sesiones del mes: La cabecera mostrará la racha de días entrenados en
  grande con 🔥 y el número de sesiones del mes en curso.
  - CA: un día cuenta si hay al menos una sesión cuya marca de inicio cae en ese día
    en **hora local** (UTC-3, RF-02 de la 002); las marcas UTC se convierten a local
    antes de tomar la fecha. Varias sesiones el mismo día cuentan una vez.
  - CA: la sesión abierta cuenta para su día de inicio y nunca arrastra días
    posteriores aunque siga abierta.
  - CA: la racha son días consecutivos con sesión contando desde hoy: si hoy hay
    sesión, la racha incluye hoy; si hoy no hay pero sí ayer, la racha sigue viva con
    el mismo número y el aviso "Hoy aún no entrenas; la racha sigue viva."; si hoy ni
    ayer → racha 0 y se muestra el último entreno ("Último entreno: 16/10").
  - CA: "Sesiones del mes" = sesiones iniciadas en el mes en curso en hora local,
    incluida la abierta si su inicio cae en ese mes.
  - CA: sin ninguna sesión → estado vacío "Aún no hay sesiones. Abre la primera con
    /inicio" (el mismo de /historial) y racha 0.
  - CA: la fecha "hoy" se calcula al generar y se pasa como parámetro a la función
    pura de racha, para que se pueda testear sin reloj.
- RF-03 Sección RM: La página mostrará el RM vigente por ejercicio, su evolución en el
  tiempo y una tabla de porcentajes sobre el RM vigente.
  - CA: RM vigente por ejercicio = último valor de `rm_history` por ejercicio, con el
    mismo criterio y el mismo orden alfabético que /rms (RF-02 y RF-03 de la 001).
  - CA: evolución: por cada ejercicio, puntos (fecha local de la marca, kilos) en
    orden cronológico, en un SVG dibujado a mano con ejes etiquetados en español.
  - CA: tabla de porcentajes: filas de 50 % a 100 % en pasos de 5 % (11 filas), una
    columna por ejercicio con RM vigente, kilos redondeados a 0,5 con el redondeo
    existente (`round_half_kg`, RF-05 de la 001) y coma decimal en la muestra.
  - CA: sin RM vigente el ejercicio no aparece ni en la tabla ni en la evolución; sin
    ningún RM, la sección muestra "Aún no hay RM. Guarda uno con /rm <ejercicio>
    <kg>".
  - CA: un solo punto de evolución (un solo RM guardado) → solo círculo, sin línea.
- RF-04 Historial y carga máxima: La página listará todas las sesiones, de más reciente
  a más antigua, con duración, volumen y ejercicios, más un gráfico de carga máxima por
  ejercicio en el tiempo.
  - CA: orden por fecha de inicio descendente (`started_at`), sin límite de cantidad
    ni de longitud (a diferencia de /historial no hay tope de 3800 caracteres).
  - CA: cada sesión muestra: fecha local de inicio, duración con el formato de /fin
    (`format_duration`), volumen total, una línea por ejercicio con el mismo formato
    que /fin (`exercise_stat_line`, en el orden de la primera serie vía
    `group_series_by_exercise`) y sus pares plan→real (RF-05).
  - CA: la sesión abierta se marca "abierta desde las 20:35" (mismo texto que
    /historial, RF-03 de la 003) y no muestra duración.
  - CA: el gráfico de carga máxima es **un solo gráfico** con un `<select>` (JS puro,
    sin librerías) que lista los ejercicios con al menos una serie — nombres
    normalizados con `normalize_exercise` (RF-11 de la 001) — y muestra, para el
    elegido, el peso máximo real de cada sesión en el tiempo (fecha local vs kilos),
    en orden cronológico.
  - CA: el `<select>` es el único control de la página; con 1 punto se dibuja solo el
    círculo; sin ninguna serie, la sección muestra el estado vacío de sesiones.
- RF-05 Plan contra real: Cada sesión cerrada mostrará sus pares plan→real, con el
  mismo formato que /fin.
  - CA: los pares salen de una helper pura `plan_real_pairs` extraída de
    `build_summary` con la misma técnica que `exercise_stat_line` (spec 003): **la
    salida de /fin no cambia**.
  - CA: mismo formato que /fin ("plan→real: 70→66, 80-85→52", flecha → de la 001 y
    coma decimal); una serie sin plan no aporta par y una sesión sin ninguna serie
    planificada no muestra la línea, igual que /fin.
  - CA: `planned_reps` o `planned_max_kg` en NULL (datos migrados de la v1) → par en
    el formato simple ("96→98"); nunca un error ni un par vacío.
- RF-06 Documento HTML autocontenido: El generado será un único archivo válido,
  seguro contra inyección y legible en el móvil y al imprimir.
  - CA: sin CDN, sin librerías, sin fuentes externas y sin `fetch` (no funciona en
    `file://`): los datos van en `<script type="application/json">` y el JS solo hace
    `JSON.parse` de su `textContent`.
  - CA: dos capas de escapado: todo texto visible se escapa con `html.escape`
    (incluidas las etiquetas SVG) y el JSON incrustado se genera con `<` reemplazado
    por `\u003c` (neutraliza `</script>`), con `ensure_ascii=False` para que el
    español y los emojis se lean tal cual.
  - CA: todos los textos visibles en español; kilos con coma decimal; fechas y horas
    en hora local (UTC-3).
  - CA: diseño limpio y mobile-first (viewport y CSS responsive): la racha se lee
    bien en pantallas chicas.
  - CA: `@media print`: al imprimir desde el navegador (incluido "Guardar como PDF")
    se ocultan el `<select>` y los demás elementos interactivos; es solo CSS, sin
    botón ni función propia de exportación.
  - CA: cada sección sin datos muestra un estado vacío en español; el HTML se genera
    igual con la base vacía.
  - CA: el HTML contiene datos personales (ver Supuestos) pero nunca el token ni
    rutas ni contenidos de `.env`.

## Requisitos no funcionales
- RNF-1 Solo lectura total: el dashboard no escribe, borra ni migra nada en la base;
  su única escritura es el propio HTML.
- RNF-2 Privacidad: el HTML es un archivo con datos personales (peso, altura, RM y
  series) y vive en `data/`, que ya está en `.gitignore`; nunca se sube a git y el
  token no puede aparecer en él (RF-01 y RF-06).
- RNF-3 Sin dependencias ni red: solo stdlib (`sqlite3`, `json`, `html`, `pathlib`,
  `datetime`); `requirements.txt` no cambia, no hay servidor ni peticiones.
- RNF-4 Idioma y horas: español en toda la salida, kilos con coma decimal y fechas en
  hora local UTC-3 (constitución, reglas 6 y 7; hereda el RNF-1 de la 001).
- RNF-5 Claridad: cada mensaje de error del comando indica qué hacer a continuación
  (migrar, inicializar, reintentar); un fallo nunca deja el HTML a medias.
- RNF-6 Separación: los cálculos (racha, agregados, pares) viven en `core.py` como
  funciones puras — sin importar `sqlite3`, como exige
  `test_core_no_importa_telegram_ni_sqlite` —; las consultas en `db.py`; el comando y
  la plantilla en el módulo nuevo `boxlog/dashboard.py`, que solo orquesta. La
  constitución no cambia.

## Casos límite
- CL-1 Base vacía (sin sesiones, sin RM) → el HTML se genera igual: racha 0,
  "Aún no hay sesiones. Abre la primera con /inicio" y los estados vacíos de cada
  sección; nunca una excepción.
- CL-2 Una sola sesión → racha según su fecha (1 si es hoy); gráficos con un punto
  (círculo sin línea); la tabla de porcentajes, con una sola columna si hay RM.
- CL-3 Sesión abierta olvidada (abierta hace días) → cuenta solo para su día de
  inicio (no infla la racha); en el historial aparece marcada "abierta desde las
  HH:MM" sin duración; si su inicio cayó en este mes, cuenta en "Sesiones del mes".
- CL-4 Racha con hueco (ayer no entrené, antayer sí) → la racha se reinicia: si hoy
  entreno vale 1; si hoy tampoco, racha 0 y "Último entreno" con la fecha de antayer.
- CL-5 Hoy sin entrenar y ayer sí → la racha sigue viva: mismo número que ayer con el
  aviso "Hoy aún no entrenas; la racha sigue viva.".
- CL-6 Marca UTC que cae en otro día que el local (p. ej. `2026-10-17T01:30Z` =
  16/10 22:30 en local) → el día que cuenta es el **local**, no el UTC; probado en
  ambos sentidos del cambio de día (patrón CL-12 de la 002).
- CL-7 Dos sesiones el mismo día → el día cuenta una vez en la racha y "Sesiones del
  mes" muestra 2.
- CL-8 Nombre de ejercicio hostil (`</script><script>alert(1)</script>`,
  `<img src=x onerror=…>`, comillas, `--`) → escapado en las dos capas: el JSON queda
  con `\u003c/script`, el texto visible con entidades; el HTML se abre y no ejecuta
  nada.
- CL-9 Base en v1 sin migrar → mensaje "La base está en v1: ejecuta el bot una vez
  para migrarla."; no se genera el HTML y no se migra nada (solo lectura).
- CL-10 Base inexistente → mensaje "No hay base: ejecuta el bot una vez para
  crearla."; no se crea el archivo `.db`.
- CL-11 El bot escribe a la vez → lectura de un snapshot consistente; reintento corto
  ante "database is locked" y, si persiste, mensaje claro sin dejar el HTML a medias.
- CL-12 Base existente pero sin inicializar (user_version 0) → mensaje "La base no
  está inicializada: ejecuta el bot una vez."; no se escribe nada.
- CL-13 Versión de la base desconocida (distinta de 0, 1 y 2) → mensaje "Versión de
  la base no soportada por este dashboard."; no se intenta interpretar el esquema.
- CL-14 Sesión sin plan o migrada de v1 con `planned_*` en NULL → sin línea de pares
  o par en formato simple; nunca un error.
- CL-15 Ejercicio con series pero sin RM → aparece en el `<select>` del gráfico de
  carga y no en la tabla de porcentajes; ejercicio con RM pero sin series → en la
  tabla y en la evolución, no en el selector.
- CL-16 Regeneración sobre un HTML existente → se sobrescribe completo vía archivo
  temporal; un fallo a mitad deja el HTML anterior intacto.

## Fuera de alcance
- Servidor local (`http.server`), auto-refresh o watch mode, y `fetch` de un JSON
  aparte (no funciona en `file://`): se regenera re-ejecutando el comando.
- Librerías de gráficos o plantillas (Chart.js, pandas, CDN): los SVG se dibujan a
  mano con la stdlib, por regla 1 de la constitución.
- Escribir, editar o borrar datos desde el dashboard: es solo lectura total.
- Compartir o publicar el HTML (contiene datos personales): sería una decisión
  explícita futura.
- Récords personales y detección de PRs (ya fuera de alcance en la 001).
- Filtros, búsqueda y navegación más allá del `<select>` del gráfico.
- Exportar a PDF como función propia (solo el CSS `@media print`).
- Multiusuario.
- WOD, calorías, audios y datos de Garmin (specs 005 y 006) y lenguaje natural (006).
- Botones inline de la spec 003b.
- Consultar RM o historial desde el bot (el historial de RM se consulta aquí, no en
  Telegram; /rms sigue mostrando solo los vigentes).

## Supuestos
- **Decisión registrada:** el HTML contiene datos personales (peso, altura, RM y
  series) y vive en `data/dashboard.html`, dentro de `data/` que ya está en
  `.gitignore` (lo verifica `test_gitignore_cubre_env_y_data`): nunca se sube a git;
  compartirlo sería una decisión explícita futura.
- La base no cambia de esquema: el dashboard lee la versión 2 existente; no hay
  migración desde este comando (los mensajes de versión lo dejan claro).
- Horas: todas las marcas se convierten de UTC a local con `to_local` (RFC de la
  002); "hoy", "ayer" y el mes en curso se calculan en hora local.
- Arquitectura: cálculos puros en `core.py` (sin `sqlite3`), consultas en `db.py`
  (funciones `read_*` de solo lectura, sin commits) y CLI + plantilla en
  `boxlog/dashboard.py`. La constitución no se cambia; `AGENTS.md` se actualizará al
  cierre (estructura del paquete y comando nuevo).
- Espec única con tareas por capas (decisión de alcance): una sola plantilla y una
  sola máquina de gráficos; dividir en 004/004b obligaría a tocar el mismo archivo
  dos veces con decisiones de escapado y formato paralelas.
- Reutiliza sin inventar formatos: `to_local`, `normalize_exercise`, `format_kg`,
  `format_duration`, `round_half_kg`, `group_series_by_exercise`,
  `exercise_stat_line`, `build_summary` (vía `plan_real_pairs`) y los textos de
  estado vacío de /historial.
- Las consultas de sesiones siguen el mismo patrón que `get_recent_sessions` pero sin
  límite de 5 ni tope de longitud, ordenadas por `started_at` descendente.
- El ensayo manual del usuario al cierre: doble clic en `data/dashboard.html`
  (vacío y con datos) y "Guardar como PDF" desde el navegador; en CI no se abre
  ningún navegador.
- README y AGENTS.md se ajustarán al cierre de la 004 (en tasks.md), como en la 003.

## Tests de la 001/002/003 que cambiarán al implementar
- Se esperan **ninguno**: la 004 añade módulos, helpers y consultas nuevas sin tocar
  comportamiento existente. Estos son los tests que harán de guardia ante la
  extracción de `plan_real_pairs` de `build_summary` — si alguno cambia de texto, la
  extracción rompió /fin y hay que corregirla, no el test:
  - `tests/test_core.py::test_build_summary_pares_plan_real_solo_series_con_plan`
    (los pares exactos "plan→real: 84→82, 96→96" y una sola línea).
  - `tests/test_core.py::test_build_summary_duración_volumen_real_y_total` (línea de
    volumen total al final del resumen).
  - `tests/test_commands.py::test_fin_resumen_duracion_y_volumen_real` (pares y
    volumen total de /fin).
  - `tests/test_commands.py::test_fin_par_de_rango_desde_la_serie` (par con rango
    "80-85→82").
  - `tests/test_commands.py::test_fin_resumen_mas_de_una_hora` (sin series
    planificadas → sin línea de pares).
  - `tests/test_db.py::test_flujo_real_tras_migrar` (base migrada de v1 → par en
    formato simple).
  - `tests/test_e2e.py::test_ciclo_completo_punta_a_punta`,
    `test_ciclo_con_rango_reps_y_hora_local_punta_a_punta` y
    `test_mensaje_suelto_historial_y_cierre_punta_a_punta` (textos de /fin completos
    en el camino punta a punta).
- Condición de diseño, sin cambio: `tests/test_core.py::test_core_no_importa_telegram_ni_sqlite`
  exige que `core.py` no importe `sqlite3`, así que las funciones de racha y
  agregados reciben filas ya leídas (dicts), nunca una conexión.
- `tests/test_bot.py::test_gitignore_cubre_env_y_data` ya garantiza que `data/` (y
  por tanto `data/dashboard.html`) está ignorado por git; sigue en verde sin cambios.

## Criterios de finalización
- Tests primero: se escriben antes que el código y no se avanza con `python -m pytest`
  en rojo; la suite completa queda en verde antes de cada commit.
- Racha y agregados: tests puros parametrizados sin reloj (base vacía, una sesión,
  racha con hueco, hoy sin entrenar y ayer sí, marca UTC en otro día local, dos
  sesiones el mismo día, sesión abierta olvidada).
- Solo lectura: hash de la base antes/después de generar, `INSERT` que falla en la
  conexión del dashboard y los cuatro mensajes de versión (0, 1, 2, otro) probados.
- HTML generado en `tmp_path`: el JSON incrustado se extrae con `json.loads` y se
  compara con el payload esperado; los SVG presentes con 0, 1 y 2 puntos; nombre
  hostil escapado en las dos capas; ausencia de token, de `http` externo y de
  `<script src=`; `@media print` presente; textos en español y kilos con coma
  decimal.
- /fin intacto: todas las guardias de la sección anterior en verde.
- Verificación final: sin token ni datos personales en el diff (el HTML de los tests
  vive en `tmp_path`, nunca en `data/`); `requirements.txt` y el esquema de la base
  sin cambios; MEMORY.md actualizado; README y AGENTS.md actualizados.
- Ensayo manual del usuario: doble clic en `data/dashboard.html` con datos reales,
  racha y secciones completas, cambio de ejercicio en el selector y "Guardar como
  PDF" con el selector oculto.
