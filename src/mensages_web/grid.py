"""Traduce el esquema SQLite a ``columnDefs`` de AG Grid.

Cada tipo declarado en el DDL se convierte en el editor y el renderizador que
le corresponden, de modo que en la rejilla un ``BOOLEAN`` es una casilla, un
``CHECK (col IN (...))`` es un desplegable y un entero no acepta texto.
"""

from __future__ import annotations

from .db import NEW_FLAG, PK_FIELD
from .meta import KIND_BOOL, KIND_FLOAT, KIND_INT, Table

#: Campos internos que la rejilla usa para identificar filas y no se muestran.
HIDDEN_FIELDS = (PK_FIELD, NEW_FLAG)


def build_column_defs(table: Table) -> list[dict]:
    """Definiciones de columna de AG Grid para una tabla del esquema."""
    defs: list[dict] = []
    for column in table.columns:
        defs.append(_column_def(table, column))
    return defs


def _column_def(table: Table, column) -> dict:
    editable = not column.is_pk
    col: dict = {
        "field": column.name,
        "headerName": column.name,
        "editable": editable,
        "sortable": True,
        "filter": True,
        "resizable": True,
        "minWidth": 110,
    }

    if column.is_pk:
        col.update(
            {
                "cellClass": "celda-pk",
                "pinned": "left",
                "lockPosition": True,
                "headerTooltip": f"Clave primaria ({column.declared_type})",
            }
        )
    if column.foreign_key:
        col["headerTooltip"] = f"Clave foránea → {column.foreign_key}"

    kind = column.kind

    if kind == KIND_BOOL:
        # La casilla de edicion es nativa de AG Grid Community. El valor se ve
        # como 0/1 porque dash-ag-grid 35 ya no acepta renderizadores escritos
        # en Python: cellRenderer solo admite nombres de componente.
        col.update(
            {
                "cellEditor": "agCheckboxCellEditor",
                "type": "rightAligned",
                "width": 150,
                "minWidth": 140,
                "headerTooltip": f"{column.name} · booleano: 1 = sí, 0 = no",
            }
        )
    elif column.choices:
        col.update(
            {
                "cellEditor": "agSelectCellEditor",
                "cellEditorParams": {"values": list(column.choices)},
                "width": 140,
            }
        )
    elif kind == KIND_INT:
        col.update({"cellDataType": "number", "cellEditor": "agNumberCellEditor"})
    elif kind == KIND_FLOAT:
        col.update({"cellDataType": "number", "cellEditor": "agNumberCellEditor"})
        if column.max_length:
            col["cellEditorParams"] = {"precision": max(0, column.max_length - 2)}
    else:
        col.update({"cellDataType": "text", "cellEditor": "agTextCellEditor"})
        # AG Grid 35 quito colDef.maxLength; la longitud maxima la comprueba
        # la capa de datos al guardar, leyendo el VARCHAR(n) del esquema.
        if column.max_length and column.max_length >= 40:
            col["flex"] = 2
            col["minWidth"] = 180

    return col


def build_default_col_def() -> dict:
    """Opciones comunes a todas las columnas."""
    return {
        "sortable": True,
        "filter": True,
        "resizable": True,
        "wrapHeaderText": True,
        "autoHeaderHeight": True,
    }


def build_grid_options(**extra) -> dict:
    """Opciones de la rejilla (las que no tienen prop propio)."""
    options = {
        "rowSelection": {
            "mode": "multiRow",
            "checkboxes": True,
            "headerCheckbox": True,
            "enableClickSelection": False,
        },
        "pagination": True,
        "paginationPageSize": 50,
        "paginationPageSizeSelector": [25, 50, 100, 250],
        "animateRows": False,
        "undoRedoCellEditing": True,
        "undoRedoCellEditingLimit": 20,
        "tooltipShowDelay": 400,
        # Desde AG Grid 33 esto es opcion de la rejilla, no del colDef.
        "stopEditingWhenCellsLoseFocus": True,
    }
    options.update(extra)
    return options
