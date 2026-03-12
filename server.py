import os
import sys
import logging
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
    host: str = Field(..., description="IP o hostname del router Cisco")
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


def _sanitize_output(text: str) -> str:
    return text


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
def run_exec_command(
    host: str,
    command: str,
    confirm: Literal["LAB"] = "LAB",
    device_type: str = DEFAULT_DEVICE_TYPE,
    username: Optional[str] = DEFAULT_USERNAME,
    password: Optional[str] = DEFAULT_PASSWORD,
    secret: Optional[str] = DEFAULT_SECRET,
    port: int = 22,
) -> str:
    """
    Ejecuta un comando EXEC/operacional en un router Cisco de laboratorio.
    Esta herramienta está pensada para comandos como show, ping, traceroute,
    clear counters y otros comandos operacionales compatibles con el modo EXEC.
    Requiere confirm='LAB' y CISCO_LAB_MODE=true.
    """
    _require_lab_mode()

    if confirm != "LAB":
        raise ValueError("Debes pasar confirm='LAB' para ejecutar comandos abiertos en laboratorio.")

    normalized = _normalize_command(command)
    if not normalized:
        raise ValueError("El comando no puede estar vacío.")

    params = DeviceParams(
        host=host,
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

    return output


@mcp.tool()
def run_exec_commands(
    host: str,
    commands: list[str],
    confirm: Literal["LAB"] = "LAB",
    device_type: str = DEFAULT_DEVICE_TYPE,
    username: Optional[str] = DEFAULT_USERNAME,
    password: Optional[str] = DEFAULT_PASSWORD,
    secret: Optional[str] = DEFAULT_SECRET,
    port: int = 22,
) -> str:
    """
    Ejecuta varios comandos EXEC/operacionales en un router Cisco de laboratorio.
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

    params = DeviceParams(
        host=host,
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

    return "\n\n" + ("\n\n" + ("-" * 80) + "\n\n").join(results)


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
    Ejecuta cualquier comando show válido en un router Cisco.
    Usa esta herramienta para consultar estado, rutas, interfaces,
    inventario o configuración del equipo.

    Ejemplos:
    - show version
    - show ip interface brief
    - show running-config
    - show ip route
    - show logging | begin LINEPROTO
    - show running-config | section interface
    """
    params = DeviceParams(
        host=host,
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
    device_type: str = DEFAULT_DEVICE_TYPE,
    username: Optional[str] = DEFAULT_USERNAME,
    password: Optional[str] = DEFAULT_PASSWORD,
    secret: Optional[str] = DEFAULT_SECRET,
    port: int = 22,
) -> str:
    """
    Aplica comandos de configuración en un router Cisco de laboratorio.
    Usa el modo configuración del equipo.
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

    params = DeviceParams(
        host=host,
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
        return f"{result}\n\n--- SAVE ---\n{save_output}"
    return result


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
    Esta herramienta sigue siendo útil para preguntas en lenguaje natural.
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


if __name__ == "__main__":
    mcp.run()
