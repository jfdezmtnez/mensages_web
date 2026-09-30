"""Generador de datos de demostracion para el esquema MensaGes.

    uv run python scripts/demo_data.py                  # rellena ../bbdd.sqlite
    uv run python scripts/demo_data.py --db otra.sqlite

Los datos no son aleatorios sin mas: se generan aplicando las mismas reglas
que el programa original (FORMULAS.PAS y FACTURAS.PAS), de modo que las cifras
cuadran entre si:

* el subtotal de cada albaran se calcula con ``calcular_albaran``, usando las
  tarifas del cliente y los puntos por km de la configuracion;
* la factura de un cliente recoge solo albaranes suyos y aun no facturados, y
  sus totales salen de ``total_albaran_cliente`` (descuento, IVA, recargo de
  equivalencia y neto);
* el flag ``albaran.facturado`` marca exactamente los albaranes que aparecen
  en alguna linea de factura;
* las estadisticas mensuales se reconstruyen a partir de las altas de cliente y
  de las facturas emitidas ese mes;
* las claves foraneas y los rangos de los CHECK del esquema se respetan.

Es determinista: con la misma semilla sale siempre el mismo contenido.
"""

from __future__ import annotations

import argparse
import math
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
SCHEMA = REPO / "schema.sql"

ANIO = 1996
MESES_CORTOS = ("ENE", "FEB", "MAR", "ABR", "MAY", "JUN",
                "JUL", "AGO", "SEP", "OCT", "NOV", "DIC")
DIAS_MES = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)  # 1996 bisiesto


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #


def rnd(x: float) -> int:
    """round() de Pascal: mitad hacia el infinito, no al par como Python."""
    return math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)


def dow(dia: date) -> int:
    """Dia de la semana como lo devolvia getdate del DOS (domingo = 0)."""
    return (dia.weekday() + 1) % 7


def nd(fecha: date) -> int:
    """Fecha como entero AAAAMMDD de dos digitos, el formato de fecha.ndx."""
    return (fecha.year % 100) * 10000 + fecha.month * 100 + fecha.day


def parsear_km(texto: str) -> tuple[int, str]:
    """Separa "12c" en (12, "c"), como haria el val() del Pascal.

    El codigo original leia los digitos iniciales y luego miraba el caracter
    siguiente para saber si el envio iba en coche o en moto.
    """
    digitos = ""
    for ch in texto.strip():
        if ch.isdigit():
            digitos += ch
        else:
            break
    resto = texto.strip()[len(digitos):].strip().lower()
    return int(digitos or 0), (resto[0] if resto else "")


def ins(con: sqlite3.Connection, tabla: str, **valores) -> None:
    columnas = list(valores)
    con.execute(
        f"INSERT INTO {tabla} ({', '.join(columnas)})"
        f" VALUES ({', '.join('?' * len(columnas))})",
        [valores[c] for c in columnas],
    )


# --------------------------------------------------------------------------- #
# Catálogos
# --------------------------------------------------------------------------- #

APELLIDOS = (
    "Rodríguez", "Fernández", "González", "Vázquez", "Vigo", "Castro", "Pérez",
    "Suárez", "Álvarez", "Santos", "Moure", "Itoiz", "Garrido", "Lorenzo",
    "Salgado", "Cameselle", "Bautista", "Dominguez", "Iglesias", "Pastrana",
    "Sobrino", "Yáñez", "Cabral", "Rego", "Nogueiras", "Barbeito", "Ares",
    "Sande", "Lago", "Frobe", "Cifuentes", "Beiro", "Teijeiro",
)

NOMBRES = (
    "José", "Manuel", "José Luis", "Xosé", "Mª José", "Ángel", "Carlos",
    "Antón", "Suso", "Bea", "Pilar", "Lourdes", "Marta", "Nuria", "Rosa",
    "Ana", "Verónica", "Sonia", "Santi", "Rubén", "Brais", "Iván", "Óscar",
    "Diego", "Moisés", "Ramón", "Chus", "Gervasio",
)

PREFIJOS_EMPRESA = (
    "Distribuciones", "Talleres", "Panadería", "Concesionaria", "Almacenes",
    "Cafetería", "Restaurante", "Farmacia", "Óptica", "Librería",
    "Ferretería", "Cerrajería", "Muebles", "Textil", "Alimentación",
    "Frutería", "Pastelería", "Estación de servicio", "Clínica", "Laboratorio",
    "Imprenta", "Carpintería", "Peluquería", "Joyería", "Floristería",
    "Papelería", "Heladería", "Hostal", "Bar", "Joyas", "Bicicletas",
    "Motos", "Pescadería", "Comestibles",
)

SFIJOS_EMPRESA = (
    "del Faro S.L.", "Rey S.A.", "del Centro", "Norte", "Sur", "Viejo",
    "Nuevo", "Galicia", "Atlántico", "Rías", "Do Miño", "del Puerto", "Río",
    "de la Avenida", "Principal", "del Valle", "Mayor", "Hermandad",
)

CALLES = (
    "Ronda da Orense", "Avenida da Atlántida", "Rúa do Príncipe", "Calle Real",
    "Avenida de Madrid", "Rúa da Paz", "Travesía do Castro",
    "Rúa García Barbón", "Calle Diagonal", "Rúa do Areal",
    "Avenida de Castelao", "Rúa Urzaíz", "Rúa Exports", "Rúa Manuel Quiroga",
)

POBLACIONES = (
    ("Vigo", "Pontevedra", 36200), ("Vigo", "Pontevedra", 36300),
    ("A Coruña", "A Coruña", 15001), ("Ourense", "Ourense", 32001),
    ("Pontevedra", "Pontevedra", 36001),
    ("Santiago de Compostela", "A Coruña", 15701),
    ("Redondela", "Pontevedra", 36140), ("Cangas", "Pontevedra", 36200),
    ("Nigrán", "Pontevedra", 36350), ("As Neves", "Pontevedra", 36122),
    ("Moaña", "Pontevedra", 36270), ("Teis", "Pontevedra", 36152),
    ("Chapela", "Pontevedra", 36320), ("Vilagarcía de Arousa", "Pontevedra", 36600),
)

