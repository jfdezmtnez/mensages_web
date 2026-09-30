"""Introspeccion del esquema SQLite y metadatos de columnas.

Todo el CRUD de la aplicacion se genera a partir de la informacion que se lee
de la propia base de datos (``sqlite_master`` y ``PRAGMA table_info``), por lo
que no hay lista de tablas ni de columnas escrita a mano.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# --------------------------------------------------------------------------- #
# Identificadores
# --------------------------------------------------------------------------- #

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def check_ident(name: str) -> str:
    """Valida un identificador de la base de datos.

    Los nombres de tablas y columnas solo llegan desde ``sqlite_master``, pero
    se validan igualmente porque acaban interpolados en el SQL (los valores si
    viajan siempre como parametros ligados).
    """
    if not _IDENT_RE.match(name):
        raise ValueError(f"Identificador no permitido: {name!r}")
    return name


def q(name: str) -> str:
    """Cita un identificador para SQLite."""
    return f'"{check_ident(name)}"'


# --------------------------------------------------------------------------- #
# Metadatos
# --------------------------------------------------------------------------- #

#: Tipo de campo que se pinta en el formulario.
KIND_BOOL = "bool"
KIND_INT = "int"
KIND_FLOAT = "float"
KIND_TEXT = "text"

_TRUE_FALSE = ("0", "1")


@dataclass(frozen=True)
class Column:
    name: str
    declared_type: str
    notnull: bool
    default: str | None
    pk_index: int          # 0 = no forma parte de la clave primaria
    choices: tuple[str, ...]  # valores permitidos por un CHECK (col IN (...))
    foreign_key: str | None   # "tabla.columna"

    @property
    def is_pk(self) -> bool:
        return self.pk_index > 0

    @property
    def has_default(self) -> bool:
        return self.default is not None

    @property
    def required(self) -> bool:
        """Obligatorio en el formulario de alta/edicion."""
        return self.notnull and not self.has_default and not self.is_pk

    @property
    def kind(self) -> str:
        if self.choices == _TRUE_FALSE:
            return KIND_BOOL
        t = self.declared_type.upper()
        if "BOOL" in t:
            return KIND_BOOL
        if any(k in t for k in ("INT", "REAL", "FLOA", "DOUB", "NUM", "DEC", "FLOA")):
            if any(k in t for k in ("REAL", "FLOA", "DOUB", "NUM", "DEC")):
                return KIND_FLOAT
            return KIND_INT
        return KIND_TEXT

    @property
    def is_text(self) -> bool:
        return self.kind == KIND_TEXT

    @property
    def max_length(self) -> int | None:
        m = re.search(r"\(\s*(\d+)", self.declared_type)
        return int(m.group(1)) if m else None


@dataclass
class Table:
    name: str
    sql: str
    columns: list[Column] = field(default_factory=list)

    @property
    def pk_columns(self) -> list[Column]:
        return sorted((c for c in self.columns if c.is_pk), key=lambda c: c.pk_index)

    @property
    def pk_names(self) -> list[str]:
        return [c.name for c in self.pk_columns]

    @property
    def has_pk(self) -> bool:
        return bool(self.pk_columns)

    @property
    def generated_pk(self) -> Column | None:
        """PK que hay que calcular al insertar: una sola columna ``INTEGER``.

        SQLite la trata como alias de ``rowid`` y no admite actualizarla, asi
        que el formulario la muestra como solo lectura.
        """
        pks = self.pk_columns
        if len(pks) != 1:
            return None
        pk = pks[0]
        declared = pk.declared_type.upper().strip()
        return pk if declared in ("INTEGER", "INT", "") else None

    @property
    def editable_columns(self) -> list[Column]:
        """Columnas que aparecen en el formulario de edicion.

        Se excluye toda la clave primaria: la fila se identifica por ella, y
        permitir cambiarla en un UPDATE dejaria filas inaccesibles. En las
        tablas con PK ``INTEGER`` autogenerada la exclusion es ademas
        obligatoria porque SQLite no admite actualizarla.
        """
        return [c for c in self.columns if not c.is_pk]

    @property
    def insertable_columns(self) -> list[Column]:
        """Columnas que aparecen en el formulario de alta.

        La PK ``INTEGER`` de una sola pieza se autocompleta con
        ``MAX(id) + 1``, igual que el ``rowid`` de SQLite, asi que no se pide.
        """
        gen = self.generated_pk
        return [c for c in self.columns if gen is None or c is not gen]


# --------------------------------------------------------------------------- #
# Lectura del esquema
# --------------------------------------------------------------------------- #

_CHECK_IN_RE_CACHE: dict[str, dict[str, tuple[str, ...]]] = {}


def _parse_check_choices(sql: str) -> dict[str, tuple[str, ...]]:
    """Extrae de los CHECK del DDL las columnas con lista cerrada de valores.

    Reconoce ``col IN ('a','b')`` y ``col IN (0,1)``, que es como el esquema
    declara los booleanos y los campos enumerados (portes, vehiculo...).
    """
    cached = _CHECK_IN_RE_CACHE.get(sql)
    if cached is not None:
        return cached

    result: dict[str, tuple[str, ...]] = {}
    body = re.sub(r"--[^\n]*", " ", sql)  # quita comentarios de linea
    for match in re.finditer(
        r"(?P<col>[A-Za-z_][A-Za-z0-9_]*)\s+IN\s*\((?P<vals>[^)]*)\)", body, re.IGNORECASE
    ):
        col = match.group("col")
        raw = match.group("vals")
        values: list[str] = []
        for item in raw.split(","):
            item = item.strip()
            if len(item) >= 2 and item[0] == item[-1] == "'":
                values.append(item[1:-1])          # literal de texto
            elif re.fullmatch(r"-?\d+", item):
                values.append(item)                # literal numerico
        if values:
            result.setdefault(col, tuple(values))

    _CHECK_IN_RE_CACHE[sql] = result
    return result


def _foreign_keys(con: sqlite3.Connection, table: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for fk in con.execute(f"PRAGMA foreign_key_list({q(table)})"):
        if fk[3] is not None:
            out[fk[3]] = f"{fk[2]}.{fk[4]}"
    return out


#: Posiciones de las columnas que devuelve ``PRAGMA table_info``.
_TABLE_INFO = ("cid", "name", "type", "notnull", "dflt_value", "pk")

_CID, _NAME, _TYPE, _NOTNULL, _DEFAULT, _PK = range(6)


@lru_cache(maxsize=1)
def read_schema(db_path: str) -> dict[str, Table]:
    """Devuelve {tabla: Table} para todas las tablas de usuario de la base."""
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        tables: dict[str, Table] = {}
        names = [
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master"
                " WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                " ORDER BY name"
            )
        ]
        for name in names:
            sql = con.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
            ).fetchone()[0]
            checks = _parse_check_choices(sql)
            fks = _foreign_keys(con, name)

            columns: list[Column] = []
            for info in con.execute(f"PRAGMA table_info({q(name)})"):
                col_name, ctype, notnull, default, pk_index = (
                    info[_NAME], info[_TYPE], info[_NOTNULL], info[_DEFAULT], info[_PK]
                )
                columns.append(
                    Column(
                        name=col_name,
                        declared_type=ctype or "",
                        notnull=bool(notnull),
                        default=default,
                        pk_index=int(pk_index),
                        choices=checks.get(col_name, ()),
                        foreign_key=fks.get(col_name),
                    )
                )
            tables[name] = Table(name=name, sql=sql or "", columns=columns)
        return tables
    finally:
        con.close()
