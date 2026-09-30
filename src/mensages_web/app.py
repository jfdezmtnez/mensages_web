"""Aplicación Dash: rejilla AG Grid para editar las tablas de bbdd.sqlite.

Modelo de edición
------------------
La rejilla trabaja en modo cliente (AG Grid Community). Cada cambio de celda lo
recoge un ``clientside_callback`` sobre ``cellValueChanged`` y lo acumula en un
``dcc.Store``; el botón «Guardar» es el único que escribe en la base de datos, y
lo hace dentro de una transacción. Así no hay escrituras parciales y los
errores se muestran antes de tocar nada.

Una sola callback de control
----------------------------
En Dash una propiedad de componente solo puede ser salida de una callback. Por
eso todo (elegir tabla, nueva fila, guardar, descartar, borrar, filtrar) cuelga
de **un único** callback con varias entradas que se distingue con
``ctx.triggered_id``. Si se reparte en varias, las que compartan firma de salida
silenciosamente se pisan entre si y solo queda registrada la última.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from dash import (
    Dash,
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
)
import dash_ag_grid as dag

from . import __version__, db
from .db import NEW_FLAG, PK_FIELD, is_new
from .grid import build_column_defs, build_default_col_def, build_grid_options
from .meta import Table

DB_PATH: Path = db.default_db_path()

app = Dash(
    __name__,
    title=f"MensaGes · editor de {DB_PATH.name}",
    update_title=None,
    suppress_callback_exceptions=True,
)

GRID_ID = "rejilla"
CAMBIOS_ID = "cambios"


# --------------------------------------------------------------------------- #
# Utilidades de rejilla
# --------------------------------------------------------------------------- #


def overlay(rows: list[dict], cambios: list[dict] | None) -> list[dict]:
    """Superpone los cambios pendientes sobre lo que hay en la base de datos.

    Las filas ya existentes conservan su posicion (editar una celda no debe
    moverla al final) y las filas nuevas se anaden al final. Asi, cualquier
    operacion que recarga la rejilla muestra el estado real, no una copia
    desactualizada.
    """
    if not cambios:
        return rows
    pendientes = {str(c.get(PK_FIELD)): c for c in cambios}
    resultado: list[dict] = []
    for row in rows:
        resultado.append(pendientes.pop(str(row.get(PK_FIELD)), row))
    resultado.extend(pendientes.values())
    return resultado


def _order(rows: list[dict], table: Table) -> list[dict]:
    """Ordena por clave primaria, que es como se insertan las filas nuevas."""
    names = [c.name for c in table.pk_columns]

    def key(row: dict):
        if is_new(str(row.get(PK_FIELD, ""))):
            return (1, 0, "") + tuple("" for _ in names)
        valores = []
        for n in names:
            v = row.get(n)
            valores.append(0 if v is None else 1)
            valores.append(str(v))
        return (0, 0, "") + tuple(valores)

    return sorted(rows, key=key)


def _filas(tabla_nombre: str, cambios: list[dict] | None) -> tuple[list[dict], Table | None]:
    """Carga la tabla aplicando encima los cambios pendientes."""
    if not tabla_nombre:
        return [], None
    table = db.get_table(DB_PATH, tabla_nombre)
    return _order(overlay(db.load_rows(DB_PATH, table), cambios), table), table


# --------------------------------------------------------------------------- #
# Presentacion
# --------------------------------------------------------------------------- #

app.layout = lambda: _layout()


def _layout():
    tablas = [t for t, _ in db.list_tables(DB_PATH)]
    return html.Div(
        [
            dcc.Store(id=CAMBIOS_ID, data=[]),
            # Permite abrir una tabla concreta con ?tabla=cliente
            dcc.Location(id="url"),
            html.Header(
                [
                    html.Div(
                        [
                            html.H1(["MensaGes", html.Span(" · editor de bbdd.sqlite")]),
                            html.Span(id="db-name", className="subtitulo"),
                        ],
                        className="marca",
                    ),
                    html.Div(
                        [
                            html.Label("Tabla ", htmlFor="selector-tabla"),
                            dcc.Dropdown(
                                id="selector-tabla",
                                options=[{"label": t, "value": t} for t in tablas],
                                value=tablas[0] if tablas else None,
                                clearable=False,
                                searchable=True,
                                className="selector",
                            ),
                        ],
                        className="bloque-selector",
                    ),
                ],
                className="cabecera",
            ),
            html.Main(
                [
                    html.Div(
                        [
                            html.Button("+ Nueva fila", id="btn-nueva",
                                        className="btn btn-primario"),
                            html.Button("Guardar cambios", id="btn-guardar",
                                        className="btn btn-guardar"),
                            html.Button("Descartar", id="btn-descartar", className="btn"),
                            html.Button("Eliminar seleccionadas", id="btn-borrar",
                                        className="btn btn-peligro"),
                            dcc.Input(
                                id="filtro", type="search", placeholder="Filtrar…",
                                className="filtro", debounce=True,
                            ),
                        ],
                        className="barra",
                    ),
                    html.Div(id="contador", className="contador"),
                    dag.AgGrid(
                        id=GRID_ID,
                        columnDefs=[],
                        rowData=[],
                        defaultColDef=build_default_col_def(),
                        dashGridOptions=build_grid_options(),
                        className="rejilla",
                        # Cada cambio de celda actualiza la fila completa en el
                        # buffer del navegador. No toca la base de datos.
                        cellValueChanged=clientside_callback(
                            JS_EDITAR_CELDA,
                            Output(CAMBIOS_ID, "data"),
                            Input(CAMBIOS_ID, "data"),
                            Input(GRID_ID, "cellValueChanged"),
                        ),
                    ),
                    html.Div(id="mensaje", className="mensaje"),
                ],
                className="cuerpo",
            ),
            html.Details(
                [
                    html.Summary("Esquema de la tabla"),
                    html.Div(id="esquema", className="esquema"),
                ],
                className="pie",
            ),
        ],
        className="app",
    )


# --------------------------------------------------------------------------- #
# Callbacks
# --------------------------------------------------------------------------- #


@callback(
    Output("selector-tabla", "value"),
    Input("url", "search"),
)
def _tabla_de_url(search: str | None):
    """Abre la tabla indicada en la query (?tabla=cliente)."""
    tablas = [t for t, _ in db.list_tables(DB_PATH)]
    if not tablas:
        return None
    pedida = parse_qs((search or "").lstrip("?")).get("tabla", [None])[0]
    return pedida if pedida in tablas else tablas[0]


@callback(
    Output(GRID_ID, "columnDefs"),
    Output(GRID_ID, "defaultColDef"),
    Output(GRID_ID, "rowData"),
    Output(GRID_ID, "dashGridOptions"),
    Output(CAMBIOS_ID, "data"),
    Output("contador", "children"),
    Output("mensaje", "children"),
    Output("mensaje", "className"),
    Output("db-name", "children"),
    Output("esquema", "children"),
    Input("selector-tabla", "value"),
    Input("btn-nueva", "n_clicks"),
    Input("btn-guardar", "n_clicks"),
    Input("btn-descartar", "n_clicks"),
    Input("btn-borrar", "n_clicks"),
    Input("filtro", "value"),
    State(CAMBIOS_ID, "data"),
    State(GRID_ID, "selectedRows"),
    prevent_initial_call=True,
)
def _control(nombre, nueva, guardar, descartar, borrar, filtro, cambios, seleccionadas):
    """Unico punto de control de la rejilla.

    El orden de los parametros debe coincidir con el de las entradas de la
    callback: Dash los pasa posicionalmente, asi que un desajuste silencioso
    haria que, por ejemplo, el nombre de tabla acabara en otro parametro.

    Todas las salidas de la rejilla, del buffer y de los mensajes salen de aqui,
    de modo que ninguna callback compite con otra por la misma propiedad.
    """
    accion = ctx.triggered_id

    # El filtro solo reconstruye las opciones de la rejilla: no toca el buffer
    # ni vuelve a consultar la base de datos.
    if accion == "filtro":
        return (
            no_update, no_update, no_update,
            build_grid_options(quickFilterText=(filtro or "").strip()),
            no_update, no_update, no_update, no_update, no_update, no_update,
        )

    if accion == "selector-tabla":
        filas, table = _filas(nombre, None)
        return (
            build_column_defs(table) if table else [],
            build_default_col_def(),
            filas,
            build_grid_options(quickFilterText=(filtro or "").strip()),
            [],
            _contador(0),
            no_update,
            "mensaje",
            DB_PATH.name,
            _esquema(table),
        )

    if not nombre:
        return (no_update,) * 10

    pendientes = list(cambios or [])

    if accion == "btn-nueva":
        filas, table = _filas(nombre, None)
        if not table.has_pk:
            return _error("Esta tabla no tiene clave primaria: no se pueden añadir filas.")
        nueva_fila = {c.name: None for c in table.columns}
        nueva_fila[PK_FIELD] = db.make_new_pk()
        nueva_fila[NEW_FLAG] = True
        pendientes.append(nueva_fila)
        return (
            no_update, no_update,
            _order(overlay(filas, pendientes), table),
            no_update, pendientes, _contador(len(pendientes)),
            "Fila nueva preparada. Rellénala y pulsa «Guardar cambios».",
            "mensaje info", no_update, no_update,
        )

    if accion == "btn-guardar":
        if not pendientes:
            return _aviso("No hay cambios pendientes.")
        table = db.get_table(DB_PATH, nombre)
        nuevas = actualizadas = 0
        try:
            for fila in pendientes:
                resultado = db.save_row(DB_PATH, table, fila)
                if resultado == "nueva":
                    nuevas += 1
                elif resultado == "actualizada":
                    actualizadas += 1
        except db.DbError as exc:
            # No se recarga nada: se conserva lo tecleado para corregirlo.
            return _error(str(exc), pendientes)

        filas, _ = _filas(nombre, None)
        if not (nuevas or actualizadas):
            return (no_update, no_update, filas, no_update, [], _contador(0),
                    "No había ningún valor distinto al almacenado.", "mensaje info",
                    no_update, no_update)
        partes = []
        if nuevas:
            partes.append(f"{nuevas} nueva(s)")
        if actualizadas:
            partes.append(f"{actualizadas} actualizada(s)")
        return (no_update, no_update, filas, no_update, [], _contador(0),
                f"Guardado en {table.name}: {', '.join(partes)}.", "mensaje ok",
                no_update, no_update)

    if accion == "btn-descartar":
        filas, _ = _filas(nombre, None)
        return (no_update, no_update, filas, no_update, [], _contador(0),
                "Cambios descartados. La rejilla vuelve a los datos almacenados.",
                "mensaje info", no_update, no_update)

    if accion == "btn-borrar":
        tokens = [str(f.get(PK_FIELD)) for f in (seleccionadas or []) if f and f.get(PK_FIELD)]
        if not tokens:
            return _aviso("Marca alguna fila con la casilla de la izquierda.")
        table = db.get_table(DB_PATH, nombre)
        borradas, errores = db.delete_rows(DB_PATH, table, tokens)
        # Las filas nuevas nunca guardadas solo salen del buffer.
        pendientes = [c for c in pendientes if str(c.get(PK_FIELD)) not in set(tokens)]
        filas, _ = _filas(nombre, pendientes)
        if errores:
            return (no_update, no_update, filas, no_update, pendientes,
                    _contador(len(pendientes)),
                    f"Borradas {borradas}; {len(errores)} sin éxito: {errores[0]}",
                    "mensaje error", no_update, no_update)
        return (no_update, no_update, filas, no_update, pendientes,
                _contador(len(pendientes)),
                f"{borradas} fila(s) borradas de {table.name}.", "mensaje ok",
                no_update, no_update)

    return (no_update,) * 10


@callback(
    Output("btn-guardar", "disabled"),
    Output("btn-descartar", "disabled"),
    Output("btn-borrar", "disabled"),
    Output("btn-nueva", "disabled"),
    Input(CAMBIOS_ID, "data"),
    Input(GRID_ID, "selectedRows"),
    Input("selector-tabla", "value"),
)
def _habilitar_botones(cambios, seleccionadas, nombre):
    pendientes = bool(cambios)
    return (
        not pendientes,
        not pendientes,
        not bool(seleccionadas),
        not bool(nombre),
    )


# --------------------------------------------------------------------------- #
# Utilidades de vista
# --------------------------------------------------------------------------- #


def _contador(pendientes: int) -> str:
    if not pendientes:
        return "Sin cambios pendientes"
    plural = "s" if pendientes != 1 else ""
    return f"{pendientes} cambio{plural} sin guardar"


def _aviso(texto: str):
    """Mensaje informativo sin recargar la rejilla."""
    return (no_update, no_update, no_update, no_update, no_update, no_update,
            texto, "mensaje info", no_update, no_update)


def _error(texto: str, pendientes=None):
    """Mensaje de error conservando el buffer para poder corregirlo."""
    if pendientes is None:
        return (no_update, no_update, no_update, no_update, no_update, no_update,
                texto, "mensaje error", no_update, no_update)
    return (no_update, no_update, no_update, no_update, pendientes,
            _contador(len(pendientes)), texto, "mensaje error", no_update, no_update)


def _esquema(table: Table | None) -> list:
    if table is None or not table.has_pk:
        return [html.P("Esta tabla no tiene clave primaria: solo lectura.")]
    filas = [
        html.Tr(
            [
                html.Td(c.name),
                html.Td(c.declared_type or "TEXT"),
                html.Td("sí" if c.notnull else "no"),
                html.Td(
                    html.Span("PK", className="etiqueta pk")
                    if c.is_pk
                    else (html.Span(fk, className="etiqueta fk")
                          if (fk := c.foreign_key) else "")
                ),
                html.Td(", ".join(c.choices) if c.choices else (c.default or "")),
            ]
        )
        for c in table.columns
    ]
    return [
        html.Table(
            [
                html.Thead(html.Tr([
                    html.Th("Columna"), html.Th("Tipo"), html.Th("NOT NULL"),
                    html.Th("Clave"), html.Th("Valores / defecto"),
                ])),
                html.Tbody(filas),
            ],
            className="tabla-esquema",
        )
    ]


# --------------------------------------------------------------------------- #
# JavaScript de cliente
# --------------------------------------------------------------------------- #

JS_EDITAR_CELDA = """
function(cambios, evento) {
    if (!evento || !evento.data) {
        return cambios || [];
    }
    var lista = (cambios || []).slice();
    var fila = evento.data;
    var indice = -1;
    for (var i = 0; i < lista.length; i++) {
        if (lista[i].__pk__ === fila.__pk__) { indice = i; break; }
    }
    if (indice >= 0) {
        lista[indice] = fila;
    } else {
        lista.push(fila);
    }
    return lista;
}
"""
