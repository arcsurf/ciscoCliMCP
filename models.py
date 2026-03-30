from typing import Optional, Literal
from pydantic import BaseModel, Field


class DeviceParams(BaseModel):
    host: str = Field(..., description="IP o hostname real del dispositivo Cisco")
    device_type: str = Field("cisco_ios", description="Ej: cisco_ios, cisco_xe, cisco_nxos")
    username: Optional[str] = Field(None, description="Usuario SSH")
    password: Optional[str] = Field(None, description="Password SSH")
    secret: Optional[str] = Field(None, description="Enable secret si aplica")
    port: int = Field(22, description="Puerto SSH")


class DiagnosticRequest(BaseModel):
    host: str
    symptom: str = Field(..., description="Descripción natural del problema")
    scope: Optional[str] = Field(None, description="interface_issue, routing_issue, logging_issue, etc.")
    interface: Optional[str] = None
    inventory_csv: str = "inventory.csv"


class DiagnosticResult(BaseModel):
    host: str
    symptom: str
    scope: str
    summary: str
    severity: Literal["info", "warning", "critical"]
    findings: list[str]
    commands_executed: list[str]
    raw_outputs: dict[str, str]
    next_steps: list[str]