ESTUDIOS = ("FP", "BUP", "Licenciatura", "Master", "", "", "")

# Sin I, O, Ñ ni S: las claves de una sociedad no las llevan (BOE).
LETRAS_CIF = ("A", "B", "C", "D", "E", "F", "G", "H", "J", "L", "M", "N",
              "P", "Q", "R", "T", "U", "V", "W")

EXPERIENCIA = (
    "Repartidor 3 años en agencia", "Jefa de almacén", "Taxista desde 1989",
    "Comercial de alimentación", "Sin experiencia previa", "",
    "Mecánico y reparto", "Administrativa de comercio",
)

OBSERVACIONES_CLIENTE = (
    "", "", "", "Entregar en horario de mañana", "Avisar antes de llegar",
    "No llamar por teléfono, solo fax", "Cliente del centro comercial",
    "Paga siempre al contado", "", "Entrega en la puerta de atrás",
)

OBSERVACIONES_ALBARAN = (
    "", "", "", "", "",
    "Recogida en el almacen del cliente",
    "Entrega urgente, antes de las 10:00",
    "Pendiente de confirmar el destinatario",
    "Repetir la entrega tras el cierre",
    "Entrega en la puerta de vehiculos",
    "El destinatario no estaba",
)

# La columna forma_pago es VARCHAR(20), como el string[20] del Pascal
FORMAS_PAGO = (
    ("Contado", 0),
    ("Recibo bancario", 30),
    ("Transf. a 30 días", 30),
    ("Transf. a 60 días", 60),
    ("Recibo a 15 días", 15),
    ("Pagaré a 90 días", 90),
)

# Reparto realista por tipo de servicio: casi todo son recogidas en moto o
# coche dentro de la ciudad, y los servicios nacionales quedan para el Final.
# Los indices de esta lista son los numeros de cliente_tarifa (1..9).
SERVICIOS = (1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 4, 4, 4, 5, 5, 6, 6, 7, 7, 8)


# --------------------------------------------------------------------------- #
# Configuración y catálogos fijos
# --------------------------------------------------------------------------- #

# Valores por defecto que sembraba INSTALAR.PAS
TARIFAS_DEFECTO_CLIENTE = (
    (1, "Moto", 200, 0, 18, 40),
    (2, "Coche", 425, 20, 20, 45),
    (3, "Po-Express", 450, 30, 0, 0),
    (4, "S. Regular", 400, 30, 0, 0),
    (5, "Reg. Cap.", 1000, 40, 0, 0),
    (6, "Reg. Pob.", 1300, 40, 0, 0),
    (7, "Nac. Cap.", 1350, 975, 0, 0),
    (8, "Nac. Pob.", 1800, 975, 0, 0),
    (9, "S. Especial", 0, 0, 0, 0),
)

TARIFAS_DEFECTO_MENSAJERO = (
    (1, "Moto", 100, 0, 9, 20),
    (2, "Coche", 225, 10, 10, 22),
    (3, 'Serv. "75"', 75, 0, 0, 0),
    (4, "", 0, 0, 0, 0),
    (5, "", 0, 0, 0, 0),
    (6, "", 0, 0, 0, 0),
    (7, "", 0, 0, 0, 0),
    (8, "", 0, 0, 0, 0),
)

LLAVE = (172, 169, 176, 176, 173, 167, 179, 178, 173, 165)

RUTA = "C:\\MENSAGES\\"
IVA_PORCENTAJE = 16.0
PTS_KM_COCHE = 45
PTS_KM_MOTO = 40
RECARGO_EQUIVALENCIA = 0.04  # 4% sobre el IVA (FORMULAS.PAS)
PORC_REEMBOLSO = 0.03        # 3% del importe a reembolsar

#: Cuanto trafico se genera. Las dos variantes cortas existen para que las
#: pruebas tengan una base diminuta y estable en vez de depender de las cifras
#: del ano entero.
TRAFICO_COMPLETO = "completo"
TRAFICO_MINIMO = "minimo"    # un albaran con una casilla: basta para probar FKs
TRAFIGO_NINGUNO = "ninguno"


# --------------------------------------------------------------------------- #
# Modelo en memoria
# --------------------------------------------------------------------------- #


