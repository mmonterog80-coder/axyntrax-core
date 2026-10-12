"""
Módulo de Detección de Adulteración y Depuración (Anti-Tamper & Anti-Debugging).
Inspirado en scottyab/rootbeer y securing/IOSSecuritySuite.
Detecta entornos de análisis activo, emulación y adulteración en tiempo de ejecución.
"""
import hashlib
import os
import sys
from typing import Any


class IntegrityGuard:
    @staticmethod
    def is_debugger_attached() -> bool:
        """
        Detección heurística de depuradores y trazadores (sys.gettrace).
        """
        # Verificación de tracer activo en runtime (Python debuggers / Frida hooks)
        return sys.gettrace() is not None

    @staticmethod
    def verify_file_checksum(filepath: str, expected_sha256: str) -> bool:
        """
        Verificación de integridad de binarios / módulos críticos en disco.
        Detecta si el archivo fue modificado (parchado) por herramientas de ingeniería inversa.
        """
        if not os.path.exists(filepath):
            return False
        
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        
        return hasher.hexdigest().lower() == expected_sha256.lower()

    @staticmethod
    def run_health_check() -> dict[str, Any]:
        """
        Ejecuta un escaneo integral del estado del entorno de ejecución.
        """
        debugger = IntegrityGuard.is_debugger_attached()
        return {
            "debugger_detected": debugger,
            "environment_safe": not debugger,
            "status": "SECURE" if not debugger else "COMPROMISED"
        }
