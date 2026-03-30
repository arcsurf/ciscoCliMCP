import csv
import logging
from pathlib import Path
from functools import lru_cache

from models import DeviceParams

logger = logging.getLogger("cisco-mcp")


@lru_cache(maxsize=8)
def load_inventory(csv_path: str) -> dict[str, dict]:
    path = Path(csv_path)

    if not path.exists():
        raise ValueError(f"No existe el fichero de inventario CSV: {csv_path}")

    inventory: dict[str, dict] = {}

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise ValueError("El CSV de inventario no tiene cabecera.")

        required = {"hostname", "ip"}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(
                f"Faltan columnas obligatorias en el CSV: {', '.join(sorted(missing))}"
            )

        for row_num, row in enumerate(reader, start=2):
            hostname = (row.get("hostname") or "").strip()
            ip = (row.get("ip") or "").strip()

            if not hostname or not ip:
                logger.warning("Fila %s ignorada por faltar hostname/ip", row_num)
                continue

            try:
                port = int((row.get("port") or "22").strip() or "22")
            except ValueError:
                raise ValueError(f"Puerto inválido para '{hostname}' en línea {row_num}")

            key = hostname.lower()
            if key in inventory:
                raise ValueError(f"Hostname duplicado en inventario: '{hostname}'")

            inventory[key] = {
                "hostname": hostname,
                "host": ip,
                "device_type": (row.get("device_type") or "").strip() or "cisco_ios",
                "port": port,
                "username": (row.get("username") or "").strip() or None,
                "password": (row.get("password") or "").strip() or None,
                "secret": (row.get("secret") or "").strip() or None,
            }

    return inventory


def get_device_from_inventory(hostname: str, csv_path: str) -> DeviceParams:
    inventory = load_inventory(csv_path)

    key = hostname.strip().lower()
    if key not in inventory:
        available = ", ".join(sorted(inventory.keys())) if inventory else "inventario vacío"
        raise ValueError(
            f"El hostname '{hostname}' no existe en el inventario. Disponibles: {available}"
        )

    device = inventory[key]

    return DeviceParams(
        host=device["host"],
        device_type=device["device_type"],
        username=device["username"],
        password=device["password"],
        secret=device["secret"],
        port=device["port"],
    )