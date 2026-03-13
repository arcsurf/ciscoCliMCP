import os
import sys
import csv
import logging
from pathlib import Path
from typing import Optional, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from netmiko import ConnectHandler
from mcp.server.fastmcp import FastMCP

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("cisco-mcp")

mcp = FastMCP("Cisco Router MCP")

DEFAULT_DEVICE_TYPE = os.getenv("CISCO_DEFAULT_DEVICE_TYPE", "cisco_ios")
DEFAULT_USERNAME = os.getenv("CISCO_USERNAME")
DEFAULT_PASSWORD = os.getenv("CISCO_PASSWORD")
DEFAULT_SECRET = os.getenv("CISCO_ENABLE_SECRET")
DEFAULT_INVENTORY_CSV = os.getenv("CISCO_INVENTORY_CSV", "inventory.csv")

# Modo laboratorio: debe activarse explícitamente
LAB_MODE = os.getenv("CISCO_LAB_MODE", "false").lower() == "true"

READ_TIMEOUT = int(os.getenv("CISCO_READ_TIMEOUT", "120"))

ALLOWED_SHOW_FILTERS = {
    "include",
    "exclude",
    "begin",
    "section",
}


class DeviceParams(BaseModel):
    host: str = Field(..., description="IP o hostname real del dispositivo Cisco")
    device_type: str = Field(DEFAULT_DEVICE_TYPE, description="Ej: cisco_ios, cisco_xe, cisco_nxos")
    username: Optional[str] = Field(DEFAULT_USERNAME, description="Usuario SSH")
    password: Optional[str] = Field(DEFAULT_PASSWORD, description="Password SSH")
    secret: Optional[str] = Field(DEFAULT_SECRET, description="Enable secret si aplica")
    port: int = Field(22, description="Puerto SSH")


def _require_lab_mode():
    if not LAB_MODE:
        raise ValueError(
            "CISCO_LAB_MODE no está activado. "
            "Define CISCO_LAB_MODE=true en el .env para usar comandos abiertos en laboratorio."
        )


def _validate_credentials(params: DeviceParams):
    if not params.username or not params.password:
        raise ValueError("Faltan credenciales: username/password.")


def _normalize_command(cmd: str) -> str:
    return " ".join(cmd.strip().split())


def _validate_show_command(command: str) -> str:
    normalized = _normalize_command(command)
    if not normalized:
        raise ValueError("El comando no puede estar vacío.")

    lower_cmd = normalized.lower()

    if not lower_cmd.startswith("show "):
        raise ValueError("Solo se permiten comandos que comiencen por 'show '.")

    if "|" in normalized:
        parts = [p.strip() for p in normalized.split("|")]
        if len(parts) < 2:
            raise ValueError("Sintaxis inválida en el pipe del comando show.")

        for pipe_part in parts[1:]:
            tokens = pipe_part.split()
            keyword = tokens[0].lower() if tokens else ""
            if keyword not in ALLOWED_SHOW_FILTERS:
                raise ValueError(
                    f"Filtro no permitido tras '|': {keyword}. "
                    f"Permitidos: {', '.join(sorted(ALLOWED_SHOW_FILTERS))}"
                )

    return normalized


def _sanitize_output(text: Optional[str]) -> str:
    if text is None:
        return "```text\n\n```"

    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").rstrip()
    return f"```text\n{cleaned}\n```"


def _load_inventory(csv_path: str = DEFAULT_INVENTORY_CSV) -> dict[str, dict]:
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
                logger.warning(
                    "Fila %s ignorada en inventario CSV por faltar hostname/ip",
                    row_num
                )
                continue

            try:
                port = int((row.get("port") or "22").strip() or "22")
            except ValueError:
                raise ValueError(
                    f"Puerto inválido en CSV para hostname '{hostname}' en línea {row_num}"
                )

            key = hostname.lower()

            if key in inventory:
                raise ValueError(
                    f"Hostname duplicado en inventario CSV: '{hostname}' (línea {row_num})"
                )

            inventory[key] = {
                "hostname": hostname,
                "host": ip,
                "device_type": (row.get("device_type") or "").strip() or DEFAULT_DEVICE_TYPE,
                "port": port,
                "username": (row.get("username") or "").strip() or DEFAULT_USERNAME,
                "password": (row.get("password") or "").strip() or DEFAULT_PASSWORD,
                "secret": (row.get("secret") or "").strip() or DEFAULT_SECRET,
            }

    return inventory


def _get_device_from_inventory(
    hostname: str,
    csv_path: str = DEFAULT_INVENTORY_CSV,
) -> DeviceParams:
    inventory = _load_inventory(csv_path)

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


