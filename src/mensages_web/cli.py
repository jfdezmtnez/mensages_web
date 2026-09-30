"""Arranque del servidor local.

    uv run mensages-web
    uv run mensages-web --port 9000 --db otra.sqlite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import db


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mensages-web",
        description="Editor web local de la base de datos SQLite de MensaGes.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=db.default_db_path(),
        help="Ruta del fichero SQLite (por defecto: bbdd.sqlite del repositorio).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Interfaz de escucha.")
    parser.add_argument("--port", type=int, default=8000, help="Puerto HTTP.")
    parser.add_argument("--debug", action="store_true", help="Recarga al guardar.")
    args = parser.parse_args(argv)

    if not args.db.is_file():
        print(f"error: no encuentro la base de datos en {args.db}", file=sys.stderr)
        return 1

    from . import app as server

    server.DB_PATH = args.db.resolve()
    server.app.title = f"MensaGes · editor de {server.DB_PATH.name}"

    print(f"Base de datos: {server.DB_PATH}")
    print(f"Editor:        http://{args.host}:{args.port}/")
    print(f"Codigo:        {Path(server.__file__).parent}")
    server.app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
