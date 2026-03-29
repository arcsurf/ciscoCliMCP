# Cisco CLI MCP

Servidor **MCP (Model Context Protocol)** para ejecutar comandos de operación en equipos Cisco usando **Netmiko** y un inventario CSV.

El proyecto está pensado para exponer herramientas MCP simples y controladas para:

- consultar inventario de dispositivos
- ejecutar comandos `show`
- obtener información base del dispositivo
- ejecutar comandos EXEC en laboratorio
- aplicar configuración en laboratorio

La implementación actual está basada en `FastMCP`, `Netmiko`, variables de entorno y resolución de dispositivos desde un archivo `inventory.csv`. fileciteturn0file0

## Características

- Inventario de equipos mediante CSV.
- Resolución de dispositivos por **hostname lógico**.
- Soporte de credenciales por defecto desde `.env`.
- Validación estricta para comandos `show`.
- Modo laboratorio separado para comandos abiertos y configuración.
- Salida devuelta en bloques preformateados para preservar columnas, saltos de línea y formato de CLI. fileciteturn0file0

## Requisitos

- Python 3.10 o superior
- Acceso IP/SSH a los dispositivos Cisco
- Credenciales válidas
- Un entorno MCP compatible con servidores Python

## Dependencias

Dependencias observadas en el código fuente:

- `python-dotenv`
- `pydantic`
- `netmiko`
- `mcp`

Instalación sugerida:

```bash
python -m venv .venv
source .venv/bin/activate
pip install python-dotenv pydantic netmiko mcp
```

## Estructura esperada

```text
.
├── server.py
├── .env
└── inventory.csv
```

## Variables de entorno

El servidor carga configuración desde `.env` usando `load_dotenv()`. fileciteturn0file0

Variables soportadas:

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `CISCO_DEFAULT_DEVICE_TYPE` | Driver por defecto de Netmiko | `cisco_ios` |
| `CISCO_USERNAME` | Usuario SSH por defecto | `None` |
| `CISCO_PASSWORD` | Contraseña SSH por defecto | `None` |
| `CISCO_ENABLE_SECRET` | Enable secret por defecto | `None` |
| `CISCO_INVENTORY_CSV` | Ruta del inventario CSV | `inventory.csv` |
| `CISCO_LAB_MODE` | Habilita comandos abiertos y configuración | `false` |
| `CISCO_READ_TIMEOUT` | Timeout para `send_command()` | `120` |

### Ejemplo de `.env`

```dotenv
CISCO_DEFAULT_DEVICE_TYPE=cisco_ios
CISCO_USERNAME=admin
CISCO_PASSWORD=SuperSecretPassword
CISCO_ENABLE_SECRET=MyEnableSecret
CISCO_INVENTORY_CSV=inventory.csv
CISCO_LAB_MODE=false
CISCO_READ_TIMEOUT=120
```

## Inventario CSV

El servidor resuelve el parámetro `host` como un **hostname lógico** definido en el CSV, no como una IP directa. Internamente, ese hostname se traduce a la IP y demás parámetros del dispositivo. fileciteturn0file0

Columnas obligatorias:

- `hostname`
- `ip`

Columnas opcionales:

- `port`
- `device_type`
- `username`
- `password`
- `secret`

### Ejemplo de `inventory.csv`

```csv
hostname,ip,port,device_type,username,password,secret
R1,192.168.1.10,22,cisco_ios,admin,password123,enable123
R2,192.168.1.11,22,cisco_ios,admin,password123,enable123
SW1,192.168.1.20,22,cisco_ios,admin,password123,enable123
```

### Reglas del inventario

- Si el archivo no existe, el servidor devuelve error.
- Si faltan columnas obligatorias, devuelve error.
- Si hay hostnames duplicados, devuelve error.
- Si una fila no tiene `hostname` o `ip`, se ignora con warning de log.
- Si una columna opcional no está definida, se usan los valores por defecto del `.env` cuando existan. fileciteturn0file0

## Seguridad operativa

### Comandos `show`

La tool `run_show_command` solo acepta comandos que:

- no estén vacíos
- empiecen por `show `
- usen únicamente estos filtros tras `|`:
  - `include`
  - `exclude`
  - `begin`
  - `section` fileciteturn0file0

Ejemplos válidos:

```text
show version
show ip interface brief
show running-config | section interface
show interfaces | include line protocol
```

Ejemplos rechazados:

```text
conf t
reload
write memory
show running-config | redirect flash:backup.txt
```

### Modo laboratorio

Las tools que ejecutan comandos abiertos o cambios de configuración requieren dos condiciones:

1. `CISCO_LAB_MODE=true`
2. pasar `confirm="LAB"`

Esto aplica a:

