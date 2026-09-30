"""Reinicia el servidor de desarrollo de mensages-web de forma determinista.

    uv run python scripts/dev.py --port 8086 [--db ruta.sqlite] [--sin-arrancar]

Matar cualquier cosa que escuche en el puerto, esperar a que quede libre y
lanzar una unica instancia. Sin esto, dos ejecuciones de dev.py se pisan y
acaba sirviendo el proceso viejo con codigo obsoleto.
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from libera_puerto import liberar  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8086)
    ap.add_argument("--db", default=str(REPO / "bbdd.demo.sqlite"))
    ap.add_argument("--sin-arrancar", action="store_true")
    args = ap.parse_args()

    if args.db and not Path(args.db).is_file():
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "demo_data.py"), "--db", args.db],
            check=True,
        )

    liberar(args.port)
    if args.sin_arrancar:
        return 0

    print(f"http://127.0.0.1:{args.port}/  sobre  {args.db}", flush=True)
    return subprocess.call(
        [sys.executable, "-m", "mensages_web.cli", "--db", args.db, "--port", str(args.port)]
    )


if __name__ == "__main__":
    raise SystemExit(main())
