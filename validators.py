ALLOWED_SHOW_FILTERS = {
    "include",
    "exclude",
    "begin",
    "section",
}


def normalize_command(cmd: str) -> str:
    return " ".join(cmd.strip().split())


def validate_show_command(command: str) -> str:
    normalized = normalize_command(command)
    if not normalized:
        raise ValueError("El comando no puede estar vacío.")

    lower_cmd = normalized.lower()

    if not lower_cmd.startswith("show "):
        raise ValueError("Solo se permiten comandos que comiencen por 'show '.")

    if "|" in normalized:
        parts = [p.strip() for p in normalized.split("|")]
        if len(parts) < 2:
            raise ValueError("Sintaxis inválida en el pipe del comando show.")

        for pipe_part in parts[1:]:
            tokens = pipe_part.split()
            keyword = tokens[0].lower() if tokens else ""
            if keyword not in ALLOWED_SHOW_FILTERS:
                raise ValueError(
                    f"Filtro no permitido tras '|': {keyword}. "
                    f"Permitidos: {', '.join(sorted(ALLOWED_SHOW_FILTERS))}"
                )

    return normalized


def validate_credentials(username: str | None, password: str | None):
    if not username or not password:
        raise ValueError("Faltan credenciales: username/password.")


def require_lab_mode(lab_mode: bool):
    if not lab_mode:
        raise ValueError(
            "CISCO_LAB_MODE no está activado. "
            "Define CISCO_LAB_MODE=true en el .env para usar comandos abiertos en laboratorio."
        )