class Demo:
    """Acumula los datos generados y los vuelca en la base de datos."""

    def __init__(
        self,
        con: sqlite3.Connection,
        semilla: int = 19960101,
        *,
        clientes: int = 40,
        mensajeros: int = 12,
        trafico: str = TRAFICO_COMPLETO,
    ):
        self.con = con
        self.rnd = random.Random(semilla)
        self.iva = IVA_PORCENTAJE
        self.pts_km = {"c": PTS_KM_COCHE, "m": PTS_KM_MOTO}
        self.n_clientes = clientes
        self.n_mensajeros = mensajeros
        self.trafico = trafico

        self.comerciales: list[dict] = []
        self.mensajeros: list[dict] = []
        self.clientes: list[dict] = []
        self.albaranes: list[dict] = []
        self.casillas: list[dict] = []
        self.facturas: list[dict] = []
        self.lineas: list[dict] = []
        self.ingresos_mes = [0] * 12

    # -- utilidades de aleatoriedad ------------------------------------- #

    def elegir(self, *opciones):
        return self.rnd.choice(opciones)

    def entre(self, a: int, b: int) -> int:
        return self.rnd.randint(a, b)

    def nombre_persona(self) -> str:
        return f"{self.elegir(*NOMBRES)} {self.elegir(*APELLIDOS)} {self.elegir(*APELLIDOS)}"

    def direccion(self) -> dict:
        localidad, provincia, cp = self.elegir(*POBLACIONES)
        return {
            "dir_calle": self.elegir(*CALLES),
            "dir_numero": self.entre(1, 180),
            "dir_piso": self.elegir(0, 0, 0, 1, 2, 3, 4),
            "dir_letra": self.elegir("", "", "", "A", "B", "C", "D"),
            "dir_cpostal": cp + self.entre(0, 60),
            "dir_localidad": localidad,
            "dir_provincia": provincia,
        }

    def cif(self) -> str:
        return f"{self.entre(10000000, 99999999)}{self.elegir(*LETRAS_CIF)}"

    # -- albedo de las tablas base ------------------------------------- #

    def _semilla_config(self) -> None:
        ins(
            self.con, "config",
            id_config=1, iva_porcentaje=self.iva,
            pts_km_coche=PTS_KM_COCHE, pts_km_moto=PTS_KM_MOTO,
            ruta_trabajo=RUTA, permit=1, fecha_prueba=99999999,
            ingreso_mes=0, ultimo_mes_fact="", ultimo_num_factura=0,
            ultimo_disco=1, disco_nuevo=0,
        )
        ins(self.con, "instalacion", id_instalacion=1, ruta=RUTA, codigo=39580626)
        for pos, valor in enumerate(LLAVE, start=1):
            ins(self.con, "licencia_clave", posicion=pos, valor=valor)
        for t in TARIFAS_DEFECTO_CLIENTE:
            ins(self.con, "tarifa_defecto_cliente", orden=t[0], descripcion=t[1],
                precio=t[2], ex_peso=t[3], ex_tiempo=t[4], ex_km=t[5])
        for t in TARIFAS_DEFECTO_MENSAJERO:
            ins(self.con, "tarifa_defecto_mensajero", orden=t[0], descripcion=t[1],
                precio=t[2], ex_peso=t[3], ex_tiempo=t[4], ex_km=t[5])

    def _cargar_comerciales_existentes(self) -> list[dict]:
        con = self.con
        con.row_factory = sqlite3.Row
        filas = [dict(r) for r in con.execute("select * from comercial order by codigo")]
        con.row_factory = None
        return filas

    def _crear_comerciales(self) -> None:
        """Respeta los comerciales que ya hubiera y añade los de la demo.

        Los comerciales reales del usuario no se tocan: si ya hay alguno, se
        reutilizan como plantilla y la demo se limita a completar la plantilla
        hasta tener tres, que es lo que usa la distribucion de clientes.
        """
        existentes = self._cargar_comerciales_existentes()
        self.comerciales = existentes
        siguiente = max((c["codigo"] for c in existentes), default=0) + 1

        if not self.comerciales:
            for codigo, nombre, porcentaje in (
                (1, "Ana Rois Zhang", 10),
                (2, "Luis Moure Vidal", 5),
                (3, "Marta Prado Lemos", 7),
            ):
                self.comerciales.append(
                    self._nuevo_comercial(codigo, nombre, porcentaje)
                )
                siguiente = codigo + 1

        plantilla = ("Susana Fiel Taboas", "Rubén Amoedo Gil", "Nuria Camiño Rey")
        i = 0
        while len(self.comerciales) < 3:
            self.comerciales.append(
                self._nuevo_comercial(siguiente, plantilla[i % len(plantilla)],
                                      self.elegir(5, 7, 10, 15))
            )
            siguiente += 1
            i += 1

    def _nuevo_comercial(self, codigo: int, nombre: str, porcentaje: int) -> dict:
        d = self.direccion()
        c = {
            "codigo": codigo,
            "nombre": nombre,
            "cif": self.cif(),
            "porcentaje": porcentaje,
            "telefono": 986000000 + self.entre(1, 999999),
            "estudios": self.elegir(*ESTUDIOS),
            "experiencia_laboral": self.elegir(*EXPERIENCIA),
            "obs": self.elegir("", "", "Cobertura de la comarca del Morrazo"),
        }
        ins(self.con, "comercial", **c, **d)
        return c

    def _crear_mensajeros(self, cuantos: int | None = None) -> None:
        for codigo in range(1, (self.n_mensajeros if cuantos is None else cuantos) + 1):
            nombre = self.nombre_persona()
            d = self.direccion()
            m = {
                "codigo": codigo,
                "nombre": nombre,
                "cif": self.cif(),
                "telefono": 600000000 + self.entre(10000, 99999),
                "estado_civil": self.entre(0, 1),
                "servicio_militar": self.entre(0, 1),
                # Reparto de vehiculos: bastante mas de motos que coches
                "vehiculo": self.elegir("m", "c", "m", "m", "c"),
                "obs": self.elegir("", "", "Reparto por la mañana",
                                   "Disponible solo a partir de las 16:00"),
            }
            ins(self.con, "mensajero", **m, **d)
            self.mensajeros.append(m)

    def _crear_clientes(self, cuantos: int | None = None) -> None:
        total = self.n_clientes if cuantos is None else cuantos
        usados = set()
        for i in range(1, total + 1):
            while True:
                nombre = f"{self.elegir(*PREFIJOS_EMPRESA)} {self.elegir(*SFIJOS_EMPRESA)}"
                if nombre not in usados:
                    usados.add(nombre)
                    break

            d = self.direccion()
            # Los clientes se dan de alta a lo largo del año (y algunos en 1995)
            if i <= 10:
                alta = date(1995, self.entre(1, 12), self.entre(1, 28))
            else:
                alta = date(ANIO, self.entre(1, 11), self.entre(1, 28))
            forma_pago, plazo = self.elegir(*FORMAS_PAGO)

            c = {
                "id_cliente": i,
                "telefono": 986100000 + self.entre(1, 899999),
                "nombre": nombre,
                "cif": self.cif(),
                "forma_pago": forma_pago,
                "cod_comercial": self.comerciales[i % len(self.comerciales)]["codigo"],
                "descuento": self.elegir(0, 0, 0, 5, 5, 10, 10, 15),
                "recargo_equivalencia": self.entre(0, 1),
                "cobrar_reembolso": self.elegir(0, 0, 0, 1),
                "obs": self.elegir(*OBSERVACIONES_CLIENTE),
                "fecha_alta_dia": alta.day,
                "fecha_alta_mes": alta.month,
                "fecha_alta_anio": alta.year,
                "fecha_alta_dow": dow(alta),
                "plazo_pago": plazo,
                "tarifas": [],
            }
            ins(self.con, "cliente", **{k: v for k, v in c.items() if k != "tarifas"
                                        and k != "plazo_pago"}, **d)
            self.clientes.append(c)
            self._crear_tarifas_cliente(c)

    def _crear_tarifas_cliente(self, cliente: dict) -> None:
        """Copia las tarifas por defecto y las personaliza un poco.

        Igual que hace la aplicacion al dar de alta un cliente: se copian los
        valores de MENSAGES.CFG y luego el usuario los ajusta.
        """
        for orden, desc, precio, ex_peso, ex_tiempo, ex_km in TARIFAS_DEFECTO_CLIENTE:
            if precio:
                # +-15% segun el cliente, redondeado a 5 pesetas
                factor = self.rnd.uniform(0.85, 1.15)
                precio = int(rnd(precio * factor / 5) * 5)
                ex_peso = int(rnd(ex_peso * self.rnd.uniform(0.8, 1.2) / 5) * 5)
                ex_tiempo = int(rnd(ex_tiempo * self.rnd.uniform(0.8, 1.2) / 5) * 5)
                ex_km = int(rnd(ex_km * self.rnd.uniform(0.8, 1.2) / 5) * 5)
            cliente["tarifas"].append(
                {"orden": orden, "descripcion": desc, "precio": precio,
                 "ex_peso": ex_peso, "ex_tiempo": ex_tiempo, "ex_km": ex_km}
            )
            ins(
                self.con, "cliente_tarifa", id_cliente=cliente["id_cliente"],
                orden=orden, descripcion=desc, precio=precio,
                ex_peso=ex_peso, ex_tiempo=ex_tiempo, ex_km=ex_km,
            )

    # -- trafico de albaranes ------------------------------------------ #

    def _crear_albaranes(self) -> None:
        """Un año de trafico: cada cliente activo genera albaranes cada mes."""
        if self.trafico == TRAFIGO_NINGUNO:
            return
        if self.trafico == TRAFICO_MINIMO:
            # Lo justo para que haya una clave foranea viva que probar: un
            # albaran del primer cliente con una casilla del mensajero 1.
            self._crear_albaran_minimo()
            return

        num = 1000
        for mes in range(1, 13):
            for cliente in self.clientes:
                if cliente["fecha_alta_anio"] == ANIO and mes < cliente["fecha_alta_mes"]:
                    continue
                # Los clientes pequenos facturan de vez en cuando
                if self.rnd.random() > 0.8:
                    continue
                for _ in range(self.entre(1, 4)):
                    num += 1
                    self._crear_albaran(cliente, mes, num)

    def _crear_albaran_minimo(self) -> None:
        cliente = self.clientes[0]
        albaran = {
            "num_albaran": 1001, "letra": "A",
            "id_cliente": cliente["id_cliente"], "telefono": cliente["telefono"],
            "fecha_dia": 3, "fecha_mes": 1, "fecha_anio": ANIO, "fecha_dow": 4,
            "portes": "P", "facturado": 0, "obs": "", "cliente": cliente,
        }
        self.albaranes.append(albaran)
        self.casillas.append({
            "num_albaran": 1001, "letra": "A", "casilla": 1,
            "cod_mensajero": 1, "serv_cliente": 1, "serv_mensajero": 1,
            "ex_peso": 10, "ex_tiempo": 0, "ex_km": "12c",
            "nombre": "Destinatario de prueba", "direccion": "Rúa da Paz, 1",
            "hora": "10:00", "facturar": 1, "reembolso": 0,
        })

    def _crear_albaran(self, cliente: dict, mes: int, num: int) -> None:
        dia = self.entre(1, DIAS_MES[mes - 1])
        fecha = date(ANIO, mes, dia)
        # El original alternaba A y B en el codigo de albaran
        letra = "A" if num % 2 else "B"
        albaran = {
            "num_albaran": num,
            "letra": letra,
            "id_cliente": cliente["id_cliente"],
            "telefono": cliente["telefono"],
            "fecha_dia": dia,
            "fecha_mes": mes,
            "fecha_anio": ANIO,
            "fecha_dow": dow(fecha),
            "portes": self.elegir("P", "P", "P", "D"),
            "facturado": 0,
            "obs": self.elegir(*OBSERVACIONES_ALBARAN),
            "cliente": cliente,
        }
        self.albaranes.append(albaran)
        for casilla in range(1, self.entre(1, 4) + 1):
            self._crear_casilla(albaran, casilla)

    def _crear_casilla(self, albaran: dict, casilla: int) -> None:
        cliente = albaran["cliente"]
        mensajero = self.mensajeros[self.rnd.randrange(len(self.mensajeros))]
        # Un 20% de los envios se cobra solo por kilometraje (tarifa 0)
        solo_km = self.rnd.random() < 0.2
        serv_cliente = 0 if solo_km else self.elegir(*SERVICIOS)
        facturar = 0 if self.rnd.random() < 0.08 else 1

        if solo_km:
            # Sin tarifa del cliente: solo km, con sufijo de vehiculo
            km = self.entre(2, 60)
            ex_km = f"{km}{'c' if mensajero['vehiculo'] == 'c' else 'm'}"
            ex_peso = 0
            ex_tiempo = 0
        else:
            km = self.entre(1, 40)
            ex_km = f"{km}{'c' if self.rnd.random() < 0.5 else 'm'}"
            ex_peso = self.entre(0, 60)
            ex_tiempo = self.entre(0, 20)

        reembolso = 0
        if cliente["cobrar_reembolso"] and facturar and self.rnd.random() < 0.4:
            reembolso = self.elegir(0, 5000, 10000, 15000, 25000, 50000, 120000)

        self.casillas.append({
            "num_albaran": albaran["num_albaran"],
            "letra": albaran["letra"],
            "casilla": casilla,
            "cod_mensajero": mensajero["codigo"],
            "serv_cliente": serv_cliente,
            "serv_mensajero": self.entre(1, 3) if mensajero["vehiculo"] == "c" else self.entre(1, 2),
            "ex_peso": ex_peso,
            "ex_tiempo": ex_tiempo,
            "ex_km": ex_km,
            "nombre": f"{self.elegir(*NOMBRES)} {self.elegir(*APELLIDOS)}",
            "direccion": f"{self.elegir(*CALLES)}, {self.entre(1, 120)}",
            "hora": f"{self.entre(8, 20):02d}:{self.elegir('00', '15', '30', '45')}",
            "facturar": facturar,
            "reembolso": reembolso,
        })

    # -- facturacion ----------------------------------------------------- #

    def subtotal_albaran(self, albaran: dict) -> tuple[int, list[int]]:
        """Replica calcular_albaran de FORMULAS.PAS.

        Devuelve (subtotal, unidades por tipo de servicio).

        El Pascal original asignaba subkm/subpeso/subtiempo en vez de
        acumularlos, de modo que un albaran con dos casillas del mismo tipo
        perdia parte del importe. Aqui se acumulan, que es lo que buscaba el
        codigo: el subtotal es la suma de lo que aporta cada casilla.
        """
        cliente = albaran["cliente"]
        tarifas = cliente["tarifas"]
        unidades = [0] * 9
        subtotal = 0

        for casilla in self.casillas_de(albaran):
            if not casilla["facturar"]:
                continue
            if casilla["serv_cliente"] != 0:
                k = casilla["serv_cliente"] - 1
                unidades[k] += 1
                tarifa = tarifas[k]
                km, _ = parsear_km(casilla["ex_km"])
                subtotal += tarifa["precio"]
                subtotal += km * tarifa["ex_km"]
                subtotal += casilla["ex_peso"] * tarifa["ex_peso"]
                subtotal += casilla["ex_tiempo"] * tarifa["ex_tiempo"]
                if cliente["cobrar_reembolso"]:
                    subtotal += rnd(casilla["reembolso"] * PORC_REEMBOLSO)
            else:
                # Solo kilometraje: el importe sale de los puntos por km de la
                # configuracion segun el vehiculo, que marca la letra final
                km, sufijo = parsear_km(casilla["ex_km"])
                subtotal += km * self.pts_km.get(sufijo or "c", PTS_KM_COCHE)
                if cliente["cobrar_reembolso"]:
                    subtotal += rnd(casilla["reembolso"] * PORC_REEMBOLSO)
        return subtotal, unidades

    def casillas_de(self, albaran: dict) -> list[dict]:
        return [c for c in self.casillas
                if c["num_albaran"] == albaran["num_albaran"]
                and c["letra"] == albaran["letra"]]

    def _crear_facturas(self) -> None:
        """Cada mes se factura a cada cliente lo que tego pendiente.

        Como en la aplicacion, los albaranes de un mes se facturan al mes
        siguiente (a veces con mas retraso) y solo si siguen sin facturar.
        """
        if self.trafico != TRAFICO_COMPLETO:
            return
        numero = 0
        for mes_factura in range(2, 13):
            for cliente in self.clientes:
                if cliente["fecha_alta_anio"] == ANIO and mes_factura < cliente["fecha_alta_mes"] + 1:
                    continue
                # Alrededor de un 15% se queda pendiente y lo vera el ano siguiente
                mes = mes_factura - 1
                if self.rnd.random() < 0.15:
                    continue
                pendientes = [
                    a for a in self.clientes_de(cliente)
                    if not a["facturado"] and a["fecha_mes"] == mes
                ]
                if not pendientes:
                    continue
                numero += 1
                self._emitir_factura(cliente, pendientes, numero, mes_factura)

    def clientes_de(self, cliente: dict) -> list[dict]:
        return [a for a in self.albaranes
                if a["id_cliente"] == cliente["id_cliente"]]

    def _emitir_factura(self, cliente: dict, albaranes: list[dict],
                        numero: int, mes_factura: int) -> None:
        dia = self.entre(1, 10)
        fecha = date(ANIO, mes_factura, dia)
        plazo = cliente["plazo_pago"]
        if plazo:
            pago = fecha + timedelta(days=plazo)
            pagado = pago <= date(ANIO, 12, 31)
        else:
            pago, pagado = fecha, 1

        # Se factura lo servido hasta el cierre del mes anterior, y solo lo que
        # tiene algo cobrable: los albaranes cuyas casillas estan todas
        # marcadas como "no facturar" (mercancia que no se cobra) se quedan
        # pendientes en lugar de ensuciar la factura con lineas a cero.
        corte = date(ANIO, mes_factura - 1, DIAS_MES[mes_factura - 2])
        subtotales = {
            (a["num_albaran"], a["letra"]): self.subtotal_albaran(a)[0]
            for a in albaranes
            if date(ANIO, a["fecha_mes"], a["fecha_dia"]) <= corte
        }
        facturables = [
            a for a in albaranes
            if subtotales.get((a["num_albaran"], a["letra"]), 0) > 0
        ]
        if not facturables:
            return

        bruto = 0
        lineas = []
        for linea, albaran in enumerate(facturables, start=1):
            subtotal, unidades = self.subtotal_albaran(albaran)
            bruto += subtotal
            albaran["facturado"] = 1
            lineas.append({
                "num_factura": numero, "letra": "A", "linea": linea,
                "num_albaran": albaran["num_albaran"],
                "letra_alb": albaran["letra"],
                "fecha_dia": albaran["fecha_dia"],
                "fecha_mes": albaran["fecha_mes"],
                "fecha_anio": albaran["fecha_anio"],
                "cantidades": unidades,
                "subtotal": subtotal,
            })

        descuento = rnd(bruto * cliente["descuento"] / 100)
        base = bruto - descuento
        iva = rnd(base * self.iva / 100)
        recargo = rnd(iva * RECARGO_EQUIVALENCIA) if cliente["recargo_equivalencia"] else 0
        neto = base + iva + recargo

        self.facturas.append({
            "num_factura": numero, "letra": "A",
            "id_cliente": cliente["id_cliente"],
            "telefono": cliente["telefono"],
            "fecha_dia": fecha.day, "fecha_mes": fecha.month,
            "fecha_anio": fecha.year, "fecha_dow": dow(fecha),
            "pagado": pagado, "tipo_pago": cliente["forma_pago"],
            "fecha_pago_dia": pago.day, "fecha_pago_mes": pago.month,
            "fecha_pago_anio": pago.year,
            "iva_porcentaje": self.iva, "descuento_porc": cliente["descuento"],
            "total_bruto": bruto, "total_descuento": descuento,
            "total_iva": iva, "total_recargo_eq": recargo, "total_neto": neto,
            "obs": self.elegir("", "", "", "Pendiente de revision"),
            "ini_linea": 0,
        })
        self.lineas.extend(lineas)
        self.ingresos_mes[mes_factura - 1] += bruto

    # -- estadisticas y archivo ------------------------------------------ #

    def _crear_estadisticas(self) -> None:
        """make_stats de STATS.PAS, reconstruido desde los datos reales."""
        for mes in range(1, 13):
            ultimo = date(ANIO, mes, DIAS_MES[mes - 1])
            activos = [c for c in self.clientes
                       if (c["fecha_alta_anio"], c["fecha_alta_mes"]) <= (ANIO, mes)]
            nuevos = [c for c in self.clientes
                      if c["fecha_alta_anio"] == ANIO and c["fecha_alta_mes"] == mes]
            por_comercial = [0] * 10
            for c in activos:
                codigo = c["cod_comercial"]
                if 1 <= codigo <= 10:
                    por_comercial[codigo - 1] += 1
            ins(
                self.con, "estadistica_mensual",
                anio=ANIO, mes=mes, dia=ultimo.day, dow=dow(ultimo),
                num_clientes=len(activos), clientes_nuevos=len(nuevos),
                ingresos=self.ingresos_mes[mes - 1],
                **{f"clientes_comercial_{i + 1}": por_comercial[i] for i in range(10)},
            )

    def _crear_archivados(self) -> None:
        """Albaranes de 1995, ya pasatiados a los disquetes de archivo."""
        num = 800
        for disco in (1, 2):
            for pos in range(1, self.entre(36, 49)):
                fecha = date(1995, self.entre(1, 12), self.entre(1, 28))
                num += 1
                ins(
                    self.con, "albaran_archivado", disco=disco,
                    num_albaran=num, letra="A" if num % 2 else "B",
                    fecha_ndx=nd(fecha), pos=pos,
                )

    # -- volcado ---------------------------------------------------------- #

    def volcar(self) -> None:
        con = self.con
        for a in self.albaranes:
            ins(
                con, "albaran", num_albaran=a["num_albaran"], letra=a["letra"],
                id_cliente=a["id_cliente"], telefono=a["telefono"],
                fecha_dia=a["fecha_dia"], fecha_mes=a["fecha_mes"],
                fecha_anio=a["fecha_anio"], fecha_dow=a["fecha_dow"],
                portes=a["portes"], facturado=a["facturado"], obs=a["obs"],
            )
        for c in self.casillas:
            ins(con, "albaran_casilla", **c)
        for f in self.facturas:
            ins(
                con, "factura", num_factura=f["num_factura"], letra=f["letra"],
                id_cliente=f["id_cliente"], telefono=f["telefono"],
                fecha_dia=f["fecha_dia"], fecha_mes=f["fecha_mes"],
                fecha_anio=f["fecha_anio"], fecha_dow=f["fecha_dow"],
                pagado=f["pagado"], tipo_pago=f["tipo_pago"],
                fecha_pago_dia=f["fecha_pago_dia"],
                fecha_pago_mes=f["fecha_pago_mes"],
                fecha_pago_anio=f["fecha_pago_anio"],
                iva_porcentaje=f["iva_porcentaje"],
                descuento_porc=f["descuento_porc"],
                total_bruto=f["total_bruto"],
                total_descuento=f["total_descuento"],
                total_iva=f["total_iva"], total_recargo_eq=f["total_recargo_eq"],
                total_neto=f["total_neto"], obs=f["obs"],
                ini_linea=f["ini_linea"],
            )
        for l in self.lineas:
            ins(
                con, "factura_linea", num_factura=l["num_factura"],
                letra=l["letra"], linea=l["linea"],
                num_albaran=l["num_albaran"], letra_alb=l["letra_alb"],
                fecha_dia=l["fecha_dia"], fecha_mes=l["fecha_mes"],
                fecha_anio=l["fecha_anio"],
                **{f"cant_serv_{i + 1}": l["cantidades"][i] for i in range(9)},
                subtotal=l["subtotal"],
            )

        # config: ultimo numero de factura, ingresos del mes y mes en curso
        ultima = self.facturas[-1] if self.facturas else None
        ingresos = sum(f["total_bruto"] for f in self.facturas
                       if f["fecha_mes"] == 12)
        con.execute(
            "update config set ultimo_num_factura = ?, ultimo_mes_fact = ?,"
            " ingreso_mes = ?",
            (ultima["num_factura"] if ultima else 0,
             f"{MESES_CORTOS[11]}{ANIO}", ingresos),
        )


