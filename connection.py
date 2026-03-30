from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

from models import DeviceParams
from validators import validate_credentials


def sanitize_output(text: str | None) -> str:
    if text is None:
        return "```text\n\n```"

    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").rstrip()
    return f"```text\n{cleaned}\n```"


def connect(params: DeviceParams):
    validate_credentials(params.username, params.password)

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


def run_commands(
    params: DeviceParams,
    commands: list[str],
    use_timing: bool = False,
    read_timeout: int = 120,
) -> dict[str, str]:
    results: dict[str, str] = {}

    try:
        with connect(params) as conn:
            try:
                if params.secret:
                    conn.enable()
            except Exception:
                pass

            for cmd in commands:
                if use_timing:
                    output = conn.send_command_timing(
                        cmd,
                        read_timeout=read_timeout,
                        strip_prompt=False,
                        strip_command=False,
                    )
                else:
                    output = conn.send_command(
                        cmd,
                        read_timeout=read_timeout,
                        strip_prompt=False,
                        strip_command=False,
                    )

                results[cmd] = output

    except NetmikoAuthenticationException:
        raise ValueError("Error de autenticación SSH contra el dispositivo.")
    except NetmikoTimeoutException:
        raise ValueError("Timeout de conexión o lectura con el dispositivo.")
    except Exception as exc:
        raise ValueError(f"Error operativo: {exc}")

    return results


def run_config_set(
    params: DeviceParams,
    config_lines: list[str],
    save: bool = False,
) -> tuple[str, str]:
    try:
        with connect(params) as conn:
            if params.secret:
                conn.enable()

            result = conn.send_config_set(config_lines)

            save_output = ""
            if save:
                if hasattr(conn, "save_config"):
                    save_output = conn.save_config()
                else:
                    save_output = "El driver actual no soporta save_config()."

            return result, save_output

    except NetmikoAuthenticationException:
        raise ValueError("Error de autenticación SSH contra el dispositivo.")
    except NetmikoTimeoutException:
        raise ValueError("Timeout de conexión o lectura con el dispositivo.")
    except Exception as exc:
        raise ValueError(f"Error operativo: {exc}")