- `run_exec_command`
- `run_exec_commands`
- `run_config_commands` fileciteturn0file0

## Tools MCP disponibles

### `list_inventory`

Lista los equipos disponibles en el inventario CSV.

**Parámetros:**

- `inventory_csv` (opcional)

**Uso esperado:**

- ver los equipos cargados
- validar que el inventario esté disponible

---

### `run_show_command`

Ejecuta un comando `show` válido en un dispositivo Cisco.

**Parámetros principales:**

- `host`: hostname lógico definido en el CSV
- `command`: comando `show`
- `device_type` (opcional)
- `username` (opcional)
- `password` (opcional)
- `secret` (opcional)
- `port` (opcional)
- `inventory_csv` (opcional)

**Ejemplos:**

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

Obtiene información base del equipo ejecutando varios comandos:

- `show version`
- `show ip interface brief`
- `show inventory`
- `show clock` fileciteturn0file0

**Parámetros principales:**

- `host`
- parámetros opcionales de conexión e inventario

**Ejemplo:**

```json
{
  "host": "R1"
}
```

---

### `run_exec_command`

Ejecuta un comando EXEC/operacional abierto en un equipo de laboratorio.

**Requisitos:**

- `CISCO_LAB_MODE=true`
- `confirm="LAB"`

**Ejemplo:**

```json
{
  "host": "R1",
  "command": "ping 8.8.8.8",
  "confirm": "LAB"
}
```

---

### `run_exec_commands`

Ejecuta varios comandos EXEC/operacionales en lote.

**Requisitos:**

- `CISCO_LAB_MODE=true`
- `confirm="LAB"`

**Ejemplo:**

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

Aplica líneas de configuración en un dispositivo Cisco de laboratorio.

**Requisitos:**

- `CISCO_LAB_MODE=true`
- `confirm="LAB"`

**Parámetros destacados:**

- `config_lines`: lista de líneas de configuración
- `save`: guarda configuración si el driver soporta `save_config()`

**Ejemplo:**

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

## Ejecución del servidor

La implementación actual arranca el servidor con:

```python
if __name__ == "__main__":
    mcp.run()
```

Por tanto, una forma simple de ejecutarlo es:

```bash
python server.py
```

## Comportamiento de conexión

El flujo interno es el siguiente:

1. se resuelve el hostname lógico en el inventario CSV
2. se completan overrides opcionales (`device_type`, `username`, `password`, `secret`, `port`)
3. se validan credenciales
4. se conecta al dispositivo vía `Netmiko`
5. si existe `secret`, intenta entrar en modo enable
6. ejecuta el comando y devuelve la salida formateada en bloque de texto preformateado fileciteturn0file0

## Salida devuelta

Todas las tools devuelven texto encapsulado en bloques tipo:

```text
```text
...salida del equipo...
```
```

Esto ayuda a preservar:

- columnas
- espaciado
- saltos de línea
- formato original de CLI fileciteturn0file0

## Logs

El servidor usa `logging` con nivel `INFO` y escribe a `stderr`. Además, registra advertencias para operaciones de laboratorio, por ejemplo:

- ejecución de comandos EXEC abiertos
- ejecución de lotes
- aplicación de configuración fileciteturn0file0

## Limitaciones actuales

- El inventario se basa únicamente en CSV.
- No hay segmentación por perfiles o roles de acceso.
- `run_show_command` restringe intencionadamente los filtros permitidos.
- Los comandos abiertos y de configuración dependen del modo laboratorio.
- La validación se centra en seguridad básica operativa, no en autorización avanzada o RBAC. Esta conclusión se infiere del código actual. fileciteturn0file0

## Recomendaciones

### Uso recomendado

- usar `run_show_command` para observabilidad y troubleshooting de solo lectura
- reservar `run_exec_command`, `run_exec_commands` y `run_config_commands` para laboratorios
- mantener `CISCO_LAB_MODE=false` en entornos productivos
- almacenar credenciales con cuidado y limitar el acceso al `.env`
- usar un inventario mínimo y controlado

### Mejoras posibles

- soporte para inventario YAML o integración con NetBox
- listas de comandos permitidos por tool
- auditoría estructurada de cambios
- soporte para múltiples vendors
- validación más fina de comandos EXEC/config
- tests automáticos y ejemplos de cliente MCP

## Ejemplo de descripción breve del proyecto

> Cisco CLI MCP es un servidor MCP para operar equipos Cisco por SSH usando Netmiko, inventario CSV y controles simples de seguridad para separar consultas `show` de acciones de laboratorio.

## Licencia

Añade aquí la licencia real del repositorio, por ejemplo MIT, Apache-2.0 o la que corresponda.

## Estado del README

Este README fue redactado según la implementación observable en `server.py`.