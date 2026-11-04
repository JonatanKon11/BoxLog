# Spec 003 — UX del bot: menú, mensaje suelto, /historial y aviso de error (BoxLog v0.3)

## Contexto y objetivo
BoxLog registra sesiones de fuerza con plan porcentual y series reales (v0.2). Esta
especificación reduce la fricción en el box: que el bot se use sin escribir comandos de
memoria y con menos tipeo con las manos sudadas. Cuatro mejoras de interfaz, sin tocar el
modelo de datos: menú de comandos de Telegram, registro directo desde un mensaje suelto
("52x3"), consulta de las últimas sesiones con /historial y un aviso corto cuando falla
algo interno. La mecánica de entrenamiento (plan, series, deshacer, cierre) no cambia.

## Alcance
Menú de comandos con descripciones (RF-01), mensaje suelto con forma de registro
(RF-02), /historial de solo lectura (RF-03) y aviso de error interno en el chat (RF-04).
No se cambia el esquema de la base (sin migración) ni la mecánica de /log, /deshacer,
/hoy y /fin. Los botones inline quedan fuera, en la spec 003b posterior.

## Requisitos funcionales
- RF-01 Menú de comandos: El sistema deberá publicar en el menú de comandos de Telegram
  (la lista que aparece al escribir "/" y en el botón de comandos) todos los comandos,
  con descripciones cortas en español.
  - CA: los comandos del menú son exactamente: perfil, rm, rms, inicio, hoy, log,
    deshacer, historial, fin y ayuda; /start sigue aliasando a /ayuda sin entrada propia.
  - CA: cada descripción tendrá 25 caracteres o menos (el límite de Telegram), en
    español, sin kilos, horas ni datos personales.
  - CA: el menú y la lista de /ayuda saldrán de una única constante compartida (una sola
    fuente de verdad); un test de sincronía comprobará que ambos listan los mismos
    comandos, que /historial está incluido y que las descripciones no superan 25
    caracteres.
  - CA: el menú se publica al arrancar el bot; /ayuda sigue respondiendo la lista
    completa como hasta ahora, ahora con /historial incluido.
  - CA: los comandos desconocidos siguen respondiendo la lista de comandos (RF-12 de la
    spec 001).
- RF-02 Mensaje suelto: Cuando el usuario envía un mensaje sin comando que consta de un
  **único token** con forma de `<peso>x<repeticiones>`, el sistema deberá registrarlo
  como una serie, usando el ejercicio de la última serie de la sesión abierta.
  - CA: la forma es número (coma o punto decimal, RF-10 de la 001) seguido de "x" o "X"
    y un entero de repeticiones. [Corregido en T2: la validación es exactamente la de
    /log de la 001 (peso y reps > 0, reps enteras, sin notación científica ni nan/inf);
    /log no tiene techo de kilos, por eso "600x3" se registra]
  - CA: el ejercicio es el de la **última serie registrada en la sesión abierta** (la
    misma que borraría /deshacer, RF-07 de la 001); tras un /deshacer, el siguiente
    mensaje suelto usa la serie que quedó como última.
  - CA: la confirmación, la copia del plan a la serie y el consumo del plan son
    idénticos a /log (RF-06 de la 001, RF-04 y RF-05 de la 002): misma línea
    "clean · serie N: 52 kg × 3 (plan …)" y mismo sufijo con × y con rango.
  - CA: un token con forma de `<peso>x<repeticiones>` pero inválido ("52x0", "52x",
    "1e3x5") → aviso de uso de RF-09 con el motivo y un ejemplo, sin guardar
    nada. **(RF-09 modificado por esta spec)**
    [Ajuste de T2: "x3" (sin peso) y "-5x3" (peso negativo) también dan aviso de uso,
    por simetría con "52x": /log los rechaza igual con su aviso.]
  - CA: cualquier otro texto libre (con espacios, con caracteres de más o sin forma de
    registro) y los comandos desconocidos → la lista de comandos (RF-12 de la 001), sin
    guardar nada. **(RF-12 modificado por esta spec)**
  - CA: sin sesión abierta → el aviso "No hay sesión abierta, envía /inicio" (CL-2 de la
    001), sin guardar nada.
  - CA: sesión abierta sin series → no se adivina el ejercicio por el plan de /hoy; el
    aviso será "Aún no hay series en esta sesión. Registra una con /log <ejercicio>
    <peso>x<reps>", sin guardar nada.
  - CA: los mensajes de un ID distinto del dueño se ignoran por completo, igual que todo
    (RF-08 y CL-7 de la 001).
