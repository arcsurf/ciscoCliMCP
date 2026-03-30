from inventory import load_inventory, get_device_from_inventory
from connection import run_commands, sanitize_output
from validators import validate_show_command


def register_show_tools(mcp, defaults):
    @mcp.tool()
    def list_inventory(inventory_csv: str = defaults["inventory_csv"]) -> str:
        inventory = load_inventory(inventory_csv)

        if not inventory:
            return sanitize_output("El inventario está vacío.")

        lines = []
        for key in sorted(inventory.keys()):
            item = inventory[key]
            lines.append(
                f"{item['hostname']} -> {item['host']} "
                f"(device_type={item['device_type']}, port={item['port']})"
            )

        return sanitize_output("\n".join(lines))

    @mcp.tool()
    def run_show_command(
        host: str,
        command: str,
        inventory_csv: str = defaults["inventory_csv"],
    ) -> str:
        params = get_device_from_inventory(host, inventory_csv)
        normalized = validate_show_command(command)
        outputs = run_commands(params, [normalized], use_timing=False, read_timeout=defaults["read_timeout"])
        return sanitize_output(outputs[normalized])

    @mcp.tool()
    def get_device_facts(
        host: str,
        inventory_csv: str = defaults["inventory_csv"],
    ) -> str:
        params = get_device_from_inventory(host, inventory_csv)

        commands = [
            "show version",
            "show ip interface brief",
            "show inventory",
            "show clock",
        ]

        outputs = run_commands(params, commands, use_timing=False, read_timeout=60)

        results = []
        for cmd in commands:
            results.append(f"$ {cmd}\n{outputs[cmd]}")

        combined = "\n\n" + ("\n\n" + ("=" * 80) + "\n\n").join(results)
        return sanitize_output(combined)