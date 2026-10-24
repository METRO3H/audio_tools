"""
core/network/remote_target.py
-----------------------------
Dónde se ejecuta una tool que puede correr en esta PC o en el mediador de la red.

Antes cada `run_*` recibía `remote_host` y `remote_port` por separado y decidía "remoto" con
`host is not None and port is not None` (lo mismo, repetido en cada tool). Ahora viaja un único
`target` dentro de las opciones:

    {"mode": "local"}
    {"mode": "remote", "host": "192.168.1.20", "port": 8765}

Este módulo no habla con el mediador (eso es core/network/mediator_client.py, que no cambia): solo
valida y representa el destino.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RemoteTarget:
    host: str
    port: int

    def __str__(self) -> str:
        return f"{self.host}:{self.port}"


def parse_target(raw) -> RemoteTarget | None:
    """
    `None` = ejecutar en esta PC (ausente o `{"mode": "local"}`); un RemoteTarget = en el mediador.
    Levanta ValueError con un mensaje legible si el destino no es válido.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("La opción «target» debe ser un objeto.")

    unknown = sorted(set(raw) - {"mode", "host", "port"})
    if unknown:
        raise ValueError("«target» tiene claves desconocidas: " + ", ".join(unknown))

    mode = raw.get("mode")
    if mode == "local":
        if "host" in raw or "port" in raw:
            raise ValueError("El destino local no lleva host ni puerto.")
        return None
    if mode != "remote":
        raise ValueError("«target.mode» debe ser «local» o «remote».")

    host = raw.get("host")
    if not isinstance(host, str) or not host.strip():
        raise ValueError("El destino remoto necesita un «host».")

    port = raw.get("port")
    is_number = isinstance(port, (int, float)) and not isinstance(port, bool)
    if not is_number or not float(port).is_integer() or not 1 <= int(port) <= 65535:
        raise ValueError("El «port» del destino remoto debe ser un número entre 1 y 65535.")

    return RemoteTarget(host.strip(), int(port))