- RF-03 /historial: Cuando el usuario envía /historial, el sistema deberá responder las
  últimas sesiones registradas, en modo solo lectura y sin cambiar nada.
  - CA: la respuesta incluye la sesión abierta (si la hay), la primera y marcada como
    "abierta", seguida de las últimas 5 cerradas, de más reciente a más antigua.
  - CA: cada sesión se muestra con una línea de cabecera y una línea por ejercicio:
    cabecera de cerrada "13/10 · 1 h 11 min" (fecha local de apertura y duración con el
    mismo formato que /fin, RF-04 de la 001); cabecera de la abierta
    "19/10 · abierta desde las 20:35" (fecha de apertura y hora de apertura en local,
    RF-03 de la 001); línea de ejercicio "clean: 2 series · 8 repeticiones ·
    volumen 708 kg · máx 96 kg" (el mismo formato por ejercicio del resumen de /fin).
  - CA: no se muestran pares plan→real ni la hora de cada serie: /historial es un resumen
    de lectura rápida; el detalle de la sesión actual lo da /fin.
  - CA: las fechas, horas y duraciones se muestran en hora local (UTC-3, RF-02 de la
    002); la duración de la sesión abierta se calcula contra la hora actual.
  - CA: el mensaje nunca superará 3800 caracteres: si no cabe, se muestran menos
    sesiones, descartando primero las más antiguas; nunca se parte en dos mensajes y
    siempre se muestra al menos la sesión más reciente.
  - CA: funciona con sesión abierta o cerrada, como /rms y /perfil (CL-6 de la 001); no
    recibe argumentos (con argumentos → aviso de uso de RF-09).
  - CA: sin ninguna sesión registrada → mensaje claro: "Aún no hay sesiones. Abre la
    primera con /inicio".
- RF-04 Aviso de error interno: Si un comando produce un error interno (no de red), el
  sistema deberá enviar al dueño, en el chat, un aviso corto y genérico.
  - CA: el texto del chat será fijo: "⚠️ Algo salió mal; no se ha perdido nada.
    Inténtalo de nuevo."
  - CA: el chat nunca recibe el texto del error ni su traceback (podrían contener datos
    o el token, RNF-2).
  - CA: el detalle completo del error sigue yendo al log con `format_error_log` (token
    redactado), como hasta ahora.
  - CA: NetworkError y TimedOut no envían nada al chat: solo se loguean, como hasta
    ahora, porque la librería reintenta sola y un aviso con la red caída también
    fallaría.
  - CA: el aviso solo puede llegar al dueño: los mensajes de otros IDs se ignoran antes
    de llegar a los comandos (RF-08).

## Requisitos no funcionales
- RNF-1 Idioma: mensajes en español, kilos con coma decimal (22,5) y horas legibles en
  hora local (hereda el RNF-1 de la 001 y el RF-02 de la 002).
- RNF-2 Protección: ni el chat ni el menú muestran el token, trazas de error ni datos
  personales; el detalle del error solo al log con el token redactado.
- RNF-3 Sin dependencias ni migraciones: el menú, el mensaje suelto, /historial y el
  aviso de error se implementan solo con la stdlib y con python-telegram-bot ya
  instalado; `requirements.txt` no cambia y el esquema de la base tampoco.
- RNF-4 Claridad: cada aviso indica qué hacer a continuación (hereda el RNF-4 de la
  001).
- RNF-5 Dueño único: todo lo nuevo respeta RF-08, incluido el aviso de error, que solo
  puede llegar al dueño.

## Casos límite
- CL-1 Mensaje con espacios ("mañana hago 52x3") o con varios tokens → no es un único
  token; responde la lista de comandos (RF-12 de la 001) y no guarda nada.
- CL-2 Caracteres extra ("52x3?", "52x3.") → sin forma exacta de
  `<peso>x<repeticiones>`; lista de comandos, sin guardar nada.
- CL-3 Coma decimal y mayúscula ("52,5X3") → se registra igual que /log (RF-10 de la
  001, mayúscula/minúscula): "clean · serie N: 52,5 kg × 3 (plan …)".
- CL-4 Forma de registro pero inválida ("52x0", "52x", "x3", "-5x3", "5x2,5", "1e3x5")
  → aviso de uso con el motivo y un ejemplo (RF-09); no se guarda nada. ("600x3" no es
  inválido: /log no tiene techo de kilos, se registra — RF-02 corregido en T2.)
- CL-5 Mensaje suelto válido sin sesión abierta → "No hay sesión abierta, envía /inicio"
  (CL-2 de la 001); no se guarda nada.
- CL-6 Sesión abierta sin series (con o sin plan de /hoy) → "Aún no hay series en esta
  sesión. Registra una con /log <ejercicio> <peso>x<reps>"; no se guarda nada: no se
  adivina el ejercicio.
- CL-7 Tras un /deshacer → el mensaje suelto usa la serie que quedó como última (su
  ejercicio); si el /deshacer dejó la sesión sin series, aplica CL-6.
- CL-8 Mensaje de un ID que no es el dueño (incluido "52x3") → ignorado por completo,
  sin respuesta ni guardado (RF-08, CL-7 de la 001).
- CL-9 /historial sin ninguna sesión → "Aún no hay sesiones. Abre la primera con
  /inicio"; funciona igual con sesión abierta o cerrada (CL-6 de la 001).
- CL-10 /historial con sesión abierta → la lista empieza por la sesión abierta, marcada
  "abierta", con su duración calculada hasta el momento.
- CL-11 /historial muy largo → el mensaje se limita a 3800 caracteres mostrando menos
    sesiones (se descartan primero las más antiguas); nunca se parte en dos mensajes y
    siempre cabe al menos la sesión más reciente.
