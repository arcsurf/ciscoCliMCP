import re

from inventory import get_device_from_inventory
from connection import run_commands
from models import DiagnosticResult


DIAGNOSTIC_PLAYBOOKS = {
    "generic_issue": [
        "show clock",
        "show version",
        "show logging | last 100",
        "show ip interface brief",
        "show interfaces",
        "show processes cpu sorted",
    ],
    "interface_issue": [
        "show clock",
        "show logging | include LINEPROTO|LINK|UPDOWN|ERR|DUPLEX|CRC",
        "show ip interface brief",
        "show interfaces {interface}",
        "show interfaces {interface} counters errors",
    ],
    "routing_issue": [
        "show ip route",
        "show ip cef summary",
        "show arp",
        "show logging | include ROUTE|OSPF|BGP|EIGRP",
    ],
    "logging_issue": [
        "show logging | last 200",
        "show clock",
        "show logging",
    ],
}


def classify_symptom(symptom: str, scope: str | None = None) -> str:
    if scope:
        return scope

    s = symptom.lower()

    if any(x in s for x in ["interfaz", "interface", "puerto", "link", "crc", "duplex", "down", "flap"]):
        return "interface_issue"
    if any(x in s for x in ["ruta", "routing", "ospf", "bgp", "eigrp"]):
        return "routing_issue"
    if any(x in s for x in ["log", "logs", "syslog", "mensaje"]):
        return "logging_issue"

    return "generic_issue"


ERROR_PATTERNS = [
    (re.compile(r'CRC|input error|output error', re.I), "Se observan errores físicos o de capa 2."),
    (re.compile(r'line protocol is down', re.I), "Hay una interfaz con protocolo caído."),
    (re.compile(r'%LINK-|%LINEPROTO-', re.I), "Se detectan eventos de cambio de estado en interfaces."),
    (re.compile(r'TRACEBACK|crash|reload', re.I), "Hay indicios de fallo severo o reinicio."),
]


def extract_findings(outputs: dict[str, str]) -> list[str]:
    findings = []

    for cmd, text in outputs.items():
        for pattern, message in ERROR_PATTERNS:
            if pattern.search(text):
                findings.append(f"{message} [fuente: {cmd}]")

    if not findings:
        findings.append("No se detectaron patrones evidentes en la revisión inicial.")

    return findings


def estimate_severity(findings: list[str]) -> str:
    joined = " ".join(findings).lower()
    if any(x in joined for x in ["fallo severo", "reinicio", "crash", "traceback"]):
        return "critical"
    if any(x in joined for x in ["errores físicos", "protocolo caído", "cambio de estado"]):
        return "warning"
    return "info"


def suggest_next_steps(scope: str, findings: list[str]) -> list[str]:
    if scope == "interface_issue":
        return [
            "Revisar cableado, transceiver o puerto remoto.",
            "Validar speed/duplex en ambos extremos.",
            "Correlacionar con syslog remoto si existe.",
        ]
    if scope == "routing_issue":
        return [
            "Validar adyacencias de routing.",
            "Revisar reachability hacia next-hop.",
            "Comparar tabla de rutas esperada vs actual.",
        ]
    return [
        "Revisar eventos recientes en logging.",
        "Comparar con estado habitual del equipo.",
        "Profundizar sobre la zona afectada si el síntoma persiste.",
    ]


def build_summary(scope: str, findings: list[str]) -> str:
    if findings and findings[0] != "No se detectaron patrones evidentes en la revisión inicial.":
        return f"Se encontraron indicios asociados a {scope}."
    return "No se observaron anomalías claras en la revisión inicial."


def register_diag_tools(mcp, defaults):
    @mcp.tool()
    def diagnose_issue(
        host: str,
        symptom: str,
        scope: str | None = None,
        interface: str | None = None,
        inventory_csv: str = defaults["inventory_csv"],
    ) -> dict:
        params = get_device_from_inventory(host, inventory_csv)

        playbook = classify_symptom(symptom, scope)
        commands = DIAGNOSTIC_PLAYBOOKS[playbook]

        rendered = []
        for cmd in commands:
            if "{interface}" in cmd:
                if interface:
                    rendered.append(cmd.format(interface=interface))
            else:
                rendered.append(cmd)

        outputs = run_commands(
            params,
            rendered,
            use_timing=False,
            read_timeout=defaults["read_timeout"],
        )

        findings = extract_findings(outputs)
        severity = estimate_severity(findings)

        return DiagnosticResult(
            host=host,
            symptom=symptom,
            scope=playbook,
            summary=build_summary(playbook, findings),
            severity=severity,
            findings=findings,
            commands_executed=rendered,
            raw_outputs=outputs,
            next_steps=suggest_next_steps(playbook, findings),
        ).model_dump()