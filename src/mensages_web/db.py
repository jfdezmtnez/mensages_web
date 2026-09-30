"""Acceso a la base de datos SQLite: carga de filas y escrituras.

La interfaz trabaja con filas completas (diccionarios) en lugar de formularios
HTML, porque en la rejilla cada celda editada viaja ya como un objeto con la
clave primaria incluida.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .meta import Table, q, read_schema

# --------------------------------------------------------------------------- #
# Localizacion de la base de datos
# --------------------------------------------------------------------------- #

_HERE = Path(__file__).resolve()
PROJECT_DIR = _HERE.parent.parent.parent          # .../web
REPO_DIR = PROJECT_DIR.parent                    # .../mensages


def default_db_path() -> Path:
    """Ruta de bbdd.sqlite.

    Se puede fijar con la variable de entorno ``MENSAGES_DB``; si no, se buscan
    ``bbdd.sqlite`` en la raiz del repositorio y en la raiz del proyecto.
    """
    env = os.environ.get("MENSAGES_DB")
    if env:
        return Path(env).expanduser().resolve()
    for candidate in (REPO_DIR / "bbdd.sqlite", PROJECT_DIR / "bbdd.sqlite"):
        if candidate.is_file():
            return candidate
    return REPO_DIR / "bbdd.sqlite"


# --------------------------------------------------------------------------- #
# Errores
# --------------------------------------------------------------------------- #


class NotFound(Exception):
    """La tabla o la fila solicitada no existe."""


class DbError(Exception):
    """Error de la base de datos, ya traducido a texto para el usuario."""


# --------------------------------------------------------------------------- #
# Claves primarias dentro de la fila
# --------------------------------------------------------------------------- #

PK_FIELD = "__pk__"
NEW_FLAG = "__nuevo__"
NEW_PREFIX = "nuevo:"


def encode_pk(values) -> str:
    return json.dumps([str(v) for v in values])


def decode_pk(token: str) -> list[str]:
    return json.loads(token)


def is_new(token: str) -> bool:
    return str(token).startswith(NEW_PREFIX)


def make_new_pk() -> str:
    import uuid

    return f"{NEW_PREFIX}{uuid.uuid4().hex[:12]}"


# --------------------------------------------------------------------------- #
# Conexion
# --------------------------------------------------------------------------- #


def connect(db_path: Path, *, write: bool = False) -> sqlite3.Connection:
    """Abre la base de datos.

    Las escrituras usan un ``timeout`` largo porque SQLite serializa a los
    escritores y la app puede coexistir con otros procesos abriendo el fichero.
    """
    con = sqlite3.connect(db_path, timeout=15.0, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 15000")
    return con


# --------------------------------------------------------------------------- #
# Consultas
# --------------------------------------------------------------------------- #


def list_tables(db_path: Path) -> list[tuple[str, int]]:
    """(nombre de tabla, numero de filas) de todas las tablas de usuario."""
    con = connect(db_path)
    try:
        out = []
        for name in read_schema(str(db_path)):
            count = con.execute(f"SELECT COUNT(*) FROM {q(name)}").fetchone()[0]
            out.append((name, count))
        return out
    finally:
        con.close()


def get_table(db_path: Path, table_name: str) -> Table:
    schema = read_schema(str(db_path))
    if table_name not in schema:
        raise NotFound(f"No existe la tabla «{table_name}».")
    return schema[table_name]


def load_rows(db_path: Path, table: Table, limit: int = 5000) -> list[dict]:
    """Todas las filas de la tabla, con la clave primaria anadida a cada una.

    Cada fila lleva ``__pk__`` (JSON de los valores de la clave primaria), que
    es lo que permite despues editarla o borrarla sin ambiguedad.
    """
    if not table.has_pk:
        return []
    con = connect(db_path)
    try:
        order = ", ".join(q(c.name) for c in table.pk_columns)
        rows = con.execute(
            f"SELECT * FROM {q(table.name)} ORDER BY {order} LIMIT ?", (limit,)
        ).fetchall()
        out = []
        for row in rows:
            data = dict(row)
            data[PK_FIELD] = encode_pk([row[c.name] for c in table.pk_columns])
            out.append(data)
        return out
    finally:
        con.close()


def fetch_row(db_path: Path, table: Table, pk_values) -> sqlite3.Row | None:
    if not table.has_pk or len(pk_values) != len(table.pk_columns):
        return None
    con = connect(db_path)
    try:
        where = " AND ".join(f"{q(c.name)} = ?" for c in table.pk_columns)
        return con.execute(
            f"SELECT * FROM {q(table.name)} WHERE {where}", list(pk_values)
        ).fetchone()
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Coercion y validacion
# --------------------------------------------------------------------------- #


def nullable(column) -> bool:
    """Una columna admite NULL si no es NOT NULL o si su DEFAULT es NULL."""
    return (not column.notnull) and column.default is None


_TRUE_LITERALS = ("true", "t", "yes", "y", "on")
_FALSE_LITERALS = ("false", "f", "no", "n", "off")


def _default_value(column):
    """Interpreta el DEFAULT declarado en el DDL.

    Una celda que el usuario no ha tocado llega vacia; en vez de fallar contra
    el NOT NULL, se usa el valor por defecto que el propio esquema define.
    """
    literal = str(column.default).strip()
    kind = column.kind

    if len(literal) >= 2 and literal[0] == literal[-1] and literal[0] in "'\"":
        return literal[1:-1].replace("''", "'")

    bajo = literal.lower()
    if kind == "bool":
        if bajo in _TRUE_LITERALS:
            return 1
        if bajo in _FALSE_LITERALS:
            return 0
    if kind in ("int", "float"):
        try:
            return int(literal) if kind == "int" else float(literal)
        except ValueError as exc:
            raise DbError(
                f"El valor por defecto de «{column.name}» no es valido: {literal!r}"
            ) from exc
    return literal


def coerce_value(column, raw):
    """Convierte un valor de la rejilla al tipo declarado por la columna.

    Reglas:

    * ``BOOLEAN`` -> 1/0 (una casilla sin marcar llega como ``None`` o ``0``).
    * texto -> se guarda tal cual. Si llega vacio y la columna admite ``NULL``
      se guarda ``NULL``; si es ``NOT NULL`` se guarda cadena vacia, que es el
      valor por defecto que usa el esquema original (``DEFAULT ''``).
    * numerico -> vacio significa ``NULL`` en columnas opcionales y error en las
      obligatorias.

    La rejilla manda ``None`` en las celdas que el usuario no ha tocado, asi
    que ``None`` se trata igual que una cadena vacia.
    """
    kind = column.kind

    if kind == "bool":
        if raw is None:
            return 0
        if isinstance(raw, bool):
            return 1 if raw else 0
        return 1 if str(raw) in ("1", "1.0", "true", "True", "s", "S") else 0

    if raw is None:
        raw = ""

    vacio = isinstance(raw, str) and raw.strip() == ""
    if vacio:
        if nullable(column):
            return None
        if column.default is not None:
            return _default_value(column)
        if kind == "text":
            return ""
        raise DbError(f"El campo «{column.name}» es obligatorio.")

    if kind == "int":
        try:
            return int(float(raw))
        except (TypeError, ValueError) as exc:
            raise DbError(f"El campo «{column.name}» debe ser un numero entero.") from exc
    if kind == "float":
        try:
            return float(str(raw).replace(",", "."))
        except (TypeError, ValueError) as exc:
            raise DbError(f"El campo «{column.name}» debe ser un numero.") from exc
    return str(raw)


def validate(table: Table, data: dict) -> None:
    """Comprueba longitudes y listas de valores antes de tocar la base."""
    for column in table.columns:
        if column.name not in data:
            continue
        value = data[column.name]
        if value is None:
            if column.required:
                raise DbError(f"El campo «{column.name}» es obligatorio.")
            continue
        if column.choices and str(value) not in column.choices:
            raise DbError(
                f"El campo «{column.name}» solo admite: {', '.join(column.choices)}."
            )
        maxlen = column.max_length
        if maxlen and column.is_text and len(str(value)) > maxlen:
            raise DbError(
                f"El campo «{column.name}» admite como máximo {maxlen} caracteres."
            )


# --------------------------------------------------------------------------- #
# Escrituras
# --------------------------------------------------------------------------- #


def save_row(db_path: Path, table: Table, row: dict) -> str:
    """Inserta o actualiza una fila segun su marca ``__nuevo__``.

    Devuelve ``"nueva"``, ``"actualizada"`` o ``"sin_cambios"``.
    """
    token = str(row.get(PK_FIELD, ""))
    if is_new(token):
        return _insert(db_path, table, row)
    return _update(db_path, table, token, row)


def _insert(db_path: Path, table: Table, row: dict) -> str:
    con = connect(db_path)
    try:
        con.execute("BEGIN IMMEDIATE")
        data: dict[str, object] = {}
        for column in table.insertable_columns:
            data[column.name] = coerce_value(column, row.get(column.name))

        generated = table.generated_pk
        if generated is not None and data.get(generated.name) in (None, ""):
            data[generated.name] = con.execute(
                f"SELECT COALESCE(MAX({q(generated.name)}), 0) + 1 FROM {q(table.name)}"
            ).fetchone()[0]

        validate(table, data)
        _insert_statement(con, table, data)

        # Una PK autogenerada debe viajar de vuelta a la rejilla.
        if generated is not None:
            row[generated.name] = data[generated.name]
        row[PK_FIELD] = encode_pk(
            [data.get(c.name) if c is not generated else data[generated.name]
             for c in table.pk_columns]
        )
        row[NEW_FLAG] = False
        con.execute("COMMIT")
        return "nueva"
    except sqlite3.Error as exc:
        _rollback(con)
        raise DbError(translate(exc)) from exc
    except DbError:
        _rollback(con)
        raise
    finally:
        con.close()


def _insert_statement(con: sqlite3.Connection, table: Table, data: dict) -> None:
    cols = list(data)
    if not cols:
        raise DbError("La fila no contiene ningun dato que insertar.")
    con.execute(
        f"INSERT INTO {q(table.name)} ({', '.join(q(c) for c in cols)})"
        f" VALUES ({', '.join('?' for _ in cols)})",
        [data[c] for c in cols],
    )


def _update(db_path: Path, table: Table, token: str, row: dict) -> str:
    pk_values = decode_pk(token)
    if len(pk_values) != len(table.pk_columns):
        raise NotFound("Clave primaria incompleta.")

    con = connect(db_path)
    try:
        con.execute("BEGIN IMMEDIATE")
        where = " AND ".join(f"{q(c.name)} = ?" for c in table.pk_columns)
        current = con.execute(
            f"SELECT * FROM {q(table.name)} WHERE {where}", pk_values
        ).fetchone()
        if current is None:
            raise NotFound("La fila que intentas modificar ya no existe.")

        # Solo se escribe lo que ha cambiado: AG Grid manda la fila entera, pero
        # reescribir columnas ajenas al cambio es pedir problemas.
        assignments: dict[str, object] = {}
        for column in table.editable_columns:
            if column.name not in row:
                continue
            new_value = coerce_value(column, row[column.name])
            if new_value == current[column.name]:
                continue
            assignments[column.name] = new_value

        if not assignments:
            con.execute("COMMIT")
            return "sin_cambios"

        validate(table, {**dict(current), **assignments})
        sets = ", ".join(f"{q(c)} = ?" for c in assignments)
        con.execute(
            f"UPDATE {q(table.name)} SET {sets} WHERE {where}",
            [*assignments.values(), *pk_values],
        )
        con.execute("COMMIT")
        return "actualizada"
    except sqlite3.Error as exc:
        _rollback(con)
        raise DbError(translate(exc)) from exc
    except (DbError, NotFound):
        _rollback(con)
        raise
    finally:
        con.close()


def delete_rows(db_path: Path, table: Table, tokens) -> tuple[int, list[str]]:
    """Borra las filas indicadas. Todas o ninguna.

    Devuelve (borradas, errores). Los errores son por fila, para que un
    borrado bloqueado por una clave foranea no impida borrar el resto.
    """
    borradas = 0
    errores: list[str] = []
    for token in tokens:
        if is_new(token):
            continue
        try:
            _delete_one(db_path, table, decode_pk(token))
            borradas += 1
        except NotFound:
            continue
        except DbError as exc:
            errores.append(str(exc))
    return borradas, errores


def _delete_one(db_path: Path, table: Table, pk_values) -> None:
    where = " AND ".join(f"{q(c.name)} = ?" for c in table.pk_columns)
    con = connect(db_path)
    try:
        con.execute("BEGIN IMMEDIATE")
        cur = con.execute(f"DELETE FROM {q(table.name)} WHERE {where}", list(pk_values))
        if cur.rowcount == 0:
            raise NotFound("La fila ya no existe.")
        con.execute("COMMIT")
    except sqlite3.Error as exc:
        _rollback(con)
        raise DbError(translate(exc)) from exc
    finally:
        con.close()


def _rollback(con: sqlite3.Connection) -> None:
    try:
        con.execute("ROLLBACK")
    except sqlite3.Error:
        pass


# --------------------------------------------------------------------------- #
# Traduccion de errores
# --------------------------------------------------------------------------- #


def translate(exc: sqlite3.Error) -> str:
    """Traduce los errores de SQLite a un mensaje comprensible."""
    text = str(exc)
    lowered = text.lower()

    if lowered.startswith("not null constraint failed"):
        columna = text.split(":", 1)[1].strip()
        return f"Falta el valor de «{columna}», que es obligatorio."
    if lowered.startswith("check constraint failed"):
        constraint = text.split(":", 1)[1].strip() or "(sin nombre)"
        return (
            f"La restricción «{constraint}» del esquema no se cumple "
            "con estos valores."
        )
    if "foreign key constraint failed" in lowered:
        return (
            "Fila referenciada por otros registros (clave foránea): "
            "borra o reasigna primero las filas hijas."
        )
    if "unique constraint failed" in lowered:
        return "Ya existe una fila con esa clave."
    if "datatype mismatch" in lowered or "not numeric" in lowered:
        return "Algún campo numérico no contiene un número válido."
    return f"Error de la base de datos: {text}"
