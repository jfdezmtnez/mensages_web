"""Editor web local (CRUD) sobre la base de datos SQLite de MensaGes.

Interfaz Dash + AG Grid (``dash_ag_grid``). El esquema de la base de datos se
introspecciona en tiempo de ejecucion, de modo que las columnas, los editores
y las restricciones se generan a partir del DDL real.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
