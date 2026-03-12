import os
import re
import sys
import uuid
import time
import logging
from typing import Optional, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from netmiko import ConnectHandler
from netmiko.exceptions import (
    NetmikoTimeoutException,
    NetmikoAuthenticationException,
)
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

LAB_MODE = os.getenv("CISCO_LAB_MODE", "false").lower() == "true"

ALLOWED_HOSTS = {
    h.strip() for h in os.getenv("CISCO_ALLOWED_HOSTS", "").split(",") if h.strip()
}

# Comandos de solo lectura que se permiten explícitamente
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
    "show clock",
    "show users",
    "show hosts",
    "show arp",
    "show ip route",
    "show vlan brief",
    "show interfaces description",
    "show logging",
}

# Prefijos peligrosos para EXEC abierto en laboratorio
DENIED_EXEC_PREFIXES = (
    "reload",
    "write erase",
    "erase startup-config",
    "delete ",
    "format ",
    "debug ",
    "undebug ",
    "clear ip bgp",
    "copy ",
    "archive ",
    "request ",
    "install ",
)

# Líneas de configuración que conviene bloquear por seguridad
DENIED_CONFIG_PREFIXES = (
    "username ",
    "no username ",
    "enable secret ",
    "enable password ",
    "aaa ",
    "crypto key ",
    "boot system",
    "format ",
    "license ",
)

SECRET_PATTERNS = [
    (re.compile(r"(snmp-server community)\s+\S+", re.IGNORECASE), r"\1 <redacted>"),
    (re.compile(r"(username\s+\S+\s+password\s+\d?\s*)\S+", re.IGNORECASE), r"\1<redacted>"),
    (re.compile(r"(username\s+\S+\s+secret\s+\d?\s*)\S+", re.IGNORECASE), r"\1<redacted>"),
    (re.compile(r"(enable secret\s+\d?\s*)\S+", re.IGNORECASE), r"\1<redacted>"),
    (re.compile(r"(enable password\s+\d?\s*)\S+", re.IGNORECASE), r"\1<redacted>"),
    (re.compile(r"(pre-shared-key)\s+\S+", re.IGNORECASE), r"\1 <redacted>"),
    (re.compile(r"(wpa-psk\s+ascii\s+\d?\s*)\S+", re.IGNORECASE), r"\1<redacted>"),
]

READ_TIMEOUT = int(os.getenv("CISCO_READ_TIMEOUT", "120"))
CONNECT_TIMEOUT = int(os.getenv("CISCO_CONNECT_TIMEOUT", "15"))


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


def _validate_host(host: str):
    if ALLOWED_HOSTS and host not in ALLOWED_HOSTS:
        raise ValueError(f"Host no permitido: {host}")


def _normalize_command(cmd: str) -> str:
    return " ".join(cmd.strip().split())


def _sanitize_output(text: str) -> str:
    sanitized = text
    for pattern, replacement in SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def _ensure_show_allowed(command: str):
    cmd = _normalize_command(command).lower()
    if cmd not in ALLOWED_SHOW_COMMANDS:
        raise ValueError(
            f"Comando show no permitido: {command}. "
            f"Permitidos: {sorted(ALLOWED_SHOW_COMMANDS)}"
        )


def _ensure_exec_not_denied(command: str):
    cmd = _normalize_command(command).lower()
    for denied in DENIED_EXEC_PREFIXES:
        if cmd.startswith(denied):
            raise ValueError(f"Comando EXEC no permitido en laboratorio: {command}")


def _ensure_config_not_denied(lines: list[str]):
    for line in lines:
        normalized = _normalize_command(line).lower()
        for denied in DENIED_CONFIG_PREFIXES:
            if normalized.startswith(denied):
                raise ValueError(f"Línea de configuración no permitida: {line}")