def _resolve_device(
    host: str,
    inventory_csv: str = DEFAULT_INVENTORY_CSV,
    device_type: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    secret: Optional[str] = None,
    port: Optional[int] = None,
) -> DeviceParams:
    """
    El parámetro host representa el hostname lógico definido en el CSV.
    """
    params = _get_device_from_inventory(host, inventory_csv)

    if device_type:
        params.device_type = device_type
    if username:
        params.username = username
    if password:
        params.password = password
    if secret:
        params.secret = secret
    if port:
        params.port = port

    return params


def _connect(params: DeviceParams):
    _validate_credentials(params)

    device = {
        "device_type": params.device_type,
        "host": params.host,
        "username": params.username,
        "password": params.password,
        "secret": params.secret,
        "port": params.port,
        "fast_cli": False,
    }

    return ConnectHandler(**device)


def _get_show_output(params: DeviceParams, command: str) -> str:
    normalized = _validate_show_command(command)

    with _connect(params) as conn:
        try:
            if params.secret:
                conn.enable()
        except Exception:
            pass

        output = conn.send_command(
            normalized,
            read_timeout=READ_TIMEOUT,
            strip_prompt=False,
            strip_command=False,
        )

    return _sanitize_output(output)


@mcp.tool()
def list_inventory(inventory_csv: str = DEFAULT_INVENTORY_CSV) -> str:
    """
    Lista los equipos disponibles en el inventario CSV.
    Devuelve el contenido preservando líneas y saltos de línea.
    """
    inventory = _load_inventory(inventory_csv)

    if not inventory:
        return _sanitize_output("El inventario está vacío.")

    lines = []
    for key in sorted(inventory.keys()):
        item = inventory[key]
        lines.append(
            f"{item['hostname']} -> {item['host']} "
            f"(device_type={item['device_type']}, port={item['port']})"
        )

    return _sanitize_output("\n".join(lines))


@mcp.tool()
def run_exec_command(
    host: str,
    command: str,
    confirm: Literal["LAB"] = "LAB",
    device_type: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    secret: Optional[str] = None,
    port: Optional[int] = None,
    inventory_csv: str = DEFAULT_INVENTORY_CSV,
) -> str:
    """
    Ejecuta un comando EXEC/operacional en un router Cisco de laboratorio.

    El parámetro host debe coincidir con el hostname definido en el CSV.
    Esta herramienta está pensada para comandos como show, ping, traceroute,
    clear counters y otros comandos operacionales compatibles con el modo EXEC.

    Devuelve la salida cruda en formato preformateado, preservando líneas,
    columnas y saltos de línea.

    Requiere confirm='LAB' y CISCO_LAB_MODE=true.
    """
    _require_lab_mode()

    if confirm != "LAB":
        raise ValueError("Debes pasar confirm='LAB' para ejecutar comandos abiertos en laboratorio.")

    normalized = _normalize_command(command)
    if not normalized:
        raise ValueError("El comando no puede estar vacío.")

    params = _resolve_device(
        host=host,
        inventory_csv=inventory_csv,
        device_type=device_type,
        username=username,
        password=password,
        secret=secret,
        port=port,
    )

    logger.warning("LAB EXEC host=%s command=%s", host, normalized)

    with _connect(params) as conn:
        try:
            if params.secret:
                conn.enable()
        except Exception:
            pass

        output = conn.send_command_timing(
            normalized,
            strip_prompt=False,
            strip_command=False
        )

    return _sanitize_output(output)


@mcp.tool()
def run_exec_commands(
    host: str,
    commands: list[str],
    confirm: Literal["LAB"] = "LAB",
    device_type: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    secret: Optional[str] = None,
    port: Optional[int] = None,
    inventory_csv: str = DEFAULT_INVENTORY_CSV,
) -> str:
    """
    Ejecuta varios comandos EXEC/operacionales en un router Cisco de laboratorio.
    El parámetro host debe coincidir con el hostname definido en el CSV.

    Devuelve la salida cruda en formato preformateado, preservando líneas,
    columnas y saltos de línea.

    Requiere confirm='LAB' y CISCO_LAB_MODE=true.
    """
    _require_lab_mode()

    if confirm != "LAB":
        raise ValueError("Debes pasar confirm='LAB' para ejecutar comandos abiertos en laboratorio.")

    cleaned = []
    for cmd in commands:
        normalized = _normalize_command(cmd)
        if normalized:
            cleaned.append(normalized)

    if not cleaned:
        raise ValueError("Debes proporcionar al menos un comando válido.")

    params = _resolve_device(
        host=host,
        inventory_csv=inventory_csv,
        device_type=device_type,
        username=username,
        password=password,
        secret=secret,
        port=port,
    )

    logger.warning("LAB EXEC BATCH host=%s commands=%s", host, cleaned)

    results = []
    with _connect(params) as conn:
        try:
            if params.secret:
                conn.enable()
        except Exception:
            pass

        for cmd in cleaned:
            output = conn.send_command_timing(
                cmd,
                strip_prompt=False,
                strip_command=False
            )
            results.append(f"$ {cmd}\n{output}")

    combined = "\n\n" + ("\n\n" + ("-" * 80) + "\n\n").join(results)
    return _sanitize_output(combined)


