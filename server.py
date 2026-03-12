import os
import re
import sys
import logging
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException
from mcp.server.fastmcp import FastMCP

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("router-mcp")

mcp = FastMCP("Router Helper MCP")

DEFAULT_DEVICE_TYPE = os.getenv("CISCO_DEFAULT_DEVICE_TYPE", "cisco_ios")
DEFAULT_USERNAME = os.getenv("CISCO_USERNAME")
DEFAULT_PASSWORD = os.getenv("CISCO_PASSWORD")
DEFAULT_SECRET = os.getenv("CISCO_ENABLE_SECRET")
READ_TIMEOUT = int(os.getenv("CISCO_READ_TIMEOUT", "120"))

class DeviceParams(BaseModel):
    host: str = Field(..., description="IP o nombre del router")
    device_type: str = Field(DEFAULT_DEVICE_TYPE, description="Tipo de dispositivo Netmiko")
    username: Optional[str] = Field(DEFAULT_USERNAME, description="Usuario SSH")
    password: Optional[str] = Field(DEFAULT_PASSWORD, description="Contraseña SSH")
    secret: Optional[str] = Field(DEFAULT_SECRET, description="Enable secret")
    port: int = Field(22, description="Puerto SSH")

def _normalize(text: str) -> str:
    return " ".join(text.strip().split())

def _validate_credentials(params: DeviceParams):
    if not params.username or not params.password:
        raise ValueError("Faltan credenciales de acceso al router.")

def _connect(params: DeviceParams):
    _validate_credentials(params)
    return ConnectHandler(
        device_type=params.device_type,
        host=params.host,
        username=params.username,
        password=params.password,
        secret=params.secret,
        port=params.port,
        fast_cli=False,
        timeout=READ_TIMEOUT,
        conn_timeout=15,
        auth_timeout=15,
        banner_timeout=15,
    )

def _enable_if_possible(conn, params: DeviceParams):
    if params.secret:
        try:
            conn.enable()
        except Exception:
            pass

def _sanitize_output(text: str) -> str:
    patterns = [
        (re.compile(r"(enable secret\s+\d?\s*)\S+", re.IGNORECASE), r"\1<redacted>"),
        (re.compile(r"(enable password\s+\d?\s*)\S+", re.IGNORECASE), r"\1<redacted>"),
        (re.compile(r"(snmp-server community)\s+\S+", re.IGNORECASE), r"\1 <redacted>"),
    ]
    out = text
    for pattern, repl in patterns:
        out = pattern.sub(repl, out)
    return out

def _get_running_config(params: DeviceParams) -> str:
    with _connect(params) as conn:
        _enable_if_possible(conn, params)
        output = conn.send_command(
            "show running-config",
            read_timeout=READ_TIMEOUT,
            strip_prompt=False,
            strip_command=False,
        )
    return _sanitize_output(output)

def _extract_summary_from_config(config: str) -> str:
    lines = config.splitlines()
    hostname = None
    interfaces = []
    static_routes = []
    ssh_enabled = False

    current_iface = None

    for line in lines:
        raw = line.rstrip()
        stripped = raw.strip()

        if stripped.startswith("hostname "):
            hostname = stripped.replace("hostname ", "", 1)

        if stripped.startswith("ip route "):
            static_routes.append(stripped)

        if "transport input ssh" in stripped or stripped == "ip ssh version 2":
            ssh_enabled = True

        if raw.startswith("interface "):
            current_iface = stripped.replace("interface ", "", 1)
            interfaces.append({"name": current_iface, "ip": None, "shutdown": None})
            continue

        if current_iface and stripped.startswith("ip address "):
            interfaces[-1]["ip"] = stripped.replace("ip address ", "", 1)

        if current_iface and stripped == "shutdown":
            interfaces[-1]["shutdown"] = True
        elif current_iface and stripped == "no shutdown":
            interfaces[-1]["shutdown"] = False

    summary = []
    summary.append("Resumen del router")
    summary.append("------------------")
    summary.append(f"Nombre del equipo: {hostname or 'No identificado en la configuración'}")
    summary.append(f"Acceso SSH detectado: {'Sí' if ssh_enabled else 'No claro en la configuración'}")
    summary.append(f"Interfaces detectadas: {len(interfaces)}")
    summary.append(f"Rutas estáticas detectadas: {len(static_routes)}")

    if interfaces:
        summary.append("")
        summary.append("Interfaces principales:")
        for iface in interfaces[:10]:
            estado = "apagada" if iface["shutdown"] is True else "activa o no indicado"
            ip = iface["ip"] or "sin IP visible"
            summary.append(f"- {iface['name']}: {ip}, estado {estado}")

    if static_routes:
        summary.append("")
        summary.append("Primeras rutas estáticas:")
        for route in static_routes[:5]:
            summary.append(f"- {route}")

    return "\n".join(summary)

@mcp.tool()
def ver_configuracion_router(
    host: str,
    username: Optional[str] = DEFAULT_USERNAME,
    password: Optional[str] = DEFAULT_PASSWORD,
    secret: Optional[str] = DEFAULT_SECRET,
    device_type: str = DEFAULT_DEVICE_TYPE,
    port: int = 22,
) -> str:
    """
    Usa esta herramienta cuando el usuario quiera ver la configuración completa de un router.
    Ejemplos:
    - ver configuración de router 192.168.0.226
    - mostrar la configuración completa del router
    - enséñame la config del router

    Devuelve la configuración real del router indicado.
    """
    params = DeviceParams(
        host=host,
        username=username,
        password=password,
        secret=secret,
        device_type=device_type,
        port=port,
    )

    try:
        return _get_running_config(params)
    except NetmikoAuthenticationException as exc:
        raise ValueError(f"Autenticación fallida en {host}: {exc}")
    except NetmikoTimeoutException as exc:
        raise ValueError(f"Timeout conectando o leyendo en {host}: {exc}")
    except Exception as exc:
        raise ValueError(f"Error obteniendo la configuración del router {host}: {exc}")

@mcp.tool()
def explicar_configuracion_router(
    host: str,
    username: Optional[str] = DEFAULT_USERNAME,
    password: Optional[str] = DEFAULT_PASSWORD,
    secret: Optional[str] = DEFAULT_SECRET,
    device_type: str = DEFAULT_DEVICE_TYPE,
    port: int = 22,
) -> str:
    """
    Usa esta herramienta cuando el usuario quiera una explicación sencilla de cómo está configurado un router.
    Ejemplos:
    - explícame la configuración del router 192.168.0.226
    - resume la configuración del router
    - dime de forma sencilla cómo está montado este router

    Devuelve un resumen en lenguaje natural basado en la configuración real del router.
    """
    params = DeviceParams(
        host=host,
        username=username,
        password=password,
        secret=secret,
        device_type=device_type,
        port=port,
    )

    try:
        config = _get_running_config(params)
        return _extract_summary_from_config(config)
    except NetmikoAuthenticationException as exc:
        raise ValueError(f"Autenticación fallida en {host}: {exc}")
    except NetmikoTimeoutException as exc:
        raise ValueError(f"Timeout conectando o leyendo en {host}: {exc}")
    except Exception as exc:
        raise ValueError(f"Error explicando la configuración del router {host}: {exc}")

if __name__ == "__main__":
    mcp.run()