def _friendly_error(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {exc}"


def _log_operation(kind: str, host: str, detail: str):
    op_id = str(uuid.uuid4())[:8]
    logger.warning("op=%s kind=%s host=%s detail=%s", op_id, kind, host, detail)
    return op_id


def _connect(params: DeviceParams):
    _validate_credentials(params)
    _validate_host(params.host)

    device = {
        "device_type": params.device_type,
        "host": params.host,
        "username": params.username,
        "password": params.password,
        "secret": params.secret,
        "port": params.port,
        "fast_cli": False,
        "conn_timeout": CONNECT_TIMEOUT,
        "banner_timeout": CONNECT_TIMEOUT,
        "auth_timeout": CONNECT_TIMEOUT,
        "timeout": READ_TIMEOUT,
    }

    return ConnectHandler(**device)


def _enable_if_possible(conn, params: DeviceParams):
    if params.secret:
        try:
            conn.enable()
        except Exception:
            pass


def _read_show_command(params: DeviceParams, command: str) -> str:
    with _connect(params) as conn:
        _enable_if_possible(conn, params)
        output = conn.send_command(
            command,
            read_timeout=READ_TIMEOUT,
            strip_prompt=False,
            strip_command=False
        )
    return _sanitize_output(output)


def _run_exec_command(params: DeviceParams, command: str) -> str:
    with _connect(params) as conn:
        _enable_if_possible(conn, params)
        output = conn.send_command_timing(
            command,
            strip_prompt=False,
            strip_command=False
        )
    return _sanitize_output(output)


@mcp.tool()
def show_running_config(
    host: str,
    device_type: str = DEFAULT_DEVICE_TYPE,
    username: Optional[str] = DEFAULT_USERNAME,
    password: Optional[str] = DEFAULT_PASSWORD,
    secret: Optional[str] = DEFAULT_SECRET,
    port: int = 22,
) -> str:
    """
    Muestra la configuración completa del equipo con formato multilínea.
    Herramienta de solo lectura para consultar el running-config.
    Usa esta tool cuando el usuario pida ver la configuración completa del router.
    """
    params = DeviceParams(
        host=host,
        device_type=device_type,
        username=username,
        password=password,
        secret=secret,
        port=port,
    )

    op_id = _log_operation("show_running_config", host, "show running-config")
    started = time.time()

    try:
        output = _read_show_command(params, "show running-config")
        elapsed = round(time.time() - started, 2)
        logger.info("op=%s completed in %ss", op_id, elapsed)
        return output
    except NetmikoAuthenticationException as exc:
        raise ValueError(f"Autenticación fallida contra {host}: {_friendly_error(exc)}")
    except NetmikoTimeoutException as exc:
        raise ValueError(f"Timeout conectando o leyendo en {host}: {_friendly_error(exc)}")
    except Exception as exc:
        raise ValueError(f"Error obteniendo running-config en {host}: {_friendly_error(exc)}")


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
    Ejecuta un comando show seguro en un equipo Cisco.
    Solo admite comandos show explícitamente permitidos.
    No aplica cambios de configuración.
    """
    normalized = _normalize_command(command)
    if not normalized:
        raise ValueError("El comando no puede estar vacío.")

    _ensure_show_allowed(normalized)

    params = DeviceParams(
        host=host,
        device_type=device_type,
        username=username,
        password=password,
        secret=secret,
        port=port,
    )

    op_id = _log_operation("run_show_command", host, normalized)
    started = time.time()

    try:
        output = _read_show_command(params, normalized)
        elapsed = round(time.time() - started, 2)
        logger.info("op=%s completed in %ss", op_id, elapsed)
        return output
    except NetmikoAuthenticationException as exc:
        raise ValueError(f"Autenticación fallida contra {host}: {_friendly_error(exc)}")
    except NetmikoTimeoutException as exc:
        raise ValueError(f"Timeout conectando o leyendo en {host}: {_friendly_error(exc)}")
    except Exception as exc:
        raise ValueError(f"Error ejecutando show en {host}: {_friendly_error(exc)}")


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
    Ejecuta varios comandos show seguros en un equipo Cisco.
    Solo admite comandos show explícitamente permitidos.
    No aplica cambios de configuración.
    """
    cleaned = []
    for cmd in commands:
        normalized = _normalize_command(cmd)
        if normalized:
            _ensure_show_allowed(normalized)
            cleaned.append(normalized)

    if not cleaned:
        raise ValueError("Debes proporcionar al menos un comando show válido.")

    params = DeviceParams(
        host=host,
        device_type=device_type,
        username=username,
        password=password,
        secret=secret,
        port=port,
    )

    op_id = _log_operation("run_show_commands", host, str(cleaned))
    started = time.time()

    try:
        results = []
        with _connect(params) as conn:
            _enable_if_possible(conn, params)
            for cmd in cleaned:
                output = conn.send_command(
                    cmd,
                    read_timeout=READ_TIMEOUT,
                    strip_prompt=False,
                    strip_command=False
                )
                results.append(f"$ {cmd}\n{_sanitize_output(output)}")

        elapsed = round(time.time() - started, 2)
        logger.info("op=%s completed in %ss", op_id, elapsed)
        return "\n\n" + ("\n\n" + ("=" * 80) + "\n\n").join(results)
    except NetmikoAuthenticationException as exc:
        raise ValueError(f"Autenticación fallida contra {host}: {_friendly_error(exc)}")
    except NetmikoTimeoutException as exc:
        raise ValueError(f"Timeout conectando o leyendo en {host}: {_friendly_error(exc)}")
    except Exception as exc:
        raise ValueError(f"Error ejecutando varios show en {host}: {_friendly_error(exc)}")


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
    Úsala para comandos operacionales como ping, traceroute y otros comandos EXEC
    cuando no exista una tool específica de solo lectura.
    No sirve para aplicar configuración.
    Requiere confirm='LAB' y CISCO_LAB_MODE=true.
    """
    _require_lab_mode()

    if confirm != "LAB":
        raise ValueError("Debes pasar confirm='LAB' para ejecutar comandos abiertos en laboratorio.")

    normalized = _normalize_command(command)
    if not normalized:
        raise ValueError("El comando no puede estar vacío.")

    _ensure_exec_not_denied(normalized)

    params = DeviceParams(
        host=host,
        device_type=device_type,
        username=username,
        password=password,
        secret=secret,
        port=port,
    )

    op_id = _log_operation("run_exec_command", host, normalized)
    started = time.time()

    try:
        output = _run_exec_command(params, normalized)
        elapsed = round(time.time() - started, 2)
        logger.info("op=%s completed in %ss", op_id, elapsed)
        return output
    except NetmikoAuthenticationException as exc:
        raise ValueError(f"Autenticación fallida contra {host}: {_friendly_error(exc)}")
    except NetmikoTimeoutException as exc:
        raise ValueError(f"Timeout conectando o ejecutando en {host}: {_friendly_error(exc)}")
    except Exception as exc:
        raise ValueError(f"Error ejecutando comando EXEC en {host}: {_friendly_error(exc)}")


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
    No sirve para aplicar configuración.
    Requiere confirm='LAB' y CISCO_LAB_MODE=true.
    """
    _require_lab_mode()

    if confirm != "LAB":
        raise ValueError("Debes pasar confirm='LAB' para ejecutar comandos abiertos en laboratorio.")

    cleaned = []
    for cmd in commands:
        normalized = _normalize_command(cmd)
        if normalized:
            _ensure_exec_not_denied(normalized)
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

    op_id = _log_operation("run_exec_commands", host, str(cleaned))
    started = time.time()

    try:
        results = []
        with _connect(params) as conn:
            _enable_if_possible(conn, params)

            for cmd in cleaned:
                output = conn.send_command_timing(
                    cmd,
                    strip_prompt=False,
                    strip_command=False
                )
                results.append(f"$ {cmd}\n{_sanitize_output(output)}")

        elapsed = round(time.time() - started, 2)
        logger.info("op=%s completed in %ss", op_id, elapsed)
        return "\n\n" + ("\n\n" + ("-" * 80) + "\n\n").join(results)
    except NetmikoAuthenticationException as exc:
        raise ValueError(f"Autenticación fallida contra {host}: {_friendly_error(exc)}")
    except NetmikoTimeoutException as exc:
        raise ValueError(f"Timeout conectando o ejecutando en {host}: {_friendly_error(exc)}")
    except Exception as exc:
        raise ValueError(f"Error ejecutando comandos EXEC en {host}: {_friendly_error(exc)}")


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
    Esta tool es para modificar configuración, no para consultar running-config ni usar comandos show.
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

    _ensure_config_not_denied(cleaned)

    params = DeviceParams(
        host=host,
        device_type=device_type,
        username=username,
        password=password,
        secret=secret,
        port=port,
    )

    op_id = _log_operation("run_config_commands", host, f"lines={cleaned} save={save}")
    started = time.time()

    try:
        with _connect(params) as conn:
            _enable_if_possible(conn, params)

            result = conn.send_config_set(cleaned)
            result = _sanitize_output(result)

            save_output = ""
            if save:
                if hasattr(conn, "save_config"):
                    save_output = conn.save_config()
                    save_output = _sanitize_output(save_output)
                else:
                    save_output = "El driver actual no soporta save_config()."

        elapsed = round(time.time() - started, 2)
        logger.info("op=%s completed in %ss", op_id, elapsed)

        if save:
            return f"{result}\n\n--- SAVE ---\n{save_output}"
        return result
    except NetmikoAuthenticationException as exc:
        raise ValueError(f"Autenticación fallida contra {host}: {_friendly_error(exc)}")
    except NetmikoTimeoutException as exc:
        raise ValueError(f"Timeout conectando o configurando en {host}: {_friendly_error(exc)}")
    except Exception as exc:
        raise ValueError(f"Error aplicando configuración en {host}: {_friendly_error(exc)}")


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
    Obtiene información base del equipo para preguntas en lenguaje natural.
    Devuelve un conjunto de comandos de inventario y estado.
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

    op_id = _log_operation("get_device_facts", host, str(commands))
    started = time.time()

    try:
        results = []
        with _connect(params) as conn:
            _enable_if_possible(conn, params)

            for cmd in commands:
                try:
                    output = conn.send_command(cmd, read_timeout=READ_TIMEOUT)
                    output = _sanitize_output(output)
                except Exception as exc:
                    output = f"ERROR ejecutando '{cmd}': {_friendly_error(exc)}"
                results.append(f"$ {cmd}\n{output}")

        elapsed = round(time.time() - started, 2)
        logger.info("op=%s completed in %ss", op_id, elapsed)

        return "\n\n" + ("\n\n" + ("=" * 80) + "\n\n").join(results)
    except NetmikoAuthenticationException as exc:
        raise ValueError(f"Autenticación fallida contra {host}: {_friendly_error(exc)}")
    except NetmikoTimeoutException as exc:
        raise ValueError(f"Timeout conectando o leyendo en {host}: {_friendly_error(exc)}")
    except Exception as exc:
        raise ValueError(f"Error obteniendo facts en {host}: {_friendly_error(exc)}")


if __name__ == "__main__":
    mcp.run()
