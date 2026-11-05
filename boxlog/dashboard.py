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
            db.read_sessions(connection), now, core.to_local(now).date()
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
    sesiones = "".join(_render_sesion(sesion) for sesion in payload["sessions"])
    historial = (
        f'<ul class="sesiones">{sesiones}</ul>'
        if sesiones
        else f"<p>{_esc(core.HISTORIAL_EMPTY)}</p>"
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
.sesiones {{ list-style: none; padding: 0; }}
.sesiones li {{ padding: 0.25rem 0; border-bottom: 1px solid #2a2d33; }}
@media print {{ body {{ background: #fff; color: #000; }}
               .controles {{ display: none; }} }}
</style></head>
<body><main>
<header>
<h1>BoxLog</h1>
<p class="generado">Generado el {_esc(payload["generated"])}</p>
<p class="racha">🔥 {streak["days"]}</p>
<p>Sesiones del mes: {payload["month_sessions"]}</p>
</header>
<section id="rm"><h2>RM</h2><p>{_esc(core.DASH_NO_RM)}</p></section>
<section id="historial"><h2>Historial</h2>{historial}</section>
<section id="carga"><h2>Carga máxima</h2><p>{_esc(core.HISTORIAL_EMPTY)}</p></section>
</main>
<script id="datos" type="application/json">{_json_seguro(payload)}</script>
<script>JSON.parse(document.getElementById("datos").textContent);</script>
</body></html>
"""


def _render_sesion(sesion: dict) -> str:
    """Una línea por sesión: fecha y duración, o la marca de abierta (CL-3)."""
    if sesion["open"]:
        detalle = f"abierta desde las {_esc(sesion['opened_at'])}"
    else:
        detalle = _esc(sesion["duration"])
    return f"<li>{_esc(sesion['date'])} · {detalle}</li>"


if __name__ == "__main__":
    raise SystemExit(main())
