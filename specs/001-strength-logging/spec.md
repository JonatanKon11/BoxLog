# Spec 001 — v0.1 Fuerza (BoxLog)

## Contexto y objetivo
BoxLog es un bot de Telegram personal para registrar sesiones de fuerza de crossfit. Esta especificación define la primera versión: perfil del usuario, RM por ejercicio con historial, sesiones con apertura y cierre, conversión de porcentajes del RM a kilos y registro de series. Objetivo: que cada sesión quede guardada con su plan y su ejecución real, y que cerrar la sesión produzca un resumen útil.

## Usuarios
- U1: propietario único, identificado por su Telegram ID. Es el único que recibe respuesta del bot.
- (No hay más usuarios en esta versión; compartir el bot queda fuera de alcance.)

## Historias de usuario
- HU-1: Como usuario, quiero registrar mi peso y mi altura para tener mi perfil guardado.
- HU-2: Como usuario, quiero guardar el RM de cada ejercicio conservando el historial, para no perder mi evolución (verla queda fuera de esta versión).
- HU-3: Como usuario, quiero abrir la sesión con /inicio y cerrarla con /fin, para medir la duración del entreno.
- HU-4: Como usuario, quiero pasar porcentajes de mi RM con /hoy, para saber qué kilos levantar hoy.
- HU-5: Como usuario, quiero registrar cada serie con un solo mensaje (/log clean 84x5), para no salir del entreno.
- HU-6: Como usuario, quiero un resumen al cerrar la sesión, para ver volumen, series y desviación del plan.
- HU-7: Como usuario, quiero que el bot solo me responda a mí, para que nadie más toque mis datos.
- HU-8: Como usuario, quiero deshacer la última serie con /deshacer, para corregir un error rápido durante el entreno.

## Requisitos funcionales
- RF-01 Perfil: Cuando el usuario envía `/perfil <peso> <altura>` (peso en kg y altura en cm; p. ej. /perfil 78 175), el sistema deberá registrar o actualizar su peso y su altura.
  - CA: confirmará los valores en español con coma decimal (22,5).
  - CA: el peso deberá estar entre 30 y 300 kg y la altura entre 100 y 250 cm; fuera de ese rango, el sistema responderá un aviso de uso con un ejemplo y no guardará nada.
  - CA: el comando funcionará con sesión abierta o cerrada.
- RF-02 RM con historial: Cuando el usuario envía `/rm <ejercicio> <kg>`, el sistema deberá guardarlo como RM vigente de ese ejercicio conservando los valores anteriores.
  - CA: cada valor quedará asociado a su fecha; el RM vigente será el más reciente.
  - CA: cuando el usuario envía `/rms`, el sistema deberá responder la lista de RM vigentes.
  - CA: ambos comandos funcionarán con sesión abierta o cerrada.
- RF-03 Inicio de sesión: Cuando el usuario envía /inicio, el sistema deberá abrir una sesión con marca de tiempo.
  - CA: si ya hay una sesión abierta, el sistema deberá responder un aviso indicando desde cuándo está abierta y sugiriendo /fin, sin cambiar nada.
  - CA: una sesión olvidada se deja abierta indefinidamente; solo el aviso de /inicio la da por conocida.
- RF-04 Cierre de sesión: Cuando el usuario envía /fin con sesión abierta, el sistema deberá cerrarla y responder un resumen con: duración (de /inicio a /fin), y por cada ejercicio el número de series, las repeticiones totales, el volumen (suma de kilos por repeticiones), el peso máximo usado y, solo cuando hubo peso planificado, la desviación entre planificado y real (p. ej. "plan 84 / real 82").
  - CA: las series sin planificado no contarán para la desviación.
  - CA: el resumen terminará con el volumen total de la sesión.
  - CA: si no hay series, el resumen lo indicará en una línea.
  - CA: si no hay sesión abierta, el sistema deberá responder "No hay sesión abierta, envía /inicio" sin cambiar nada.
- RF-05 Conversión de RM: Cuando el usuario envía `/hoy <ejercicio> <porcentajes...>` (p. ej. /hoy clean 70 80 85), el sistema deberá responder los kilos equivalentes de cada porcentaje con el RM vigente de ese ejercicio.
  - CA: el resultado será el plan de la sesión para ese ejercicio.
  - CA: si no hay sesión abierta, responderá el aviso de RF-04 sin cambiar nada.
  - CA: si el ejercicio no tiene RM, responderá el aviso "No tengo RM de <ejercicio>, cárgalo con /rm" sin cambiar nada.
  - CA: si el usuario repite /hoy para el mismo ejercicio en la misma sesión, el plan anterior se reemplaza y el orden de los valores se reinicia.
