"""Generador del dashboard local en solo lectura (spec 004, RF-01).

Solo orquesta: db lee la base, core calcula y aquí se arma el HTML. No
importa el bot ni la librería de mensajería ni lee variables de entorno
(RNF-2): el módulo funciona igual con o sin token presente.
"""

import html
import json
import os
import sqlite3
from pathlib import Path

from boxlog import core, db

# Mismas rutas relativas al cwd que el comando del bot (plan §4).
DB_PATH = Path("data") / "boxlog.db"
OUTPUT_PATH = Path("data") / "dashboard.html"


def main(argv=None) -> int:
    """0 = generado; 1 = mensaje fijo en consola con el HTML intacto (RF-01)."""
    try:
        lectura = db.with_lock_retry(_leer_payload)
    except sqlite3.OperationalError as error:
        if "unable to open database file" in str(error).lower():
            print(core.DASH_DB_MISSING)
            return 1
        raise  # cualquier otro fallo: traceback del desarrollador (plan §4)
    if isinstance(lectura, str):  # mensaje fijo: versión o base ocupada
        print(lectura)
        return 1
    payload = lectura
    documento = render_dashboard(payload)
    _escribir_atomico(OUTPUT_PATH, documento)
    print(
        core.DASH_GENERATED.format(
            ruta=OUTPUT_PATH.as_posix(), n=len(payload["sessions"])
        )
    )
    return 0


def _leer_payload():
    """Payload de la base, o el mensaje fijo que corta, como str (RF-01).

    main lo envuelve en db.with_lock_retry (CL-11): ante una base ocupada el
    error de bloqueo se reintenta aquí y, agotados los intentos,
    with_lock_retry devuelve DASH_DB_LOCKED como str.
    """
    connection = db.open_readonly(DB_PATH)
    try:
        error = core.dashboard_version_error(db.read_user_version(connection))
        if error:
            return error
        now = core.utc_now()
        return core.build_dashboard_payload(
            db.read_sessions(connection),
            db.read_series(connection),
            db.read_rm_history(connection),
            db.list_rms(connection),
            now,
            core.to_local(now).date(),
        )
    finally:
        connection.close()


def _esc(texto) -> str:
    """Texto visible y atributos escapados con html.escape, comillas incluidas."""
    return html.escape(str(texto), quote=True)


def _json_seguro(payload: dict) -> str:
    """JSON del bloque de datos sin "<" (CL-8): un "</script>" no cierra nada."""
    return json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")


def _escribir_atomico(ruta: Path, contenido: str) -> None:
    """Escritura completa y atómica (CL-16): archivo temporal y reemplazo."""
    temporal = ruta.with_name(ruta.name + ".tmp")
    try:
        temporal.write_text(contenido, encoding="utf-8")
        os.replace(temporal, ruta)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise


def render_dashboard(payload: dict) -> str:
    """HTML completo del dashboard a partir del payload (RF-06, plan §6).

    Función pura: entra el dict, sale el documento. Todo texto dinámico pasa
    por _esc y el JSON incrustado por _json_seguro: las dos capas de CL-8.
    """
    streak = payload["streak"]
    aviso = ""
    if streak["missing_today"]:
        aviso = f'<p class="aviso">{_esc(core.DASH_STREAK_ALIVE)}</p>'
    elif streak["days"] == 0 and streak["last"] is not None:
        ultimo = core.DASH_LAST_SESSION.format(ultimo=streak["last"])
        aviso = f'<p class="aviso">{_esc(ultimo)}</p>'
    sesiones = "".join(_render_sesion(sesion) for sesion in payload["sessions"])
    historial = (
        sesiones if sesiones else f"<p>{_esc(core.HISTORIAL_EMPTY)}</p>"
    )
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BoxLog — dashboard</title>
<style>
body {{ margin: 0; font-family: system-ui, sans-serif; background: #101216;
       color: #e8e8e8; line-height: 1.5; }}
main {{ max-width: 40rem; margin: 0 auto; padding: 1rem; }}
h1 {{ margin-bottom: 0.25rem; }}
.generado {{ color: #9aa0a6; margin-top: 0; }}
.racha {{ font-size: 3rem; margin: 0.5rem 0; }}
section {{ margin-top: 1.5rem; }}
.aviso {{ color: #e0b354; margin: 0.25rem 0; }}
.tarjetas {{ display: flex; flex-wrap: wrap; gap: 0.75rem; }}
.tarjeta {{ border: 1px solid #2a2d33; border-radius: 6px; padding: 0.5rem 0.75rem; }}
.tarjeta h3 {{ margin: 0; font-size: 1rem; }}
.tarjeta .kg {{ margin: 0.25rem 0 0; font-size: 1.5rem; font-weight: 600; }}
figure {{ margin: 1rem 0; }}
figcaption {{ color: #9aa0a6; font-size: 0.9rem; }}
#rm svg {{ width: 100%; height: auto; }}
#rm svg text {{ fill: #9aa0a6; font-size: 0.75rem; }}
.porcentajes {{ border-collapse: collapse; margin-top: 0.75rem; width: 100%; }}
.porcentajes th, .porcentajes td {{ border: 1px solid #2a2d33;
               padding: 0.25rem 0.5rem; text-align: right; }}
.porcentajes thead th {{ text-align: center; }}
#carga svg {{ width: 100%; height: auto; }}
#carga svg text {{ fill: #9aa0a6; font-size: 0.75rem; }}
.controles {{ display: block; width: 100%; max-width: 22rem; padding: 0.4rem;
              margin: 0.5rem 0; font: inherit; color: #e8e8e8; background: #171a1f;
              border: 1px solid #2a2d33; border-radius: 6px; }}
[hidden] {{ display: none; }}
article {{ border-bottom: 1px solid #2a2d33; padding-bottom: 0.75rem;
          margin-bottom: 0.75rem; }}
article h3 {{ margin: 0 0 0.25rem; font-size: 1.1rem; }}
article ul {{ list-style: none; margin: 0.25rem 0; padding: 0; }}
article p {{ margin: 0.25rem 0; }}
@media print {{ body {{ background: #fff; color: #000; }}
               .controles {{ display: none; }}
               article {{ break-inside: avoid; }}
               #carga svg {{ break-inside: avoid; }} }}
</style></head>
<body><main>
<header>
<h1>BoxLog</h1>
<p class="generado">Generado el {_esc(payload["generated"])}</p>
<p class="racha">🔥 {streak["days"]}</p>
{aviso}
<p>Sesiones del mes: {payload["month_sessions"]}</p>
</header>
<section id="rm"><h2>RM</h2>{_render_rm(payload)}</section>
<section id="historial"><h2>Historial</h2>{historial}</section>
<section id="carga"><h2>Carga máxima</h2>{_render_carga(payload)}</section>
</main>
<script id="datos" type="application/json">{_json_seguro(payload)}</script>
<script>
JSON.parse(document.getElementById("datos").textContent);
const grupos = document.querySelectorAll("#carga g[data-exercise]");
const selector = document.getElementById("selector-carga");
if (selector) {{
  selector.addEventListener("change", function () {{
    for (const grupo of grupos) {{
      grupo.toggleAttribute(
        "hidden", grupo.getAttribute("data-exercise") !== selector.value
      );
    }}
  }});
}}
</script>
</body></html>
"""


def _render_sesion(sesion: dict) -> str:
    """<article> de una sesión (RF-04): cabecera local, volumen, líneas y pares.

    La cabecera es "DD/MM · duración" o "DD/MM · abierta desde las HH:MM"
    (CL-3, la abierta sin duración); una sesión sin series se queda solo con
    la cabecera. Cada línea es exactamente la de /fin y la de pares lleva la
    flecha → de la 001; todo el texto pasa por _esc (CL-8).
    """
    if sesion["open"]:
        cabecera = f"{sesion['date']} · abierta desde las {sesion['opened_at']}"
    else:
        cabecera = f"{sesion['date']} · {sesion['duration']}"
    partes = [f"<h3>{_esc(cabecera)}</h3>"]
    if sesion["volume"] is not None:
        partes.append(f"<p>Volumen total: {_esc(sesion['volume'])}</p>")
    if sesion["lines"]:
        lineas = "".join(f"<li>{_esc(linea)}</li>" for linea in sesion["lines"])
        partes.append(f"<ul>{lineas}</ul>")
    if sesion["pairs"]:
        partes.append(f"<p>plan→real: {_esc(', '.join(sesion['pairs']))}</p>")
    return "<article>\n" + "\n".join(partes) + "\n</article>\n"


def _render_rm(payload: dict) -> str:
    """Sección RM (RF-03): sin RM vigente → texto fijo; con RM → tarjetas,
    una evolución SVG por ejercicio y la tabla de porcentajes. Todo el texto
    visible (nombres incluidos) pasa por _esc (CL-8)."""
    rms = payload["rm_current"]
    if not rms:
        return f"<p>{_esc(core.DASH_NO_RM)}</p>"
    tarjetas = "".join(
        f'<div class="tarjeta"><h3>{_esc(rm["exercise"])}</h3>'
        f'<p class="kg">{_esc(core.format_kg(rm["kg"]))} kg</p></div>'
        for rm in rms
    )
    evoluciones = "".join(
        "<figure><figcaption>Evolución de "
        + _esc(evolucion["exercise"])
        + "</figcaption>"
        + _svg_line(
            evolucion["points"], f"Evolución de {evolucion['exercise']}"
        )
        + "</figure>"
        for evolucion in payload["rm_evolution"]
    )
    tabla = _render_tabla_porcentajes(payload["percent_table"])
    return f'<div class="tarjetas">{tarjetas}</div>{evoluciones}{tabla}'


def _render_carga(payload: dict) -> str:
    """Sección #carga (RF-04, RF-06): sin series → estado vacío; con series →
    un <select> por ejercicio y un <g data-exercise> por grupo pre-renderizado,
    el primero visible y el resto con "hidden" (el JS solo alterna esa
    atributo, así que se imprime el gráfico elegido). Todo nombre pasa por
    _esc en value, texto de option, data-exercise y aria-label (CL-8)."""
    carga = payload["max_load"]
    if not carga:
        return f"<p>{_esc(core.HISTORIAL_EMPTY)}</p>"
    opciones = "".join(
        f'<option value="{_esc(ejercicio)}">{_esc(ejercicio)}</option>'
        for ejercicio in carga
    )
    grupos = ""
    for indice, (ejercicio, puntos) in enumerate(carga.items()):
        oculto = "" if indice == 0 else " hidden"
        grupos += (
            f'<g data-exercise="{_esc(ejercicio)}"'
            f' aria-label="Carga máxima de {_esc(ejercicio)}"{oculto}>'
            + _svg_trazo(puntos)
            + "</g>"
        )
    return (
        '<label class="controles" for="selector-carga">Ejercicio</label>'
        '<select class="controles" id="selector-carga">'
        f"{opciones}</select>"
        '<svg viewBox="0 0 640 240" role="img"'
        f' aria-label="Carga máxima por sesión">{grupos}</svg>'
    )


def _render_tabla_porcentajes(tabla: dict) -> str:
    """Tabla 50–100 % (RF-03): una columna por ejercicio y kilos con coma."""
    cabecera = "".join(f"<th>{_esc(ejercicio)}</th>" for ejercicio in tabla["exercises"])
    filas = "".join(
        f"<tr><th>{paso} %</th>"
        + "".join(f"<td>{_esc(core.format_kg(kg))}</td>" for kg in valores)
        + "</tr>"
        for paso, valores in zip(tabla["steps"], tabla["values"])
    )
    return (
        '<table class="porcentajes"><thead><tr><th>%</th>'
        f"{cabecera}</tr></thead><tbody>{filas}</tbody></table>"
    )


def _svg_line(puntos: list, etiqueta: str) -> str:
    """<svg> completo de una evolución (RF-03, R9): 0 puntos → "" (CL-2).

    Envuelve el trazo de _svg_trazo con el aria-label de la etiqueta.
    """
    if not puntos:
        return ""
    return (
        f'<svg viewBox="0 0 640 240" role="img" aria-label="{_esc(etiqueta)}">'
        + _svg_trazo(puntos)
        + "</svg>"
    )


def _svg_trazo(puntos: list) -> str:
    """Trazo del SVG (R9): 0 puntos → ""; 1 → solo <circle> (CL-2, sin línea);
    ≥2 → <polyline> + <circle>s. x por índice (los puntos vienen cronológicos),
    y escalado min..max con margen y banda central cuando max == min, sin
    división por cero. Eje X con las fechas de los extremos y eje Y con los
    kilos (format_kg); etiquetas en español y todo pasado por _esc (CL-8).
    """
    if not puntos:
        return ""
    ancho, alto = 640, 240
    izq, top, der, pie = 56, 16, 16, 40
    kg = [float(valor) for _fecha, valor in puntos]
    minimo, maximo = min(kg), max(kg)
    rango = maximo - minimo
    n = len(puntos)

    def x(indice: float) -> float:
        if n == 1:
            return (izq + ancho - der) / 2
        return izq + indice * (ancho - izq - der) / (n - 1)

    def y(valor: float) -> float:
        if rango == 0:
            return (top + alto - pie) / 2
        return (alto - pie) - (valor - minimo) * (alto - pie - top) / rango

    piezas = [
        f'<line x1="{izq}" y1="{top}" x2="{izq}" y2="{alto - pie}" stroke="#3a3f47"/>',
        f'<line x1="{izq}" y1="{alto - pie}" x2="{ancho - der}" y2="{alto - pie}"'
        ' stroke="#3a3f47"/>',
        f'<text x="6" y="{top + 10}">{_esc(core.format_kg(maximo))} kg</text>',
        f'<text x="6" y="{alto - pie}">{_esc(core.format_kg(minimo))} kg</text>',
        f'<text x="{izq}" y="{alto - 14}">{_esc(puntos[0][0])}</text>',
    ]
    if n >= 2:
        piezas.append(
            f'<text x="{ancho - der}" y="{alto - 14}" text-anchor="end">'
            f"{_esc(puntos[-1][0])}</text>"
        )
        coordenadas = " ".join(
            f"{x(indice):.1f},{y(valor):.1f}" for indice, valor in enumerate(kg)
        )
        piezas.append(
            f'<polyline points="{coordenadas}" fill="none" stroke="#7cb7ff"'
            ' stroke-width="2"/>'
        )
    piezas += [
        f'<circle cx="{x(indice):.1f}" cy="{y(valor):.1f}" r="4" fill="#7cb7ff"/>'
        for indice, valor in enumerate(kg)
    ]
    return "".join(piezas)


if __name__ == "__main__":
    raise SystemExit(main())
