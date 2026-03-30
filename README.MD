# ciscoCliMCP

**MCP (Model Context Protocol)** server for querying information from and executing actions on Cisco devices over **CLI/SSH** using **Netmiko**.

This project is designed for day-to-day operations, troubleshooting, and controlled automation on Cisco routers and switches, with a clear separation between:

- read-only `show` commands
- guided diagnostics
- open CLI commands and configuration changes only in **lab mode**

The server is implemented with `FastMCP`, uses `python-dotenv` for environment-based configuration, and loads devices from a CSV inventory.

## Features

- SSH connectivity to Cisco devices through **Netmiko**
- Device inventory stored in a **CSV** file
- Validation for `show` commands to keep read-only operations non-destructive
- MCP tools for:
  - listing inventory
  - running validated `show` commands
  - collecting device facts
  - running open exec commands
  - applying configuration lines
  - running symptom-based guided diagnostics
- Mandatory **lab mode** for configuration changes or unrestricted CLI commands
- Built-in MCP prompt and troubleshooting resource for Cisco operational analysis

## Project Structure

```text
.
├── connection.py      # SSH connection, command execution, and config handling
├── inventory.py       # CSV inventory loading and validation
├── main.py            # MCP server entry point
├── models.py          # Pydantic models
├── prompts.py         # MCP prompt for Cisco operational analysis
├── resources.py       # MCP troubleshooting resource
├── tools_config.py    # Open exec/configuration tools
├── tools_diag.py      # Guided diagnostic tool
├── tools_show.py      # Read-only show and facts tools
├── validators.py      # Validation logic and guardrails
├── requirements.txt   # Python dependencies
└── run.sh             # Example startup script using mcpo
```

## Requirements

- Python 3.10 or newer recommended
- Network access to the Cisco device over SSH
- Valid device credentials
- A CSV inventory file

Declared dependencies:

- `mcp>=1.2.0`
- `netmiko`
- `pydantic`
- `python-dotenv`

## Installation

