# Cisco CLI MCP

**MCP (Model Context Protocol)** server for running operational commands on Cisco devices using **Netmiko** and a CSV inventory.

This project is designed to expose simple, controlled MCP tools for:

- listing device inventory
- running `show` commands
- gathering basic device facts
- running EXEC commands in a lab environment
- applying configuration in a lab environment

The current implementation is based on `FastMCP`, `Netmiko`, environment variables, and device resolution from an `inventory.csv` file.

## Features

- Device inventory managed through CSV.
- Device resolution by **logical hostname**.
- Default credentials supported from `.env`.
- Strict validation for `show` commands.
- Separate lab mode for unrestricted commands and configuration changes.
- Output returned in preformatted blocks to preserve columns, line breaks, and CLI formatting.

## Requirements

- Python 3.10 or later
- IP/SSH access to Cisco devices
- Valid credentials
- An MCP-compatible environment that supports Python servers

## Dependencies

Dependencies observed in the source code:

- `python-dotenv`
- `pydantic`
- `netmiko`
- `mcp`

Suggested installation:

```bash
python -m venv .venv
source .venv/bin/activate
pip install python-dotenv pydantic netmiko mcp
```

## Expected Project Structure

```text
.
├── server.py
├── .env
└── inventory.csv
```

## Environment Variables

The server loads its configuration from `.env` using `load_dotenv()`.

Supported variables:

| Variable | Description | Default value |
|---|---|---|
| `CISCO_DEFAULT_DEVICE_TYPE` | Default Netmiko driver | `cisco_ios` |
| `CISCO_USERNAME` | Default SSH username | `None` |
| `CISCO_PASSWORD` | Default SSH password | `None` |
| `CISCO_ENABLE_SECRET` | Default enable secret | `None` |
| `CISCO_INVENTORY_CSV` | Path to the inventory CSV file | `inventory.csv` |
| `CISCO_LAB_MODE` | Enables unrestricted commands and config changes | `false` |
| `CISCO_READ_TIMEOUT` | Timeout for `send_command()` | `120` |

### `.env` Example

```dotenv
CISCO_DEFAULT_DEVICE_TYPE=cisco_ios
CISCO_USERNAME=admin
CISCO_PASSWORD=SuperSecretPassword
CISCO_ENABLE_SECRET=MyEnableSecret
CISCO_INVENTORY_CSV=inventory.csv
CISCO_LAB_MODE=false
CISCO_READ_TIMEOUT=120
```

## CSV Inventory

The server resolves the `host` parameter as a **logical hostname** defined in the CSV, not as a direct IP address. Internally, that hostname is translated into the device IP and the rest of the connection parameters.

Required columns:

- `hostname`
- `ip`

Optional columns:

- `port`
- `device_type`
- `username`
- `password`
- `secret`

### `inventory.csv` Example

```csv
hostname,ip,port,device_type,username,password,secret
R1,192.168.1.10,22,cisco_ios,admin,password123,enable123
R2,192.168.1.11,22,cisco_ios,admin,password123,enable123
SW1,192.168.1.20,22,cisco_ios,admin,password123,enable123
```

### Inventory Rules

- If the file does not exist, the server returns an error.
- If required columns are missing, the server returns an error.
- If duplicate hostnames are found, the server returns an error.
- If a row is missing `hostname` or `ip`, it is ignored with a log warning.
- If an optional column is not defined, the default values from `.env` are used when available.

## Operational Safety

### `show` Commands

The `run_show_command` tool only accepts commands that:

- are not empty
- start with `show `
- only use the following filters after `|`:
  - `include`
  - `exclude`
  - `begin`
  - `section`

Valid examples:

```text
show version
show ip interface brief
show running-config | section interface
show interfaces | include line protocol
```

Rejected examples:

```text
conf t
reload
write memory
show running-config | redirect flash:backup.txt
```

### Lab Mode

The tools that run unrestricted commands or configuration changes require two conditions:

1. `CISCO_LAB_MODE=true`
2. `confirm="LAB"`

This applies to:

- `run_exec_command`
- `run_exec_commands`
- `run_config_commands`

## Available MCP Tools

