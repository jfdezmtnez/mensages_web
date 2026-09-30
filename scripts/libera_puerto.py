"""Libera un puerto matando todos los procesos que lo escuchen.

En Windows es normal que varios sockets queden en LISTENING sobre el mismo
puerto (semantica de SO_REUSEADDR), y las peticiones pueden acabar en el
proceso mas antiguo, que sirvira codigo obsoleto. Por eso hay que matarlos
todos y esperar a que no quede ninguno.
"""

import socket
import subprocess
import sys
import time


def pids_escuchando(port: int) -> set[str]:
    out = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, errors="replace"
    ).stdout
    pids = set()
    for linea in out.splitlines():
        partes = linea.split()
        if len(partes) < 5 or partes[0] != "TCP":
            continue
        if partes[1].endswith(f":{port}") and partes[2] == "LISTENING":
            pid = partes[-1]
            if pid.isdigit() and int(pid) > 0:
                pids.add(pid)
    return pids


def _conecta(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def liberar(port: int, intentos: int = 8) -> None:
    for _ in range(intentos):
        pids = pids_escuchando(port)
        if not pids:
            print(f"puerto {port}: libre")
            return
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True)
        time.sleep(0.7)
    pids = pids_escuchando(port)
    if pids or _conecta(port):
        raise SystemExit(f"El puerto {port} sigue ocupado (PIDs {sorted(pids)})")
    print(f"puerto {port}: libre")


if __name__ == "__main__":
    liberar(int(sys.argv[1]) if len(sys.argv) > 1 else 8086)
