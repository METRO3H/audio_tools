from __future__ import annotations

"""
core/hardware_info.py
----------------------
Snapshot de VRAM de la GPU NVIDIA activa, pensado para poder comparar el
consumo de memoria entre modelos/config de traduccion.

Por ahora solo soporta NVIDIA (via pynvml/NVML) porque es el hardware que
se puede verificar. No hay equivalente confiable y liviano para AMD/Intel
en Windows sin pedirle al usuario que instale drivers/SDKs extra (ROCm es
esencialmente una herramienta Linux/datacenter) — si mas adelante hace
falta soportar otros fabricantes, este es el unico archivo a tocar.

Best-effort en todo momento: si pynvml no esta instalado, no hay GPU
NVIDIA, o falla por cualquier motivo (driver viejo, GPU en uso exclusivo,
etc.), get_vram_snapshot() devuelve None en vez de lanzar una excepcion.
El resto de las estadisticas de una corrida (rendimiento, confiabilidad)
no dependen de esto.

Requiere el paquete "nvidia-ml-py" (pip install nvidia-ml-py) — el import
sigue siendo `import pynvml`, es el nombre de paquete el que cambio hace
un tiempo (el paquete viejo "pynvml" esta deprecado).
"""

from dataclasses import dataclass


@dataclass
class VramSnapshot:
    vendor: str          # "nvidia"
    name: str             # ej. "NVIDIA GeForce RTX 4070"
    used_mb: float
    total_mb: float
    method: str            # "nvml"


def get_vram_snapshot(device_index: int = 0) -> VramSnapshot | None:
    """
    Foto puntual del uso de VRAM del dispositivo NVIDIA `device_index`
    (0 = la GPU principal en la mayoria de los sistemas con una sola GPU
    dedicada). Pensada para llamarse una vez, justo despues de cargar el
    modelo — con llama.cpp/GGUF la memoria queda bastante estable una vez
    que el modelo + KV cache estan asignados, asi que no hace falta
    muestrear picos durante toda la corrida.
    """
    try:
        import pynvml
    except ImportError:
        return None

    try:
        pynvml.nvmlInit()
    except Exception:
        return None

    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(device_index)

        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="ignore")

        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)

        return VramSnapshot(
            vendor="nvidia",
            name=name,
            used_mb=mem.used / (1024 * 1024),
            total_mb=mem.total / (1024 * 1024),
            method="nvml",
        )
    except Exception:
        return None
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass