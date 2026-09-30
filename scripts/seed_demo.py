"""Crea una base de datos de demostracion a partir de schema.sql.

    uv run python scripts/seed_demo.py
    uv run python scripts/seed_demo.py --db ruta.sqlite

No toca ``bbdd.sqlite``: por defecto escribe ``bbdd.demo.sqlite`` en la raiz del
repositorio, para poder probar el editor con contenido sin ensuciar los datos
reales.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA = ROOT / "schema.sql"


def insert(con: sqlite3.Connection, table: str, **values) -> None:
    cols = list(values)
    con.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        [values[c] for c in cols],
    )


def seed(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))

    # --- configuracion -----------------------------------------------------
    insert(
        con,
        "config",
        id_config=1,
        iva_porcentaje=16.0,
        pts_km_coche=45,
        pts_km_moto=40,
        ruta_trabajo="C:\\MENSAGES\\",
        permit=1,
        fecha_prueba=19960420,
        ingreso_mes=0,
        ultimo_mes_fact="ABR1996",
        ultimo_num_factura=2,
        ultimo_disco=1,
        disco_nuevo=1,
    )
    insert(con, "instalacion", id_instalacion=1, ruta="C:\\MENSAGES\\", codigo=39580626)

    for pos, value in enumerate(
        [172, 169, 176, 176, 173, 167, 179, 178, 173, 165], start=1
    ):
        insert(con, "licencia_clave", posicion=pos, valor=value)

    for orden, (desc, precio, peso, tiempo, km) in enumerate(
        [
            ("Moto", 200, 0, 18, 40),
            ("Coche", 425, 20, 20, 45),
            ("Po-Express", 450, 30, 0, 0),
            ("S. Regular", 400, 30, 0, 0),
            ("Reg. Cap.", 1000, 40, 0, 0),
            ("Reg. Pob.", 1300, 40, 0, 0),
            ("Nac. Cap.", 1350, 975, 0, 0),
            ("Nac. Pob.", 1800, 975, 0, 0),
            ("S. Especial", 0, 0, 0, 0),
        ],
        start=1,
    ):
        insert(
            con, "tarifa_defecto_cliente", orden=orden, descripcion=desc,
            precio=precio, ex_peso=peso, ex_tiempo=tiempo, ex_km=km,
        )

    for orden, (desc, precio, peso, tiempo, km) in enumerate(
        [
            ("Moto", 100, 0, 9, 20),
            ("Coche", 225, 10, 10, 22),
            ('Serv. "75"', 75, 0, 0, 0),
        ],
        start=1,
    ):
        insert(
            con, "tarifa_defecto_mensajero", orden=orden, descripcion=desc,
            precio=precio, ex_peso=peso, ex_tiempo=tiempo, ex_km=km,
        )

    # ---masters -----------------------------------------------------------
    for codigo, nombre, cif, porcentaje, telefono, calle, localidad in [
        (1, "Ana Rois Zhang", "12345678A", 10, 986123456, "Rúa da Porta 4", "Vigo"),
        (2, "Luis Moure Vidal", "87654321B", 5, 986987654, "Avenida Atlantida 9", "Vigo"),
    ]:
        insert(
            con, "comercial", codigo=codigo, nombre=nombre, cif=cif,
            porcentaje=porcentaje, telefono=telefono, dir_calle=calle,
            dir_localidad=localidad, dir_provincia="Pontevedra",
        )

    for codigo, nombre, cif, telefono, estado, militar, vehiculo in [
        (1, "Carlos Pena", "11111111C", 600111222, 1, 1, "m"),
        (2, "Marta Nunez", "22222222D", 600333444, 0, 0, "c"),
        (3, "Jose Itoiz", "33333333E", 600555666, 1, 0, "m"),
    ]:
        insert(
            con, "mensajero", codigo=codigo, nombre=nombre, cif=cif,
            telefono=telefono, estado_civil=estado, servicio_militar=militar,
            vehiculo=vehiculo, dir_localidad="Vigo", dir_provincia="Pontevedra",
        )

    clientes = [
        dict(id_cliente=1, telefono=986111222, nombre="Distribuciones del Faro S.L.",
             cif="B36123456", forma_pago="Recibo bancario", cod_comercial=1,
             descuento=10, recargo_equivalencia=1, cobrar_reembolso=0,
             obs="Cliente habitual", dia=3, mes=1),
        dict(id_cliente=2, telefono=986222333, nombre="Talleres Rey S.A.",
             cif="A28123456", forma_pago="Contado 30 dias", cod_comercial=1,
             descuento=0, recargo_equivalencia=0, cobrar_reembolso=1,
             obs="Paga con reembolso", dia=14, mes=2),
        dict(id_cliente=3, telefono=986333444, nombre="Concesionaria del Centro",
             cif="B48123456", forma_pago="Transferencia", cod_comercial=2,
             descuento=5, recargo_equivalencia=1, cobrar_reembolso=0,
             obs="", dia=22, mes=3),
    ]
    for c in clientes:
        insert(
            con, "cliente", id_cliente=c["id_cliente"], telefono=c["telefono"],
            nombre=c["nombre"], cif=c["cif"], forma_pago=c["forma_pago"],
            cod_comercial=c["cod_comercial"], descuento=c["descuento"],
            recargo_equivalencia=c["recargo_equivalencia"],
            cobrar_reembolso=c["cobrar_reembolso"], obs=c["obs"],
            dir_calle="Ronda de Orense 12", dir_localidad="Vigo",
            dir_provincia="Pontevedra", fecha_alta_dia=c["dia"],
            fecha_alta_mes=c["mes"], fecha_alta_anio=1996, fecha_alta_dow=0,
        )
        for orden, (desc, precio, peso, tiempo, km) in enumerate(
            [
                ("Moto", 200 + c["id_cliente"] * 20, 0, 18, 40),
                ("Coche", 425 + c["id_cliente"] * 20, 20, 20, 45),
            ],
            start=1,
        ):
            insert(
                con, "cliente_tarifa", id_cliente=c["id_cliente"], orden=orden,
                descripcion=desc, precio=precio, ex_peso=peso,
                ex_tiempo=tiempo, ex_km=km,
            )

    # --- albaranes --------------------------------------------------------
    albaranes = [
        (1001, "A", 1, 5, 3, "P", 1),
        (1002, "A", 2, 8, 3, "D", 0),
        (1003, "B", 1, 12, 4, "P", 1),
        (1004, "B", 3, 2, 5, "D", 0),
    ]
    for num, letra, id_cliente, dia, mes, portes, facturado in albaranes:
        telefono = next(c["telefono"] for c in clientes if c["id_cliente"] == id_cliente)
        insert(
            con, "albaran", num_albaran=num, letra=letra, id_cliente=id_cliente,
            telefono=telefono, fecha_dia=dia, fecha_mes=mes, fecha_anio=1996,
            fecha_dow=0, portes=portes, facturado=facturado, obs="",
        )

    casillas = {
        (1001, "A"): [
            (1, 1, 0, 2, 12, "8c", "Almacen Central", "Calle Real 1", "10:30", 1, 0),
            (2, 2, 1, 0, 0, "5m", "Sr. Gomez", "Avda. del Mar 22", "11:00", 1, 5000),
        ],
        (1002, "A"): [
            (1, 3, 0, 0, 0, "", "Taller Rey", "Poligono Norte", "09:15", 1, 0),
        ],
        (1003, "B"): [
            (1, 1, 1, 1, 0, "12c", "Panaderia Central", "Plaza Mayor 3", "12:00", 1, 0),
            (2, 2, 0, 0, 0, "3m", "Sr. Lopez", "Ronda Oeste 8", "12:30", 0, 0),
        ],
        (1004, "B"): [
            (1, 3, 2, 5, 20, "40c", "Concesionaria", "Carretera N-550 km 7", "08:00", 1, 0),
        ],
    }
    for (num, letra), filas in casillas.items():
        for i, (mens, sc, sm, peso, tiempo, km, nombre, dir, hora, fact, reemb) in enumerate(
            filas, start=1
        ):
            insert(
                con, "albaran_casilla", num_albaran=num, letra=letra, casilla=i,
                cod_mensajero=mens, serv_cliente=sc, serv_mensajero=sm,
                ex_peso=peso, ex_tiempo=tiempo, ex_km=km, nombre=nombre,
                direccion=dir, hora=hora, facturar=fact, reembolso=reemb,
            )

    # --- facturas ---------------------------------------------------------
    facturas = [
        dict(num=1, letra="A", cli=1, dia=20, mes=4, pagado=1, tipo="Recibio",
             p_dia=25, p_mes=4, p_anio=1996, bruto=3250, dto=325, iva=468,
             recargo=19, neto=3412, obs=""),
        dict(num=2, letra="A", cli=2, dia=30, mes=4, pagado=0, tipo="",
             p_dia=0, p_mes=0, p_anio=0, bruto=500, dto=0, iva=80,
             recargo=0, neto=580, obs="Pendiente de cobro"),
    ]
    for f in facturas:
        telefono = next(c["telefono"] for c in clientes if c["id_cliente"] == f["cli"])
        insert(
            con, "factura", num_factura=f["num"], letra=f["letra"],
            id_cliente=f["cli"], telefono=telefono, fecha_dia=f["dia"],
            fecha_mes=f["mes"], fecha_anio=1996, fecha_dow=0, pagado=f["pagado"],
            tipo_pago=f["tipo"], fecha_pago_dia=f["p_dia"], fecha_pago_mes=f["p_mes"],
            fecha_pago_anio=f["p_anio"], iva_porcentaje=16.0, descuento_porc=10,
            total_bruto=f["bruto"], total_descuento=f["dto"], total_iva=f["iva"],
            total_recargo_eq=f["recargo"], total_neto=f["neto"], obs=f["obs"],
            ini_linea=0,
        )

    lineas = {
        (1, "A"): [(1, 1001, "A", 5, 3, 1, 1250), (2, 1003, "B", 12, 4, 2, 2000)],
        (2, "A"): [(1, 1002, "A", 8, 3, 1, 500)],
    }
    for (num, letra), filas in lineas.items():
        for linea, alb, alb_letra, dia, mes, cant, subtotal in filas:
            counts = [0] * 9
            counts[cant - 1] = 1
            insert(
                con, "factura_linea", num_factura=num, letra=letra, linea=linea,
                num_albaran=alb, letra_alb=alb_letra, fecha_dia=dia, fecha_mes=mes,
                fecha_anio=1996,
                **{f"cant_serv_{i + 1}": counts[i] for i in range(9)},
                subtotal=subtotal,
            )

    # --- estadisticas y archivo ------------------------------------------
    ingresos = {1: 12000, 2: 14300, 3: 17850, 4: 19300, 5: 15600}
    for mes, ingresos_mes in ingresos.items():
        insert(
            con, "estadistica_mensual", anio=1996, mes=mes, dia=28, dow=0,
            num_clientes=2 + mes, clientes_nuevos=1 if mes % 2 else 0,
            clientes_comercial_1=1 if mes < 3 else 2,
            clientes_comercial_2=1 if mes >= 3 else 0,
            ingresos=ingresos_mes,
        )

    insert(con, "albaran_archivado", disco=1, num_albaran=900, letra="A",
           fecha_ndx=19970115, pos=1)
    insert(con, "albaran_archivado", disco=1, num_albaran=901, letra="A",
           fecha_ndx=19970118, pos=2)

    con.commit()
    con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Datos de demostracion para el editor.")
    parser.add_argument(
        "--db",
        type=Path,
        default=ROOT / "bbdd.demo.sqlite",
        help="Fichero SQLite de destino (por defecto bbdd.demo.sqlite).",
    )
    args = parser.parse_args()

    if args.db.exists():
        args.db.unlink()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    seed(args.db)
    print(f"Base de demostracion creada: {args.db}")
    print(f"Arranca el editor con:  uv run mensages-web --db {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