@mcp.tool()
def run_show_command(
    host: str,
    command: str,
    device_type: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    secret: Optional[str] = None,
    port: Optional[int] = None,
    inventory_csv: str = DEFAULT_INVENTORY_CSV,
) -> str:
    """
    Ejecuta cualquier comando show válido en un router Cisco.

    El parámetro host debe coincidir con el hostname definido en el CSV.

    Devuelve la salida cruda del dispositivo, preservando formato,
    líneas y saltos de línea para que pueda mostrarse tal cual.

    Ejemplos:
    - host='R1', command='show version'
    - host='R2', command='show running-config | section interface'
    - host='SW1', command='show interfaces status'
    """
    params = _resolve_device(
        host=host,
        inventory_csv=inventory_csv,
        device_type=device_type,
        username=username,
        password=password,
        secret=secret,
        port=port,
    )

    return _get_show_output(params, command)


@mcp.tool()
def run_config_commands(
    host: str,
    config_lines: list[str],
    confirm: Literal["LAB"] = "LAB",
    save: bool = False,
    device_type: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    secret: Optional[str] = None,
    port: Optional[int] = None,
    inventory_csv: str = DEFAULT_INVENTORY_CSV,
) -> str:
    """
    Aplica comandos de configuración en un router Cisco de laboratorio.
    El parámetro host debe coincidir con el hostname definido en el CSV.

    Devuelve la salida cruda en formato preformateado, preservando líneas,
    columnas y saltos de línea.

    Requiere confirm='LAB' y CISCO_LAB_MODE=true.
    """
    _require_lab_mode()

    if confirm != "LAB":
        raise ValueError("Debes pasar confirm='LAB' para aplicar configuración en laboratorio.")

    cleaned = []
    for line in config_lines:
        normalized = _normalize_command(line)
        if normalized:
            cleaned.append(normalized)

    if not cleaned:
        raise ValueError("Debes proporcionar al menos una línea de configuración válida.")

    params = _resolve_device(
        host=host,
        inventory_csv=inventory_csv,
        device_type=device_type,
        username=username,
        password=password,
        secret=secret,
        port=port,
    )

    logger.warning("LAB CONFIG host=%s lines=%s save=%s", host, cleaned, save)

    with _connect(params) as conn:
        if params.secret:
            conn.enable()

        result = conn.send_config_set(cleaned)

        save_output = ""
        if save:
            if hasattr(conn, "save_config"):
                save_output = conn.save_config()
            else:
                save_output = "El driver actual no soporta save_config()."

    if save:
        return _sanitize_output(f"{result}\n\n--- SAVE ---\n{save_output}")

    return _sanitize_output(result)


@mcp.tool()
def get_device_facts(
    host: str,
    device_type: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    secret: Optional[str] = None,
    port: Optional[int] = None,
    inventory_csv: str = DEFAULT_INVENTORY_CSV,
) -> str:
    """
    Obtiene información base del equipo.
    El parámetro host debe coincidir con el hostname definido en el CSV.

    Devuelve la salida en formato preformateado, preservando líneas,
    columnas y saltos de línea.
    """
    params = _resolve_device(
        host=host,
        inventory_csv=inventory_csv,
        device_type=device_type,
        username=username,
        password=password,
        secret=secret,
        port=port,
    )

    commands = [
        "show version",
        "show ip interface brief",
        "show inventory",
        "show clock",
    ]

    with _connect(params) as conn:
        try:
            if params.secret:
                conn.enable()
        except Exception:
            pass

        results = []
        for cmd in commands:
            output = conn.send_command(cmd, read_timeout=60)
            results.append(f"$ {cmd}\n{output}")

    combined = "\n\n" + ("\n\n" + ("=" * 80) + "\n\n").join(results)
    return _sanitize_output(combined)


if __name__ == "__main__":
    mcp.run()