- RF-06 Registro de serie: Cuando el usuario envía `/log <ejercicio> <peso>x<repeticiones>` (p. ej. /log clean 84x5), el sistema deberá guardar la serie dentro de la sesión actual.
  - CA: el peso del mensaje es el peso real; el peso planificado se tomará, en orden, del siguiente valor no consumido del plan de /hoy para ese ejercicio.
  - CA: si el ejercicio no tiene plan o el plan se agotó, la serie se guardará con el planificado vacío; el sistema no rechazará nunca un /log por falta de plan.
  - CA: si no hay sesión abierta, responderá el aviso de RF-04 sin guardar nada.
- RF-07 Deshacer: Cuando el usuario envía /deshacer con sesión abierta, el sistema deberá borrar la última serie registrada en esa sesión.
  - CA: si la sesión no tiene series, responderá un aviso indicándolo y no hará nada.
  - CA: si no hay sesión abierta, responderá el aviso de RF-04 sin cambiar nada.
  - CA: solo se borra la última serie; editar o borrar otras series queda fuera de alcance.
- RF-08 Usuario único: El sistema deberá ignorar los mensajes de cualquier ID distinto del propietario, sin responder ni guardar datos.
- RF-09 Formato inválido: Si el usuario envía un comando con formato inválido (falta de repeticiones, números cero o negativos, /hoy sin porcentajes), el sistema deberá responder un aviso de uso con un ejemplo y no guardará ni cambiará nada.
  - CA: el aviso indicará la sintaxis correcta con un ejemplo real (p. ej. "Usa /log clean 84x5").
- RF-10 Entrada numérica: El sistema deberá aceptar decimales con coma y con punto (84,5 y 84.5) en todos los comandos numéricos.

## Requisitos no funcionales
- RNF-1 Idioma: todos los mensajes al usuario estarán en español; los kilos se mostrarán con coma decimal (22,5).
- RNF-2 Protección: el token y los datos personales (peso, altura, RM, entrenamientos) no aparecerán en el repositorio ni en logs.
- RNF-3 Durabilidad: los entrenamientos guardados no se perderán ante ningún cambio de la versión.
- RNF-4 Claridad: cada rechazo o aviso indicará qué hacer a continuación (p. ej. "envía /inicio").

## Casos límite
- CL-1 /inicio con sesión ya abierta (incluida una olvidada): aviso con fecha/hora de apertura y sugerencia de /fin; sin cambios. La sesión olvidada se deja abierta (RF-03).
- CL-2 /fin, /hoy, /log o /deshacer sin sesión abierta → aviso "No hay sesión abierta, envía /inicio"; sin cambios.
- CL-3 /log de un ejercicio sin plan o con el plan agotado → serie guardada con planificado vacío, sin error.
- CL-4 Si /hoy devuelve más valores de los que se registran series para ese ejercicio, los valores no usados quedan sin efecto, sin error ni aviso.
- CL-5 Sesión cerrada sin series → /fin responde una única línea indicándolo.
- CL-6 /perfil, /rm y /rms → funcionan siempre, con sesión abierta o no.
- CL-7 Cualquier mensaje de un ID no propietario → ignorado por completo.
- CL-8 Comando con formato inválido (sin repeticiones, números cero o negativos, /hoy sin porcentajes) → aviso de uso con ejemplo; no se guarda nada (RF-09).
- CL-9 /deshacer en una sesión sin series → aviso indicándolo; no hace nada.
- CL-10 /hoy de un ejercicio sin RM → aviso "No tengo RM de <ejercicio>, cárgalo con /rm"; sin cambios.

## Fuera de alcance
- WOD (tipo, cap, tiempo real), calorías/METs, audios y datos de Garmin.
- Detección de récords y cualquier análisis posterior.
- Múltiples usuarios, tabla de usuarios, compartir el bot.
- Lenguaje natural: todos los comandos usan formato fijo.
- Ver el historial de RM (se guarda; consultar /rms solo muestra los vigentes).
- Editar o borrar series distintas de la última (solo existe /deshacer).

## Criterios de finalización
- Todos los RF y CL cubiertos con pruebas automatizadas en verde antes de cada commit.
- Verificación final: sin token ni datos personales en el diff.
- Mensajes de usuario en español con kilos en coma decimal.
- MEMORY.md actualizado con el estado y los aprendizajes de la implementación.