# --------------------------------------------------------------------------- #
# Verificación de coherencia
# --------------------------------------------------------------------------- #


def verificar(con: sqlite3.Connection) -> list[str]:
    """Devuelve la lista de incoherencias encontradas (vacia si todo cuadra)."""
    fallos: list[str] = []

    def uno(consulta: str) -> int:
        return con.execute(consulta).fetchone()[0]

    # 1. Una sola fila en las tablas de configuracion
    for tabla in ("config", "instalacion"):
        if uno(f"select count(*) from {tabla}") != 1:
            fallos.append(f"{tabla} deberia tener exactamente 1 fila")

    # 2. La clave foranea de cada factura coincide con su cliente
    if uno("""
        select count(*) from factura f
        join cliente c on c.id_cliente = f.id_cliente
        where f.telefono <> c.telefono
    """):
        fallos.append("hay facturas cuyo telefono no es el de su cliente")

    # 3. Toda linea de factura pertenece a un albaran de ese mismo cliente
    if uno("""
        select count(*) from factura_linea l
        join factura f on f.num_factura = l.num_factura and f.letra = l.letra
        join albaran a on a.num_albaran = l.num_albaran and a.letra = l.letra_alb
        where a.id_cliente <> f.id_cliente
    """):
        fallos.append("hay lineas de factura que apuntan a albaranes de otro cliente")

    # 4. Un albaran no puede estar en dos facturas
    if uno("""
        select count(*) from (
            select num_albaran, letra_alb from factura_linea
            group by num_albaran, letra_alb having count(*) > 1
        )
    """):
        fallos.append("hay albaranes repetidos en varias facturas")

    # 5. facturado == 1 exactamente si el albaran esta en alguna linea
    if uno("""
        select count(*) from albaran a
        where a.facturado <> (
            select count(*) > 0 from factura_linea l
            where l.num_albaran = a.num_albaran and l.letra_alb = a.letra
        )
    """):
        fallos.append("el flag facturado no coincide con las lineas de factura")

    # 6. Los subtotales de las lineas suman el bruto de su factura
    if uno("""
        select count(*) from (
            select f.num_factura, f.letra, f.total_bruto,
                   (select sum(l.subtotal) from factura_linea l
                     where l.num_factura = f.num_factura and l.letra = f.letra) as suma
            from factura f
        ) where total_bruto <> suma
    """):
        fallos.append("el total bruto de alguna factura no es la suma de sus lineas")

    # 7. Los totales de cada factura salen de la formula del programa
    if uno("""
        select count(*) from factura
        where total_descuento <> cast(
                round((total_bruto * descuento_porc) / 100.0) as integer)
           or total_iva <> cast(
                round(((total_bruto - total_descuento) * iva_porcentaje) / 100.0) as integer)
           or total_neto <> total_bruto - total_descuento + total_iva + total_recargo_eq
    """):
        fallos.append("los totales de alguna factura no cuadran con la formula")

    # 8. El recargo de equivalencia solo existe si el cliente lo tiene
    if uno("""
        select count(*) from factura f
        join cliente c on c.id_cliente = f.id_cliente
        where f.total_recargo_eq > 0 and c.recargo_equivalencia = 0
    """):
        fallos.append("hay facturas con recargo de equivalencia en clientes que no lo tienen")

    # 9. Las casillas respetan los rangos del esquema
    if uno("select count(*) from albaran_casilla where casilla not between 1 and 8") \
            or uno("select count(*) from albaran_casilla where serv_cliente not between 0 and 9") \
            or uno("select count(*) from albaran_casilla where serv_mensajero not between 0 and 8"):
        fallos.append("hay casillas fuera de los rangos permitidos")

    # 10. Ningun cliente tiene mas de 8 casillas en un albaran
    if uno("""
        select count(*) from (
            select a.num_albaran, a.letra from albaran a
            join albaran_casilla c on c.num_albaran = a.num_albaran and c.letra = a.letra
            group by a.num_albaran, a.letra having count(*) > 8
        )
    """):
        fallos.append("hay albaranes con mas de 8 casillas")

    # 11. Las tarifas de cada cliente cubren 1..9
    if uno("""
        select count(*) from cliente c
        where (select count(*) from cliente_tarifa t where t.id_cliente = c.id_cliente) <> 9
    """):
        fallos.append("hay clientes que no tienen las 9 tarifas")

    # 12. Las unidades por tipo de servicio son las casillas facturables
    if uno("""
        select count(*) from factura_linea l
        where l.cant_serv_1 + l.cant_serv_2 + l.cant_serv_3 + l.cant_serv_4
            + l.cant_serv_5 + l.cant_serv_6 + l.cant_serv_7 + l.cant_serv_8
            + l.cant_serv_9 <> (
            select count(*) from albaran_casilla c
            where c.num_albaran = l.num_albaran and c.letra = l.letra_alb
              and c.facturar = 1 and c.serv_cliente between 1 and 9)
    """):
        fallos.append("las unidades por servicio no cuadran con las casillas del albaran")

    if uno("select count(*) from factura_linea where subtotal <= 0"):
        fallos.append("hay lineas de factura con importe cero")

    # 13. Los ingresos mensuales de las estadisticas cuadran con las facturas
    if uno("""
        select count(*) from estadistica_mensual e
        where e.ingresos <> coalesce((
            select sum(f.total_bruto) from factura f
            where f.fecha_anio = e.anio and f.fecha_mes = e.mes), 0)
    """):
        fallos.append("los ingresos de las estadisticas no cuadran con las facturas")

    # 14. Los clientes de cada estadistica son los activos ese mes
    if uno("""
        select count(*) from estadistica_mensual e
        where e.num_clientes <> (select count(*) from cliente c
              where (c.fecha_alta_anio, c.fecha_alta_mes) <= (e.anio, e.mes))
    """):
        fallos.append("el numero de clientes de las estadisticas no cuadra")

    # 15. Ningun comercial factura a clientes que no son suyos
    if uno("""
        select count(*) from factura f
        join cliente c on c.id_cliente = f.id_cliente
        where c.cod_comercial <> 0
          and c.cod_comercial not in (select codigo from comercial)
    """):
        fallos.append("hay clientes asignados a un comercial inexistente")

    fallos.extend(_verificar_subtotales(con))

    return fallos


