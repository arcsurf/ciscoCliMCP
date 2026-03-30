from inventory import get_device_from_inventory
from connection import run_commands, run_config_set, sanitize_output
from validators import normalize_command, require_lab_mode


def register_config_tools(mcp, defaults):
    @mcp.tool()
    def run_exec_command(
        host: str,
        command: str,
        confirm: str = "LAB",
        inventory_csv: str = defaults["inventory_csv"],
    ) -> str:
        require_lab_mode(defaults["lab_mode"])

        if confirm != "LAB":
            raise ValueError("Debes pasar confirm='LAB' para ejecutar comandos abiertos en laboratorio.")

        normalized = normalize_command(command)
        if not normalized:
            raise ValueError("El comando no puede estar vacío.")

        params = get_device_from_inventory(host, inventory_csv)
        outputs = run_commands(params, [normalized], use_timing=True, read_timeout=defaults["read_timeout"])
        return sanitize_output(outputs[normalized])

    @mcp.tool()
    def run_exec_commands(
        host: str,
        commands: list[str],
        confirm: str = "LAB",
        inventory_csv: str = defaults["inventory_csv"],
    ) -> str:
        require_lab_mode(defaults["lab_mode"])

        if confirm != "LAB":
            raise ValueError("Debes pasar confirm='LAB' para ejecutar comandos abiertos en laboratorio.")

        cleaned = [normalize_command(c) for c in commands if normalize_command(c)]
        if not cleaned:
            raise ValueError("Debes proporcionar al menos un comando válido.")

        params = get_device_from_inventory(host, inventory_csv)
        outputs = run_commands(params, cleaned, use_timing=True, read_timeout=defaults["read_timeout"])

        results = []
        for cmd in cleaned:
            results.append(f"$ {cmd}\n{outputs[cmd]}")

        combined = "\n\n" + ("\n\n" + ("-" * 80) + "\n\n").join(results)
        return sanitize_output(combined)

    @mcp.tool()
    def run_config_commands(
        host: str,
        config_lines: list[str],
        confirm: str = "LAB",
        save: bool = False,
        inventory_csv: str = defaults["inventory_csv"],
    ) -> str:
        require_lab_mode(defaults["lab_mode"])

        if confirm != "LAB":
            raise ValueError("Debes pasar confirm='LAB' para aplicar configuración en laboratorio.")

        cleaned = [normalize_command(c) for c in config_lines if normalize_command(c)]
        if not cleaned:
            raise ValueError("Debes proporcionar al menos una línea de configuración válida.")

        params = get_device_from_inventory(host, inventory_csv)
        result, save_output = run_config_set(params, cleaned, save=save)

        if save:
            return sanitize_output(f"{result}\n\n--- SAVE ---\n{save_output}")

        return sanitize_output(result)