- CL-12 /historial con argumentos → aviso de uso (RF-09); no cambia nada.
- CL-13 Error interno de un comando → aviso genérico en el chat y detalle completo solo
  en el log; un NetworkError o TimedOut no avisa en el chat (RF-04).
- CL-14 Sesión con varios ejercicios → /historial muestra una línea por ejercicio, en el
  orden de su primera serie, igual que el resumen de /fin (RF-04 de la 001).
- CL-15 /ayuda y el menú incluyen /historial con la misma descripción (constante única,
  RF-01).

## Fuera de alcance
- Botones inline: spec **003b** posterior. Se prevén dos: "↩️ Deshacer" en la
  confirmación de /log (con el id de la serie, para que un botón viejo no borre la serie
  equivocada de otra sesión) y "📋 Ver plan" tras /inicio. Queda decidido que **no** habrá
  botón de cerrar sesión: un cierre accidental rompería la duración y un botón de otra
  sesión sería peligroso; /fin se escribe en dos segundos.
- Lenguaje natural: el mensaje suelto sigue siendo formato fijo "pesoxreps"; no se
  interpretan frases ni palabras.
- Dashboard, WOD, calorías, audios y datos de Garmin (specs futuras).
- Historial de RM (se guarda sin consultarse; /rms solo muestra los vigentes).
- Borrar o editar series de sesiones cerradas; /historial es solo lectura.
- Partir mensajes en varios ni paginación (quedará para 003b si hace falta).
- Tope de peso o repeticiones en /log (que el mensaje suelto heredaría): idea futura,
  **no implementado**; hoy /log no tiene techo de kilos (RF-06 de la 001, RF-02
  corregido en T2).

## Supuestos
- La base no cambia de esquema: /historial se calcula con consultas sobre `sessions` y
  `series` existentes; no hay migración.
- El "último ejercicio" del mensaje suelto es el de la última serie de la sesión
  abierta, no la última serie del historial; con la sesión recién abierta no hay
  ejercicio (CL-6).
- Los formatos de /historial reutilizan los de /fin (RF-04 de la 001) y los helpers de
  hora de la 002 para no inventar presentaciones nuevas.
- El tope de 3800 caracteres es holgado bajo el máximo de 4096 de Telegram.
- El menú se publica al arrancar (set_my_commands); si Telegram lo olvidara, vuelve al
  siguiente arranque; no hay persistencia propia.
- El README (roadmap) se ajustará al cierre de la 003: v0.3 pasa a ser esta spec y
  WOD/calorías quedan recorridos.
- Esta spec no necesita notación de revisión (A-x): las seis preguntas abiertas del
  análisis se resolvieron con el usuario antes de escribirla y quedan reflejadas en los
  RF/CL y en estos supuestos.

## Tests de la 001 que cambiarán al implementar
- `tests/test_bot.py::test_dispatch_texto_libre_devuelve_la_ayuda` (línea 69): hoy
  afirma que todo texto libre devuelve la ayuda; con RF-12 modificado, `dispatch` deberá
  recibir el texto crudo y el test pasará a cubrir el nuevo comportamiento (único token
  "52x3" → confirmación de serie; "52x0" → aviso de uso; "mañana hago 52x3" → ayuda).
- `tests/test_bot.py::test_dispatch_persona_ajena_comando_desconocido_tampoco` (línea
  61): usa la misma vía de texto libre (`dispatch(..., None, ...)`) y solo cambiará su
  llamada para adaptarse a la firma nueva; la aserción (ajeno → silencio, RF-08) no
  cambia.
- `tests/test_core.py::test_help_text_lista_todos_los_comandos_v01` (línea 818): /ayuda
  ganará /historial y saldrá de la constante única del menú (RF-01).
- No cambian: los tests de comando desconocido → ayuda (`test_dispatch_comando_desconocido_devuelve_la_ayuda`),
  los de /start y /ayuda (comparan contra `help_text()` dinámico), ni ninguno de
  commands, db, e2e ni el ciclo completo de la 001: los textos de confirmación y los
  avisos de la 001/002 se conservan tal cual.

## Criterios de finalización
- Tests primero: se escriben antes que el código y no se avanza con `python -m pytest` en
  rojo; la suite completa queda en verde antes de cada commit.
- Test de sincronía del menú: la constante única lista los diez comandos, /ayuda los
  refleja y ninguna descripción supera 25 caracteres.
- E2E del mensaje suelto: con la sesión abierta y series previas, "52,5X3" registra con
  la misma confirmación y plan que /log; "52x0" da el aviso de uso; "mañana hago 52x3"
  da la ayuda; sin series, el aviso de CL-6.
- /historial probado vacío, con sesión abierta y cerradas, y con el tope de longitud.
- Error interno: el chat recibe el aviso genérico sin `str(error)` y la red sigue solo
  en el log.
- Verificación final: sin token ni datos personales en el diff; `requirements.txt` y el
  esquema de la base sin cambios; MEMORY.md actualizado.
