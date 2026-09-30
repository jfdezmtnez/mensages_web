# MensaGes · editor web de `bbdd.sqlite`

Aplicación web local (**Dash + AG Grid**, vía `dash_ag_grid`) para consultar,
crear, editar y borrar las 15 tablas del esquema MensaGes desde una rejilla.

El esquema se **introspecciona en tiempo de ejecución** desde `sqlite_master` y
`PRAGMA table_info`: no hay ni una tabla ni una columna escrita a mano, así que
las columnas, los editores, las claves primarias y las restricciones se adaptan
solos al DDL.

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

Para ver la aplicación con contenido sin tocar los datos reales:

```bash
uv run python scripts/seed_demo.py          # crea ../bbdd.demo.sqlite
uv run mensages-web --db ../bbdd.demo.sqlite
```

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
  SQLite se traducen nombrando la restricción concreta (`ck_mensajero_vehic`,
  `uq_cliente_telefono`…) en lugar de un mensaje genérico. Los
  `ON DELETE CASCADE` del esquema se respetan; el resto de borrados se rechazan
  si dejarían filas huérfanas.
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

63 comprobaciones contra una base de demostración, sin necesidad de servidor:
generación de columnas, coerción de tipos, valores por defecto, validación de
longitudes y listas, altas, ediciones, borrados, `CASCADE`, rechazo por clave
foránea, botones y superposición de cambios pendientes. Además inyecta el
contexto de `dash.ctx` para ejecutar la callback de control por cada rama.

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
│   ├── seed_demo.py        # base de datos de demostración
│   ├── smoke_test.py       # 63 comprobaciones
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
