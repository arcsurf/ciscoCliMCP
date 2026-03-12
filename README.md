# Cisco Router MCP Server

Servidor MCP (Model Context Protocol) en Python para conectarse a routers Cisco mediante SSH y ejecutar comandos de red de forma controlada.

Este proyecto está pensado para integrarse con clientes compatibles con MCP y permitir a un modelo o asistente ejecutar herramientas sobre equipos Cisco, inicialmente con foco en comandos de solo lectura (`show`) y, de forma opcional, cambios controlados de configuración.

---

## Características

- Conexión por SSH a routers Cisco
- Ejecución de comandos `show` con lista blanca
- Ejecución de múltiples comandos en una sola llamada
- Recolección de información básica del dispositivo
- Posibilidad de aplicar configuración limitada mediante validaciones
- Separación entre operaciones de lectura y escritura
- Diseño orientado a seguridad y trazabilidad
- Basado en Python, MCP SDK y Netmiko

---

## Casos de uso

- Consultar el estado de un router Cisco desde un cliente MCP
- Obtener información de versión, interfaces y vecinos
- Ejecutar diagnósticos básicos de red
- Integrar acceso a routers dentro de flujos de observabilidad o automatización
- Exponer herramientas seguras para asistentes de IA

---

## Arquitectura

El proyecto utiliza los siguientes componentes:

- **MCP Python SDK** para exponer herramientas compatibles con MCP
- **Netmiko** para la conexión SSH con dispositivos Cisco
- **Pydantic** para validación de parámetros
- **python-dotenv** para cargar credenciales desde variables de entorno

### Tools expuestas

El servidor puede exponer herramientas como:

- `run_show_command`
- `run_show_commands`
- `get_device_facts`
- `push_config` *(opcional y restringida)*

---

## Estructura del proyecto

```text
cisco-mcp/
├── server.py
├── .env
├── .env.example
├── requirements.txt
├── README.md
└── .gitignore



Requisitos

Python 3.10 o superior

Acceso SSH a routers Cisco

Credenciales válidas

Entorno compatible con MCP

Instalación
1. Clonar el repositorio
git clone https://github.com/tu-usuario/cisco-mcp.git
cd cisco-mcp
2. Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate
3. Instalar dependencias
pip install -r requirements.txt

O manualmente:

pip install "mcp>=1.2.0" netmiko pydantic python-dotenv
Configuración

Crea un fichero .env con tus credenciales por defecto:

CISCO_DEFAULT_DEVICE_TYPE=cisco_ios
CISCO_USERNAME=tu_usuario
CISCO_PASSWORD=tu_password
CISCO_ENABLE_SECRET=tu_enable_secret
Ejemplo de .env.example
CISCO_DEFAULT_DEVICE_TYPE=cisco_ios
CISCO_USERNAME=
CISCO_PASSWORD=
CISCO_ENABLE_SECRET=
Ejecución

Para arrancar el servidor MCP localmente:

source .venv/bin/activate
python server.py
Funcionalidades principales
run_show_command

Ejecuta un único comando show permitido sobre un router Cisco.

Ejemplo conceptual:

run_show_command(
    host="10.10.10.1",
    command="show version"
)
run_show_commands

Ejecuta varios comandos show y devuelve el resultado consolidado.

Ejemplo conceptual:

run_show_commands(
    host="10.10.10.1",
    commands=[
        "show version",
        "show ip interface brief",
        "show cdp neighbors"
    ]
)
get_device_facts

Obtiene información base del equipo, como:

versión

interfaces

inventario

reloj del sistema

push_config

Permite aplicar configuración controlada mediante una lista blanca de comandos.

Esta función debe mantenerse deshabilitada o muy restringida en entornos productivos si no existe un control de seguridad adicional.

Seguridad

Este proyecto está diseñado para minimizar riesgos. Aun así, se recomienda seguir estas prácticas:

Permitir únicamente comandos show al inicio

Mantener una lista blanca estricta

Bloquear comandos destructivos

Separar claramente lectura y escritura

No exponer contraseñas en prompts ni en código

Usar variables de entorno o un gestor de secretos

Registrar logs en stderr o fichero, nunca en stdout si se usa STDIO

Validar siempre entradas recibidas desde el cliente MCP

Recomendación

Para una primera versión, usa únicamente herramientas de solo lectura.

Ejemplo de comandos permitidos

Algunos comandos que pueden incluirse en la whitelist inicial:

show version
show ip interface brief
show interfaces status
show inventory
show cdp neighbors
show lldp neighbors
show ip route
show arp
show vlan brief
show spanning-tree
show logging
show users
show clock
Roadmap
Fase 1

 Conexión SSH a routers Cisco

 Ejecución de comandos show

 Validación básica de comandos

 Variables de entorno para credenciales

Fase 2

 Soporte para múltiples plataformas Cisco

 Parsing estructurado de salidas a JSON

 Mejor control de errores

 Transporte HTTP además de STDIO

 Autenticación y autorización

Fase 3

 Integración con observabilidad

 Inventario dinámico de dispositivos

 Caché de resultados

 Validaciones previas y posteriores a cambios

 Generación de diffs de configuración

Desarrollo futuro

Algunas mejoras recomendadas:

soporte para Cisco IOS, IOS-XE y NX-OS

salida estructurada en JSON

integración con Nornir o Napalm

soporte para inventario externo

ejecución asíncrona

control RBAC para acciones sensibles

integración con Vault para secretos

.gitignore recomendado
.venv/
__pycache__/
*.pyc
.env
.idea/
.vscode/
requirements.txt de ejemplo
mcp>=1.2.0
netmiko
pydantic
python-dotenv
Buenas prácticas para Git

No subir el fichero .env

Mantener un .env.example

Versionar cambios de whitelist con cuidado

Documentar cualquier comando nuevo permitido

Revisar seguridad antes de habilitar push_config

Estado del proyecto

Proyecto en fase inicial, orientado a laboratorio, pruebas controladas y evolución hacia automatización segura de infraestructura Cisco a través de MCP.

Licencia

Puedes usar una licencia como MIT para simplificar reutilización:

MIT License
Autor

Ariel Couso
