# MensaGes · editor web de `bbdd.sqlite`

Aplicación web local (**Dash + AG Grid**, vía `dash_ag_grid`) para consultar,
crear, editar y borrar las 15 tablas del esquema MensaGes desde una rejilla.

El esquema se **introspecciona en tiempo de ejecución** desde `sqlite_master` y
`PRAGMA table_info`: no hay ni una tabla ni una columna escrita a mano, así que
las columnas, los editores, las claves primarias y las restricciones se adaptan
solos al DDL.

`../bbdd.sqlite` viene relleno con un año de actividad de una agencia de
mensajería para poder probar la aplicación con contenido de verdad: 40 clientes,
12 mensajeros, ~640 albaranes con sus casillas, ~180 facturas y las estadísticas
mes a mes, todo cuadrado entre sí (ver *Datos de demostración* más abajo).

## Puesta en marcha

```bash
cd web
uv sync
uv run mensages-web
```

Y abrir <http://127.0.0.1:8000/>.

La base se busca por este orden:

1. variable de entorno `MENSAGES_DB`
2. `../bbdd.sqlite` (raíz del repositorio)
3. `bbdd.sqlite` (dentro de `web/`)

Otras opciones:

```bash
uv run mensages-web --db ../bbdd.sqlite --port 9000 --host 127.0.0.1
uv run mensages-web --debug          # recarga al guardar
```

## Datos de demostración

`../bbdd.sqlite` viene ya relleno con un año entero de actividad de una agencia
de mensajería (1996): 40 clientes, 12 mensajeros, ~640 albaranes con sus
casillas, ~180 facturas y las estadísticas mes a mes. Los números no son de
adorno: están calculados con las mismas fórmulas del programa original.

```bash
uv run python scripts/demo_data.py             # rellena ../bbdd.sqlite
uv run python scripts/demo_data.py --verificar  # solo comprueba la coherencia
uv run python scripts/demo_data.py --db ../bbdd.demo.sqlite --forzar
```

| Opción | |
|---|---|
| `--db RUTA` | base a rellenar (por defecto `../bbdd.sqlite`) |
| `--semilla N` | con la misma semilla sale siempre el mismo contenido |
| `--forzar` | rellena aunque ya haya datos; **conserva los comerciales** que hubiera |
| `--todo` | con `--forzar`, regenera también los comerciales |
| `--verificar` | no genera nada: comprueba la coherencia y devuelve 1 si algo no cuadra |

Si la base ya tiene datos y no se pasa `--forzar`, el script dice cuántas filas
hay y no toca nada.

### Qué significa «coherente»

El generador (`scripts/demo_data.py`) aplica las reglas de `FORMULAS.PAS` y
`FACTURAS.PAS`, y `verificar()` lo comprueba contra la base ya escrita:

- el subtotal de cada albarán se obtiene con `calcular_albaran`, usando las
  tarifas del cliente y los puntos por km de la configuración;
- una factura recoge **solo** albaranes de su cliente y **solo** los que aún no
  estaban facturados, y sus totales salen de `total_albaran_cliente`
  (descuento → IVA → recargo de equivalencia → neto);
- `albaran.facturado` vale 1 exactamente en los albaranes que aparecen en alguna
  línea de factura, y ninguno está en dos facturas;
- `cant_serv_1..9` de cada línea son las casillas facturables de ese albarán;
- las estadísticas mensuales se reconstruyen desde los clientes dados de alta y
  las facturas emitidas ese mes;
- los importes se redondean con el `round()` de Pascal (mitad hacia el
  infinito), no con el redondeo al par de Python.

La comprobación más fuerte **recalcula cada subtotal desde la base de datos**,
leyendo casillas, tarifas y configuración ya guardadas, en vez de fiarse de los
números que trae el generador. Las 17 comprobaciones pasan con la base que hay
en `../bbdd.sqlite`.

## Uso

| | |
|---|---|
| Selector de tabla | cambia de tabla; también por URL: `/?tabla=cliente` |
| Celda | doble clic para editar; Enter o Tab confirma |
| `+ Nueva fila` | añade una fila en blanco al final, pendiente de guardar |
| `Guardar cambios` | **escribe en la base de datos** todo lo pendiente |
| `Descartar` | tira los cambios y vuelve a lo almacenado |
| `Eliminar seleccionadas` | borra las filas marcadas |
| `Filtrar…` | filtro rápido de AG Grid sobre todas las columnas |
| Cabecera de columna | ordenar y filtrar |
| `Esquema de la tabla` | columnas, tipos, `NOT NULL`, PK y FK |

## Cómo funciona la edición

La rejilla trabaja en modo cliente (AG Grid Community). **Editar una celda no
escribe nada en disco**: un `clientside_callback` sobre `cellValueChanged`
acumula la fila completa en un `dcc.Store` del navegador. Solo el botón
«Guardar» abre una transacción y escribe.

Ventajas de este diseño:

- no hay estados intermedios ni escrituras parciales;
- se pueden editar varias filas y guardar de una vez;
- si algo viola una restricción, **no se escribe nada** y el buffer se conserva
  para poder corregirlo;
