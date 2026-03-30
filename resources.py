def register_resources(mcp):
    @mcp.resource("cisco://troubleshooting-guide")
    def cisco_troubleshooting_guide() -> str:
        return """
Guía de troubleshooting Cisco:

1. Si el usuario pide "revisa si hay un problema":
   - show clock
   - show logging | last 100
   - show ip interface brief
   - show interfaces
   - show processes cpu sorted

2. Si menciona interfaz caída, flaps, CRC, duplex:
   - show ip interface brief
   - show interfaces <if>
   - show interfaces <if> counters errors
   - show logging | include LINEPROTO|LINK|UPDOWN|CRC|ERR

3. Si menciona routing:
   - show ip route
   - show arp
   - show ip cef summary

4. Priorizar siempre comandos show y diagnóstico no destructivo.
5. Usar configuración solo en laboratorio y con confirmación explícita.
"""