def _verificar_subtotales(con: sqlite3.Connection) -> list[str]:
    """Recalcula cada subtotal desde la base de datos y lo compara.

    Es la comprobacion de fondo: aplica calcular_albaran otra vez, pero
    leyendo las casillas, las tarifas y la configuracion ya guardadas, en
    lugar de fiarse de los numeros que trae el generador.
    """
    config = con.execute(
        "select pts_km_coche, pts_km_moto from config"
    ).fetchone()
    if config is None:
        return ["falta la fila de configuracion"]

    tarifas = {
        (t[0], t[1]): t[2:]
        for t in con.execute(
            "select id_cliente, orden, precio, ex_peso, ex_tiempo, ex_km"
            " from cliente_tarifa"
        )
    }
    casillas: dict[tuple[int, str], list[tuple]] = {}
    for fila in con.execute(
        "select num_albaran, letra, facturar, serv_cliente, ex_peso,"
        " ex_tiempo, ex_km, reembolso from albaran_casilla"
    ):
        casillas.setdefault((fila[0], fila[1]), []).append(fila[2:])

    cabeceras = {
        (f[0], f[1]): (f[2], bool(f[3]))
        for f in con.execute(
            "select f.num_factura, f.letra, f.id_cliente, c.cobrar_reembolso"
            " from factura f join cliente c on c.id_cliente = f.id_cliente"
        )
    }

    descuadres = 0
    for num, letra, alb, letra_alb, subtotal in con.execute(
        "select num_factura, letra, num_albaran, letra_alb, subtotal"
        " from factura_linea"
    ):
        cabecera = cabeceras.get((num, letra))
        if cabecera is None:
            continue
        id_cliente, cobrar = cabecera
        esperado = 0
        for facturar, serv, peso, tiempo, km_txt, reemb in casillas.get((alb, letra_alb), []):
            if not facturar:
                continue
            km, sufijo = parsear_km(km_txt)
            if serv:
                precio, ex_peso, ex_tiempo, ex_km = tarifas[(id_cliente, serv)]
                esperado += precio + km * ex_km + peso * ex_peso + tiempo * ex_tiempo
            else:
                esperado += km * (config[0] if sufijo == "c" else config[1])
            if cobrar:
                esperado += rnd(reemb * PORC_REEMBOLSO)
        if esperado != subtotal:
            descuadres += 1

    if descuadres:
        return [f"{descuadres} lineas de factura tienen un subtotal que no "
                f"recalcula desde las casillas"]
    return []


