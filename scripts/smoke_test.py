"""Pruebas del editor de bbdd.sqlite sobre Dash + AG Grid.

    uv run python scripts/smoke_test.py

No necesita servidor: importa la aplicacion y ejecuta la logica de la
callback de control (con ctx simulado), la capa de datos y la generacion de
columnas contra una base de demostracion.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

DB = REPO / "bbdd.demo.sqlite"

ok = 0
fail = 0


def check(label: str, cond: bool, extra: str = "") -> None:
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK   {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


def q(sql: str) -> list[tuple]:
    con = sqlite3.connect(DB)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


class _contexto:
    """Inyecta el contexto de callback de Dash para poder invocar _control().

    ``dash.ctx`` solo existe dentro de una callback; aqui se reproduce con el
    ContextVar que usa Dash por debajo, con la misma forma que monta el servidor.
    """

    def __init__(self, triggered_id):
        self.triggered_id = triggered_id

    def __enter__(self):
        from dash._callback_context import context_value
        from dash._utils import AttributeDict

        # Dash guarda aqui un AttributeDict; con un dict normal los atributos
        # no se verian y triggered_id saldría None.
        self._token = context_value.set(
            AttributeDict(
                {
                    "triggered_inputs": [
                        {"prop_id": f"{self.triggered_id}.n_clicks", "value": 1}
                    ],
                    "inputs_list": [],
                    "states_list": [],
                    "input_values": {},
                    "state_values": {},
                }
            )
        )
        return self

    def __exit__(self, *_):
        from dash._callback_context import context_value

        context_value.reset(self._token)
        return False


def main() -> int:
    if DB.exists():
        DB.unlink()
    import seed_demo

    seed_demo.seed(DB)

    import dash

    from mensages_web import app as A
    from mensages_web import db
    from mensages_web.db import NEW_FLAG, PK_FIELD

    A.DB_PATH = DB
    control = A._control

    def accion(gatillo, filtro="", nombre="mensajero", cambios=None, seleccionadas=None):
        with _contexto(gatillo):
            # Posicional y en el mismo orden que la declaracion de la callback:
            # Dash pasa los argumentos en ese orden, y un desajuste haria que el
            # nombre de tabla acabara en otro parametro sin avisar.
            return control(
                nombre,
                1 if gatillo == "btn-nueva" else None,
                1 if gatillo == "btn-guardar" else None,
                1 if gatillo == "btn-descartar" else None,
                1 if gatillo == "btn-borrar" else None,
                filtro,
                cambios,
                seleccionadas,
            )

    print("\n== La firma de la callback coincide con sus entradas ==")
    import inspect

    esperados = ["nombre", "nueva", "guardar", "descartar", "borrar", "filtro",
                 "cambios", "seleccionadas"]
    firma = list(inspect.signature(control).parameters)
    check("parametros en el orden de la declaracion", firma == esperados, str(firma))

    # Indices de las salidas de la callback de control
    (COLS, DEFS, DATOS, OPCIONES, BUFFER, CONTADOR, AVISO, CLASE, NOMBRE_DB, ESQ) = range(10)

    t = db.get_table(DB, "mensajero")

    print("\n== Esquema -> columnDefs ==")
    defs = A.build_column_defs(t)
    check("una columna por columna de la tabla", len(defs) == len(t.columns))
    pk = next(d for d in defs if d["field"] == "codigo")
    check("la PK no es editable", pk["editable"] is False)
    check("la PK queda fijada a la izquierda", pk.get("pinned") == "left")
    tel = next(d for d in defs if d["field"] == "telefono")
    check("entero -> editor numerico", tel["cellEditor"] == "agNumberCellEditor")
    nom = next(d for d in defs if d["field"] == "nombre")
    check("VARCHAR(80) sin maxLength (retirado en AG Grid 35)", "maxLength" not in nom)
    est = next(d for d in defs if d["field"] == "estado_civil")
    check("BOOLEAN -> editor de casilla", est["cellEditor"] == "agCheckboxCellEditor")
    check("BOOLEAN sin cellDataType", "cellDataType" not in est)
    veh = next(d for d in defs if d["field"] == "vehiculo")
    check("CHECK IN -> desplegable con sus valores",
          veh["cellEditor"] == "agSelectCellEditor"
          and veh["cellEditorParams"]["values"] == ["m", "c"])

    print("\n== Cambiar de tabla ==")
    r = accion("selector-tabla", nombre="cliente")
    check("devuelve las 10 salidas", len(r) == 10, str(len(r)))
    check("carga las filas", len(r[DATOS]) == 3, str(len(r[DATOS])))
    check("cada fila lleva su PK", all(PK_FIELD in f for f in r[DATOS]))
    check("define las columnas", len(r[COLS]) == 21, str(len(r[COLS])))
    check("limpia el buffer", r[BUFFER] == [])
    check("muestra el nombre de la base", r[NOMBRE_DB] == DB.name)
    check("describe el esquema", len(r[ESQ]) == 1)

    print("\n== Filtro rapido ==")
    r = accion("filtro", filtro="vigo", nombre="cliente")
    check("mete quickFilterText", r[OPCIONES]["quickFilterText"] == "vigo")
    check("no toca las filas", r[DATOS] is dash.no_update)
    check("no toca el buffer", r[BUFFER] is dash.no_update)

    print("\n== Nueva fila ==")
    r = accion("btn-nueva", nombre="mensajero", cambios=[])
    check("la añade a la rejilla", len(r[DATOS]) == 4, str(len(r[DATOS])))
    check("la marca como nueva", r[DATOS][-1][NEW_FLAG] is True)
    check("va al buffer", len(r[BUFFER]) == 1)
    check("cuanta el cambio", "1 cambio" in r[CONTADOR], r[CONTADOR])
    check("pide guardar", "Guardar" in r[AVISO], r[AVISO])

    print("\n== Guardar: edicion ==")
    filas = db.load_rows(DB, t)
    editada = dict(filas[0], nombre="Carlos Pena via web", telefono=600999888)
    r = accion("btn-guardar", nombre="mensajero", cambios=[editada])
    guardado = q("select nombre, telefono from mensajero where codigo=1")[0]
    check("el nombre se guardo", guardado[0] == "Carlos Pena via web", str(guardado))
    check("el telefono se guardo", guardado[1] == 600999888, str(guardado))
    check("vacía el buffer", r[BUFFER] == [])
    check("avisa", "Guardado" in r[AVISO], r[AVISO])
    check("marca el mensaje como ok", r[CLASE] == "mensaje ok", r[CLASE])
    check("recarga la rejilla", len(r[DATOS]) == 3)
    check("contador a cero", "Sin cambios" in r[CONTADOR])

    print("\n== Guardar: alta con celdas sin tocar ==")
    nueva = {
        "__pk__": db.make_new_pk(), "__nuevo__": True, "codigo": 4,
        "nombre": "Nuevo desde la web", "cif": "44444444D", "telefono": 600444444,
        "estado_civil": 1, "servicio_militar": 0, "vehiculo": "c", "obs": None,
        "dir_calle": None, "dir_numero": None, "dir_piso": None, "dir_letra": None,
        "dir_cpostal": None, "dir_localidad": "Vigo", "dir_provincia": "Pontevedra",
    }
    r = accion("btn-guardar", nombre="mensajero", cambios=[nueva])
    alta = q("select nombre, dir_numero, dir_cpostal from mensajero where codigo=4")
    check("la fila existe", len(alta) == 1, str(alta))
    check("las celdas vacias toman el DEFAULT del esquema",
          alta and alta[0][1] == 0 and alta[0][2] == 0, str(alta))
    check("avisa de la alta", "1 nueva(s)" in r[AVISO], r[AVISO])

    print("\n== Guardar: sin cambios pendientes ==")
    r = accion("btn-guardar", nombre="mensajero", cambios=[])
    check("avisa", "No hay cambios" in r[AVISO], r[AVISO])
    check("no toca las filas", r[DATOS] is dash.no_update)

    print("\n== Validacion ==")
    larga = dict(db.load_rows(DB, t)[1], nombre="x" * 200)
    r = accion("btn-guardar", nombre="mensajero", cambios=[larga])
    check("rechaza texto demasiado largo", "80 caracteres" in r[AVISO], r[AVISO])
    check("marca el mensaje como error", r[CLASE] == "mensaje error", r[CLASE])
    check("conserva el buffer para corregir", len(r[BUFFER]) == 1)
    check("no recarga la rejilla", r[DATOS] is dash.no_update)
    check("el valor largo no se guardo",
          q("select nombre from mensajero where codigo=2")[0][0] == "Marta Nunez")

    mala = dict(db.load_rows(DB, t)[1], vehiculo="z")
    r = accion("btn-guardar", nombre="mensajero", cambios=[mala])
    check("rechaza valor fuera del CHECK", "solo admite" in r[AVISO], r[AVISO])
    check("no se guardo", q("select vehiculo from mensajero where codigo=2")[0][0] == "c")

    print("\n== Descartar ==")
    total = q("select count(*) from mensajero")[0][0]
    r = accion("btn-descartar", nombre="mensajero", cambios=[editada])
    check("recarga desde la base", len(r[DATOS]) == total, f"{len(r[DATOS])} vs {total}")
    check("descarta los pendientes", r[BUFFER] == [])
    check("avisa", "descartados" in r[AVISO].lower(), r[AVISO])

    print("\n== Borrar seleccionadas ==")
    sel = [{"__pk__": '["4"]', "codigo": 4}]
    r = accion("btn-borrar", nombre="mensajero", cambios=[], seleccionadas=sel)
    check("la fila se borra", len(q("select 1 from mensajero where codigo=4")) == 0)
    check("avisa", "1 fila(s) borradas" in r[AVISO], r[AVISO])

    protegido = [{"__pk__": '["1"]', "codigo": 1}]
    r = accion("btn-borrar", nombre="mensajero", cambios=[], seleccionadas=protegido)
    check("un mensajero en un albaran no se borra",
          len(q("select 1 from mensajero where codigo=1")) == 1)
    check("explica la clave foranea", "clave foránea" in r[AVISO], r[AVISO])

    r = accion("btn-borrar", nombre="mensajero", cambios=[], seleccionadas=[])
    check("sin seleccion avisa", "Marca alguna fila" in r[AVISO], r[AVISO])

    print("\n== Descartar una fila nueva ==")
    r = accion("btn-nueva", nombre="cliente", cambios=[])
    token = r[BUFFER][0][PK_FIELD]
    r = accion("btn-borrar", nombre="cliente", cambios=r[BUFFER], seleccionadas=[{"__pk__": token}])
    check("la fila nueva desaparece sin tocar la base",
          len(r[DATOS]) == 3 and r[BUFFER] == [], f"{len(r[DATOS])} filas")

    print("\n== Botones ==")
    check("sin cambios: guardar y descartar desactivados",
          A._habilitar_botones([], [], "cliente") == (True, True, True, False))
    check("con cambios: guardar y descartar activos",
          A._habilitar_botones([{"a": 1}], [], "cliente") == (False, False, True, False))
    check("con seleccion: borrar activo",
          A._habilitar_botones([], [{"a": 1}], "cliente")[2] is False)

    print("\n== Overlay ==")
    base_filas = db.load_rows(DB, db.get_table(DB, "cliente"))
    pend = [dict(base_filas[0], nombre="Editado en el navegador")]
    comb = A.overlay(base_filas, pend)
    check("la fila editada conserva su sitio", comb[0]["nombre"] == "Editado en el navegador")
    check("no duplica filas", len(comb) == len(base_filas))
    check("sin pendientes devuelve igual", A.overlay(base_filas, []) == base_filas)
    nueva_f = dict(base_filas[0], __pk__="nuevo:x")
    check("las filas nuevas van al final",
          A.overlay(base_filas, pend + [nueva_f])[-1][PK_FIELD] == "nuevo:x")

    print("\n== Integridad referencial ==")
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute(
        "insert into cliente (id_cliente, telefono, nombre, descuento,"
        " recargo_equivalencia, cobrar_reembolso, dir_numero, dir_piso, dir_cpostal,"
        " fecha_alta_dia, fecha_alta_mes, fecha_alta_anio, fecha_alta_dow)"
        " values (99, 900000001, 'Para cascade', 0, 0, 0, 0, 0, 0, 1, 1, 1996, 1)"
    )
    con.executemany("insert into cliente_tarifa values (99, ?, 'S', 100, 0, 0, 0)", [(1,), (2,)])
    con.commit()
    con.close()
    r = accion("btn-borrar", nombre="cliente", cambios=[],
               seleccionadas=[{"__pk__": '["99"]'}])
    check("borra el cliente", len(q("select 1 from cliente where id_cliente=99")) == 0)
    check("y arrastra sus tarifas (CASCADE)",
          q("select count(*) from cliente_tarifa where id_cliente=99")[0][0] == 0)

    print("\n== Consulta con comillas (inyeccion) ==")
    con = sqlite3.connect(DB)
    malas = con.execute("select nombre from cliente where nombre = ?",
                        ("'; drop table cliente; --",)).fetchall()
    con.close()
    check("el valor va ligado, no concatenado", malas == [])
    check("la tabla sigue existiendo", len(q("select 1 from cliente")) >= 2)

    print(f"\n{'=' * 52}\n  {ok} correctas, {fail} fallidas\n{'=' * 52}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