### `list_inventory`

Lists the devices available in the CSV inventory.

**Parameters:**

- `inventory_csv` (optional)

**Typical use cases:**

- checking which devices are loaded
- validating that the inventory is available

---

### `run_show_command`

Runs a valid `show` command on a Cisco device.

**Main parameters:**

- `host`: logical hostname defined in the CSV
- `command`: `show` command
- `device_type` (optional)
- `username` (optional)
- `password` (optional)
- `secret` (optional)
- `port` (optional)
- `inventory_csv` (optional)

**Examples:**

```json
{
  "host": "R1",
  "command": "show version"
}
```

```json
{
  "host": "SW1",
  "command": "show running-config | section interface"
}
```

---

### `get_device_facts`

Collects basic device information by running several commands:

- `show version`
- `show ip interface brief`
- `show inventory`
- `show clock`

**Main parameters:**

- `host`
- optional connection and inventory parameters

**Example:**

```json
{
  "host": "R1"
}
```

---

### `run_exec_command`

Runs an unrestricted EXEC/operational command on a lab device.

**Requirements:**

- `CISCO_LAB_MODE=true`
- `confirm="LAB"`

**Example:**

```json
{
  "host": "R1",
  "command": "ping 8.8.8.8",
  "confirm": "LAB"
}
```

---

### `run_exec_commands`

Runs multiple EXEC/operational commands in batch mode.

**Requirements:**

- `CISCO_LAB_MODE=true`
- `confirm="LAB"`

**Example:**

```json
{
  "host": "R1",
  "commands": [
    "terminal length 0",
    "show ip route",
    "show arp"
  ],
  "confirm": "LAB"
}
```

---

### `run_config_commands`

Applies configuration lines on a Cisco lab device.

**Requirements:**

- `CISCO_LAB_MODE=true`
- `confirm="LAB"`

**Highlighted parameters:**

- `config_lines`: list of configuration lines
- `save`: saves the configuration if the driver supports `save_config()`

**Example:**

```json
{
  "host": "R1",
  "config_lines": [
    "interface Loopback100",
    "description MCP_TEST",
    "ip address 10.100.100.1 255.255.255.255"
  ],
  "confirm": "LAB",
  "save": false
}
```

## Running the Server

The current implementation starts the server with:

```python
if __name__ == "__main__":
    mcp.run()
```

So a simple way to run it is:

```bash
python server.py
```

## Connection Flow

The internal flow is:

1. resolve the logical hostname in the CSV inventory
2. apply optional overrides (`device_type`, `username`, `password`, `secret`, `port`)
3. validate credentials
4. connect to the device via `Netmiko`
5. if `secret` exists, attempt to enter enable mode
6. execute the command and return the output wrapped in a preformatted text block

## Returned Output

All tools return text wrapped in blocks like this:

````text
```text
...device output...
```
````

This helps preserve:

- columns
- spacing
- line breaks
- original CLI formatting

## Logs

The server uses `logging` at `INFO` level and writes to `stderr`. It also logs warnings for lab operations, for example:

- unrestricted EXEC command execution
- batch command execution
- configuration changes

## Current Limitations

- The inventory is CSV-only.
- There is no segmentation by access profiles or roles.
- `run_show_command` intentionally restricts the allowed filters.
- Unrestricted commands and configuration changes depend on lab mode.
- Validation focuses on basic operational safety, not advanced authorization or RBAC.

## Recommendations

### Recommended Usage

- use `run_show_command` for read-only observability and troubleshooting
- reserve `run_exec_command`, `run_exec_commands`, and `run_config_commands` for lab environments
- keep `CISCO_LAB_MODE=false` in production environments
- store credentials carefully and restrict access to `.env`
- use a minimal and controlled inventory

### Possible Improvements

- support for YAML inventory or NetBox integration
- allowlists per tool
- structured change auditing
- multi-vendor support
- finer validation for EXEC/config commands
- automated tests and MCP client examples

## Short Project Description

> Cisco CLI MCP is an MCP server for operating Cisco devices over SSH using Netmiko, a CSV inventory, and simple safety controls to separate `show` queries from lab actions.