# --------------------------------------------------------------------------- #
# Orquestación
# --------------------------------------------------------------------------- #


def rellenar(
    con: sqlite3.Connection,
    semilla: int = 19960101,
    *,
    clientes: int = 40,
    mensajeros: int = 12,
    trafico: str = TRAFICO_COMPLETO,
) -> Demo:
    """Genera el conjunto completo de datos de demostracion.

    ``trafico`` permite una base diminuta para las pruebas (``TRAFICO_MINIMO``
    deja un unico albaran, ``TRAFIGO_NINGUNO`` ninguno).
    """
    demo = Demo(con, semilla, clientes=clientes, mensajeros=mensajeros,
                trafico=trafico)
    demo._semilla_config()
    demo._crear_comerciales()
    demo._crear_mensajeros()
    demo._crear_clientes()
    demo._crear_albaranes()
    demo._crear_facturas()
    demo._crear_estadisticas()
    demo._crear_archivados()
    demo.volcar()
    con.commit()
    return demo


def abrir(db_path: Path) -> sqlite3.Connection:
    """Abre la base creando el esquema solo si aun no existe."""
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    tablas = con.execute(
        "select count(*) from sqlite_master where type = 'table'"
        " and name not like 'sqlite_%'"
    ).fetchone()[0]
    if not tablas:
        if not SCHEMA.is_file():
            raise SystemExit(f"No encuentro el esquema en {SCHEMA}")
        con.executescript(SCHEMA.read_text(encoding="utf-8"))
        con.commit()
    return con