```bash
git clone https://github.com/arcsurf/ciscoCliMCP.git
cd ciscoCliMCP
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

The server loads configuration from environment variables through `load_dotenv()`.

| Variable | Description | Default |
|---|---|---|
| `CISCO_DEFAULT_DEVICE_TYPE` | Default Netmiko device type | `cisco_ios` |
| `CISCO_USERNAME` | Default SSH username | none |
| `CISCO_PASSWORD` | Default SSH password | none |
| `CISCO_ENABLE_SECRET` | Default enable secret | none |
| `CISCO_INVENTORY_CSV` | CSV inventory path | `inventory.csv` |
| `CISCO_LAB_MODE` | Enables open commands and config changes | `false` |
| `CISCO_READ_TIMEOUT` | Command read timeout | `120` |

### Example `.env`

```env
CISCO_DEFAULT_DEVICE_TYPE=cisco_ios
CISCO_USERNAME=admin
CISCO_PASSWORD=your_password
CISCO_ENABLE_SECRET=your_enable_secret
CISCO_INVENTORY_CSV=inventory.csv
CISCO_LAB_MODE=false
CISCO_READ_TIMEOUT=120
```

## CSV Inventory Format

The inventory requires at least the `hostname` and `ip` columns. It also supports optional per-device overrides for connection parameters and credentials.

If either `hostname` or `ip` is missing in a row, that row is ignored. If required columns are missing from the CSV header, the loader raises an error.

### Supported Columns

- `hostname` **(required)**
- `ip` **(required)**
- `device_type`
- `port`
- `username`
- `password`
- `secret`

### Example `inventory.csv`

```csv
hostname,ip,device_type,port,username,password,secret
R1,192.168.1.10,cisco_ios,22,admin,lab123,enable123
R2,192.168.1.11,cisco_ios,22,,,
SW1,192.168.1.20,cisco_ios,22,netops,lab123,
```

Notes:

- `hostname` should be unique in the inventory
- If `username`, `password`, or `secret` are empty in the CSV, the server falls back to the default values from the environment when available

## Running the Server

The MCP server entry point is `main.py`, where the tools, resources, and prompts are registered before calling `mcp.run()`.

### Run directly

```bash
source .venv/bin/activate
python3 main.py
```

### Run with `mcpo`

The repository includes a `run.sh` example with the following startup pattern:

```bash
source .venv/bin/activate
mcpo --port 8000 --api-key "cisco" -- python3 main.py
```

## Available MCP Tools

### 1. `list_inventory`
Lists the devices available in the inventory.

**Parameters:**
- `inventory_csv` optional

### 2. `run_show_command`
Runs a validated `show` command against a host from the inventory.

Only commands starting with `show` are allowed.

**Parameters:**
- `host`
- `command`
- `inventory_csv` optional

**Example:**

```json
{
  "host": "R1",
  "command": "show ip interface brief"
}
```

### 3. `get_device_facts`
Collects a basic set of device information using these commands:

- `show version`
- `show ip interface brief`
- `show inventory`
- `show clock`

**Parameters:**
- `host`
- `inventory_csv` optional

### 4. `run_exec_command`
Runs an unrestricted exec command using `send_command_timing`.

This only works when:

- `CISCO_LAB_MODE=true`
- `confirm="LAB"`

**Parameters:**
- `host`
- `command`
- `confirm` must be `LAB`
- `inventory_csv` optional

### 5. `run_exec_commands`
Runs multiple unrestricted exec commands.

This also requires:

- `CISCO_LAB_MODE=true`
- `confirm="LAB"`

**Parameters:**
- `host`
- `commands`
- `confirm`
- `inventory_csv` optional

### 6. `run_config_commands`
Applies configuration lines using `send_config_set`.

It can optionally save the running configuration if `save=true`. This tool is only available in lab mode.

**Parameters:**
- `host`
- `config_lines`
- `confirm`
- `save`
- `inventory_csv` optional

**Example:**

```json
{
  "host": "R1",
  "config_lines": [
    "interface Loopback123",
    "description Configured from MCP",
    "ip address 10.123.123.1 255.255.255.255"
  ],
  "confirm": "LAB",
  "save": false
}
```

### 7. `diagnose_issue`
Runs a diagnostic playbook based on the symptom provided.

The tool classifies the case as one of the following:

- `generic_issue`
- `interface_issue`
- `routing_issue`
- `logging_issue`

It then runs the relevant commands and returns a structured result with:

- summary
- severity (`info`, `warning`, `critical`)
- findings
- commands executed
- raw outputs
- recommended next steps

**Parameters:**
- `host`
- `symptom`
- `scope` optional
- `interface` optional
- `inventory_csv` optional

**Example:**

```json
{
  "host": "R1",
  "symptom": "Interface Gi0/1 is showing CRC errors and flapping",
  "interface": "GigabitEthernet0/1"
}
```

## Guardrails and Safety

### Read-only command validation
The project validates `show` commands to keep normal operational queries non-destructive.

Only commands beginning with `show` are accepted for the read-only tool. Supported pipe operations are limited to:

- `include`
- `exclude`
- `begin`
- `section`

### Lab mode protection
Open exec commands and configuration changes are intentionally restricted.

To use them, you must explicitly enable:

```env
CISCO_LAB_MODE=true
```

And provide the required confirmation value:

```text
LAB
```

This makes risky actions opt-in and helps prevent accidental changes in production environments.

## Typical Use Cases

- Safe operational queries against Cisco routers and switches
- Quick device fact collection for troubleshooting sessions
- Guided diagnostics based on symptoms described in natural language
- Lab automation for CLI testing and configuration workflows
- Controlled MCP integration for network operations experiments

## Example Workflow

1. Create an `inventory.csv` with your devices
2. Configure credentials in `.env`
3. Start the MCP server
4. Use `list_inventory` to confirm the inventory is loaded
5. Run `run_show_command` for safe operational queries
6. Use `get_device_facts` or `diagnose_issue` for troubleshooting
7. Enable lab mode only if you need unrestricted exec commands or configuration changes

## Limitations

- The project is focused on Cisco CLI access over SSH
- Configuration changes are intentionally gated behind lab mode
- Inventory is CSV-based, not backed by a database or dynamic source
- Behavior depends on CLI output patterns and supported Cisco command responses

## License

No license file is currently published in the repository.

If you plan to reuse or redistribute this project, it is a good idea to add an explicit license.

## Contributing

If you want to improve the project, useful contribution areas may include:

- expanding diagnostics coverage
- adding stronger command parsing and validation
- improving test coverage
- adding support for more Cisco platforms or device types
- enhancing inventory and credential management

## Project stage

- PoC