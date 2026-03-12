import os
import re
import sys
import logging
from typing import Optional, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from netmiko import ConnectHandler
from mcp.server.fastmcp import FastMCP

load_dotenv()

# Logs siempre a stderr, nunca a stdout en STDIO
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

# Lista blanca inicial para solo lectura
ALLOWED_SHOW_COMMANDS = {
    "show version",
    "show ip interface brief",
    "show interfaces status",
    "show running-config",
    "show startup-config",
    "show inventory",
    "show platform",
    "show cdp neighbors",
    "show lldp neighbors",
    "show ip route",
    "show arp",
    "show mac address-table",
    "show vlan brief",
    "show spanning-tree",
    "show logging",
    "show clock",
    "show users",
}

# Lista blanca opcional para configuración
ALLOWED_CONFIG_PREFIXES = (
    "interface ",
    "description ",
    "hostname ",
    "ip address ",
    "no shutdown",
    "shutdown",
    "snmp-server ",
    "logging ",
)

BLOCKED_PATTERNS = (
    r"^reload\b",
    r"^write erase\b",
    r"^erase startup-config\b",
    r"^format\b",
    r"^delete\b",
    r"^copy\b",
    r"^archive\b",
    r"^boot\b",
    r"^license\b",
    r"^username\b",
    r"^enable secret\b",
)

class DeviceParams(BaseModel):
    host: str = Field(..., description="IP o hostname del router Cisco")
    device_type: str = Field(DEFAULT_DEVICE_TYPE, description="Ej: cisco_ios, cisco_xe, cisco_nxos")
    username: Optional[str] = Field(DEFAULT_USERNAME, description="Usuario SSH")
    password: Optional[str] = Field(DEFAULT_PASSWORD, description="Password SSH")
    secret: Optional[str] = Field(DEFAULT_SECRET, description="Enable secret si aplica")
    port: int = Field(22, description="Puerto SSH")

def _validate_credentials(params: DeviceParams):
    if not params.username or not params.password:
        raise ValueError("Faltan credenciales: username/password.")

def _normalize_command(cmd: str) -> str:
    return " ".join(cmd.strip().split())

def _check_show_command(cmd: str):
    normalized = _normalize_command(cmd)
    if not normalized.startswith("show "):
        raise ValueError(f"Solo se permiten comandos show. Recibido: {normalized}")
    if normalized not in ALLOWED_SHOW_COMMANDS:
        raise ValueError(
            f"Comando no permitido por whitelist: {normalized}. "
            f"Añádelo explícitamente si quieres usarlo."
        )

def _check_config_line(line: str):
    normalized = _normalize_command(line)

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            raise ValueError(f"Línea bloqueada por seguridad: {normalized}")

    if not normalized:
        return

    if not any(normalized.startswith(prefix) for prefix in ALLOWED_CONFIG_PREFIXES):
        raise ValueError(
            f"Línea no permitida por whitelist de configuración: {normalized}"
        )

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

@mcp.tool()
def run_show_command(
    host: str,
    command: str,
    device_type: str = DEFAULT_DEVICE_TYPE,
    username: Optional[str] = DEFAULT_USERNAME,
    password: Optional[str] = DEFAULT_PASSWORD,
    secret: Optional[str] = DEFAULT_SECRET,
    port: int = 22,
) -> str:
    """
    Ejecuta un único comando show en un router Cisco vía SSH.
    Solo admite comandos show presentes en whitelist.
    """
    params = DeviceParams(
        host=host,
        device_type=device_type,
        username=username,
        password=password,
        secret=secret,
        port=port,
    )

    _check_show_command(command)

    logger.info("Ejecutando show command en host=%s command=%s", host, command)

    with _connect(params) as conn:
        try:
            if params.secret:
                conn.enable()
        except Exception:
            pass

        output = conn.send_command(command, read_timeout=60)

    return output

@mcp.tool()
def run_show_commands(
    host: str,
    commands: list[str],
    device_type: str = DEFAULT_DEVICE_TYPE,
    username: Optional[str] = DEFAULT_USERNAME,
    password: Optional[str] = DEFAULT_PASSWORD,
    secret: Optional[str] = DEFAULT_SECRET,
    port: int = 22,
) -> str:
    """
    Ejecuta varios comandos show permitidos y devuelve el resultado consolidado.
    """
    params = DeviceParams(
        host=host,
        device_type=device_type,
        username=username,
        password=password,
        secret=secret,
        port=port,
    )

    for cmd in commands:
        _check_show_command(cmd)

    logger.info("Ejecutando batch show commands en host=%s", host)

    results = []
    with _connect(params) as conn:
        try:
            if params.secret:
                conn.enable()
        except Exception:
            pass

        for cmd in commands:
            output = conn.send_command(cmd, read_timeout=60)
            results.append(f"$ {cmd}\n{output}")

    return "\n\n" + ("\n\n" + ("-" * 80) + "\n\n").join(results)

@mcp.tool()
def get_device_facts(
    host: str,
    device_type: str = DEFAULT_DEVICE_TYPE,
    username: Optional[str] = DEFAULT_USERNAME,
    password: Optional[str] = DEFAULT_PASSWORD,
    secret: Optional[str] = DEFAULT_SECRET,
    port: int = 22,
) -> str:
    """
    Obtiene información base del equipo.
    """
    params = DeviceParams(
        host=host,
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

    for cmd in commands:
        _check_show_command(cmd)

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

    return "\n\n" + ("\n\n" + ("=" * 80) + "\n\n").join(results)

@mcp.tool()
def push_config(
    host: str,
    config_lines: list[str],
    confirm: Literal["YES"] = "YES",
    device_type: str = DEFAULT_DEVICE_TYPE,
    username: Optional[str] = DEFAULT_USERNAME,
    password: Optional[str] = DEFAULT_PASSWORD,
    secret: Optional[str] = DEFAULT_SECRET,
    port: int = 22,
) -> str:
    """
    Empuja configuración limitada por whitelist.
    Requiere confirm='YES'.
    """
    if confirm != "YES":
        raise ValueError("Debes pasar confirm='YES' para permitir cambios.")

    params = DeviceParams(
        host=host,
        device_type=device_type,
        username=username,
        password=password,
        secret=secret,
        port=port,
    )

    cleaned = []
    for line in config_lines:
        normalized = _normalize_command(line)
        if normalized:
            _check_config_line(normalized)
            cleaned.append(normalized)

    logger.warning("Aplicando configuración en host=%s lines=%s", host, cleaned)

    with _connect(params) as conn:
        if params.secret:
            conn.enable()

        result = conn.send_config_set(cleaned)
        save_output = conn.save_config() if hasattr(conn, "save_config") else "Config aplicada. Guardado no soportado por driver."

    return f"{result}\n\n--- SAVE ---\n{save_output}"

if __name__ == "__main__":
    # Para uso local con clientes que lanzan el servidor por STDIO
    mcp.run()