TABLAS_GENERADAS = (
    "factura_linea", "factura", "albaran_casilla", "albaran",
    "estadistica_mensual", "albaran_archivado",
    "cliente_tarifa", "cliente", "mensajero",
    "tarifa_defecto_cliente", "tarifa_defecto_mensajero",
    "licencia_clave", "instalacion", "config",
)


def contar_filas(con: sqlite3.Connection) -> dict[str, int]:
    """Filas por tabla; omite las vacias."""
    total: dict[str, int] = {}
    for (tabla,) in con.execute(
        "select name from sqlite_master where type = 'table'"
        " and name not like 'sqlite_%' order by name"
    ):
        n = con.execute(f"select count(*) from [{tabla}]").fetchone()[0]
        if n:
            total[tabla] = n
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description="Datos de demostracion para MensaGes.")
    ap.add_argument("--db", type=Path, default=REPO / "bbdd.sqlite",
                    help="Base de datos a rellenar (por defecto ../bbdd.sqlite)")
    ap.add_argument("--semilla", type=int, default=19960101,
                    help="Semilla del generador; el mismo numero, el mismo contenido.")
    ap.add_argument("--forzar", action="store_true",
                    help="Rellenar aunque ya haya datos (se conservan los comerciales).")
    ap.add_argument("--todo", action="store_true",
                    help="Con --forzar, regenerar tambien los comerciales.")
    ap.add_argument("--verificar", action="store_true",
                    help="No genera nada: solo comprueba la coherencia de la base.")
    args = ap.parse_args()

    db_path = args.db.resolve()
    con = abrir(db_path)
    try:
        if args.verificar:
            filas = contar_filas(con)
            print(f"Base comprobada: {db_path}")
            for tabla, n in filas.items():
                print(f"  {tabla:<24} {n:>7}")
            if not filas:
                print("  (vacia)")
            fallos = verificar(con)
            return _informe(fallos)

        previas = contar_filas(con)
        if not args.forzar and not previas:
            print("La base estaba vacia: se rellena sin necesidad de --forzar.")
        elif not args.forzar:
            print(f"La base {db_path.name} ya contiene datos:")
            for tabla, n in previas.items():
                print(f"    {tabla:<24} {n}")
            print("\nIndica --forzar para rellenarla de todos modos. Se conservaran "
                  "los comerciales que ya haya; el resto se regenera.")
            return 1
        elif not args.todo:
            print(f"La base {db_path.name} ya contiene datos; se regeneran las "
                  "tablas de la demo y se conservan los comerciales.")

        # Para poder relanzar el script sin duplicar nada, se vacia lo que va
        # a generarse. Los comerciales quedan intactos salvo con --todo.
        con.execute("PRAGMA foreign_keys = OFF")
        for tabla in TABLAS_GENERADAS:
            con.execute(f"delete from {tabla}")
        if args.todo:
            con.execute("delete from comercial")
        con.execute("PRAGMA foreign_keys = ON")
        con.commit()

        demo = rellenar(con, args.semilla)
        fallos = verificar(con)
    finally:
        con.close()

    print(f"Base rellenada: {db_path}")
    print(f"  comerciales   {len(demo.comerciales):>6}")
    print(f"  mensajeros    {len(demo.mensajeros):>6}")
    print(f"  clientes      {len(demo.clientes):>6}")
    print(f"  albaranes     {len(demo.albaranes):>6}")
    print(f"  casillas      {len(demo.casillas):>6}")
    print(f"  facturas      {len(demo.facturas):>6}")
    print(f"  lineas fact.  {len(demo.lineas):>6}")
    print(f"  importe facturado: {sum(f['total_neto'] for f in demo.facturas):,} pts")

    return _informe(fallos)


def _informe(fallos: list[str]) -> int:
    if fallos:
        print("\nINCOHERENCIAS DETECTADAS:")
        for fallo in fallos:
            print("  -", fallo)
        return 1
    print("\nCoherencia verificada: todas las comprobaciones pasan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