- «Descartar» es un reverso real.

Cada fila lleva un `__pk__` con su clave primaria en JSON. Así las claves
compuestas (`albaran`: `num_albaran` + `letra`) se manejan sin ambigüedad, y
las filas nuevas llevan un token `nuevo:…` hasta que se consolidan.

## Tipos de columna derivados del DDL

| En el esquema | En la rejilla |
|---|---|
| `PRIMARY KEY` | fijada a la izquierda, resaltada, **no editable** |
| `BOOLEAN` | casilla de verificación (valor 0/1) |
| `CHECK (col IN (...))` | desplegable con los valores permitidos |
| `INTEGER` / `SMALLINT` / `BIGINT` | editor numérico |
| `NUMERIC` / `REAL` | editor numérico con decimales |
| `VARCHAR(n)` / `CHAR(n)` | editor de texto |
| `FOREIGN KEY` | el texto de la cabecera indica la tabla destino |
| `DEFAULT` | se aplica a las celdas que el usuario no toca |

## Decisiones de diseño

- **Una sola callback de control.** En Dash una propiedad solo puede ser salida
  de una callback, así que elegir tabla, nueva fila, guardar, descartar, borrar
  y filtrar cuelgan de un único callback que se distingue con
  `ctx.triggered_id`. Si se reparten en varias, las que compartan firma de
  salida se pisan en silencio y solo queda registrada la última.
- **El orden de los parámetros importa.** Dash pasa los argumentos
  posicionalmente en el orden de la declaración; un desajuste hace que, por
  ejemplo, el nombre de tabla acabe en el parámetro del filtro. Hay una prueba
  que lo vigila.
- **La clave primaria no se edita.** La fila se identifica por ella, y
  cambiarla en un `UPDATE` dejaría filas inaccesibles.
- **Las restricciones mandan.** `PRAGMA foreign_keys = ON`, y los errores de
  SQLite se traducen nombrando lo concreto: la restricción que falla
  (`ck_mensajero_vehic`), la columna que se repite (`cliente.telefono`), la que
  falta. Los `ON DELETE CASCADE` del esquema se respetan; el resto de borrados
  se rechazan si dejarían filas huérfanas.
- **Transacciones explícitas** (`BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK`) y
  `busy_timeout`, para poder convivir con otros procesos abriendo SQLite.
- **Solo se escribe lo que cambia.** El `UPDATE` compara con el valor actual y
  solo asigna las columnas distintas, así que una fila abierta en la rejilla no
  pisa cambios ajenos.
- **Tema oscuro por CSS.** AG Grid 33+ se tematiza con variables `--ag-*`; el
  componente escribe su altura en línea, por eso la altura de la rejilla se fija
  con `!important`.

## Pruebas

```bash
uv run python scripts/smoke_test.py
```

65 comprobaciones contra una base de demostración diminuta (3 clientes,
3 mensajeros y un albarán con una casilla), sin necesidad de servidor:
generación de columnas, coerción de tipos, valores por defecto, validación de
longitudes y listas, altas, ediciones, borrados, `CASCADE`, rechazo por clave
foránea, botones y superposición de cambios pendientes. Además inyecta el
contexto de `dash.ctx` para ejecutar la callback de control por cada rama, y
exige que la base que acaba de generar pase las 17 comprobaciones de coherencia
de `demo_data.verificar`.

## Seguridad

Pensado para `localhost`, pero aun así:

- los nombres de tabla y columna se leen de `sqlite_master` y se validan con
  `^[A-Za-z_][A-Za-z0-9_]*$` antes de interpolarse en el SQL;
- todos los **valores** viajan como parámetros ligados, nunca concatenados;
- el escapado de HTML lo hace AG Grid al renderizar, no hay plantillas;
- las escrituras solo ocurren al pulsar «Guardar», dentro de una transacción.

**No hay autenticación.** No lo expongas fuera de `localhost`: cualquiera que
llegue al puerto puede modificar la base de datos.

## Estructura

```
web/
├── pyproject.toml
├── scripts/
│   ├── demo_data.py        # datos de demostración + verificación de coherencia
│   ├── smoke_test.py       # 65 comprobaciones
│   ├── dev.py              # arranque limpio (libera el puerto antes)
│   └── libera_puerto.py    # mata todo lo que escuche en el puerto
└── src/mensages_web/
    ├── cli.py              # arranque
    ├── app.py              # layout y callbacks de Dash
    ├── db.py               # conexión, coerción, INSERT/UPDATE/DELETE
    ├── meta.py             # introspección del esquema
    ├── grid.py             # esquema -> columnDefs de AG Grid
    └── assets/style.css
```

### Nota sobre `dev.py`

En Windows pueden quedar varios procesos escuchando en el mismo puerto, y las
peticiones acaban en el más antiguo, que sirvirá código obsoleto. Por eso
`dev.py` mata **todos** los que escuchan y espera a que el puerto quede libre
antes de arrancar. Si editas código y no ves el cambio, es que hay un servidor
viejo colgado: `uv run python scripts/libera_puerto.py 8000`.
