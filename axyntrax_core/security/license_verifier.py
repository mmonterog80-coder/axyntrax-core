"""
Módulo de Licenciamiento Criptográfico Anti-Piratería (Inspirado en OWASP MASTG).
Erradica la dependencia de booleanos locales ("is_premium = true").
Verifica licencias firmadas criptográficamente con control de expiración,
límite de máquinas y huella digital del dispositivo (Device Fingerprint).
"""
import base64
import hashlib
import hmac
import json
import time
from typing import Any


class LicenseSecurityError(Exception):
    """Excepción lanzada cuando una licencia es inválida, adulterada o expirada."""


class LicenseVerifier:
    def __init__(self, signing_key: bytes):
        """
        Inicializa el verificador con la clave simétrica de firma HMAC del sistema.
        """
        self._signing_key = signing_key

    def generate_license_token(self, company_id: str, plan: str, max_assets: int, 
                               device_fingerprint: str, duration_days: int = 30) -> str:
        """
        Generador del lado servidor: emite una licencia firmada criptográficamente.
        """
        expires_at = int(time.time()) + (duration_days * 86400)
        payload = {
            "cid": company_id,
            "plan": plan,
            "max_assets": max_assets,
            "dfp": hashlib.sha256(device_fingerprint.encode()).hexdigest()[:16],
            "exp": expires_at,
            "nonce": base64.b64encode(hashlib.sha256(str(time.time()).encode()).digest()[:8]).decode()
        }
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8")
        
        signature = hmac.new(self._signing_key, payload_bytes, hashlib.sha256).digest()
        sig_b64 = base64.urlsafe_b64encode(signature).decode("utf-8")
        
        return f"{payload_b64}.{sig_b64}"

    def verify_license(self, token: str, expected_company_id: str, 
                       current_device_fingerprint: str) -> tuple[bool, dict[str, Any]]:
        """
        Verificación del lado cliente/nodo:
        1. Comprueba integridad del hash (anti-tamper / anti-cracking).
        2. Valida expiración temporal.
        3. Valida vinculación con el dispositivo físico.
        """
        try:
            parts = token.split(".")
            if len(parts) != 2:
                raise LicenseSecurityError("Formato de licencia inválido.")
            
            payload_b64, sig_b64 = parts
            payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
            expected_sig = hmac.new(self._signing_key, payload_bytes, hashlib.sha256).digest()
            provided_sig = base64.urlsafe_b64decode(sig_b64.encode("utf-8"))
            
            # Comparación en tiempo constante para mitigar ataques de temporización (Timing Attacks)
            if not hmac.compare_digest(expected_sig, provided_sig):
                raise LicenseSecurityError("Firma criptográfica inválida: licencia adulterada.")
            
            payload = json.loads(payload_bytes.decode("utf-8"))
            
            # Validación de empresa
            if payload.get("cid") != expected_company_id:
                raise LicenseSecurityError("La licencia no corresponde a esta organización.")
            
            # Validación de dispositivo
            expected_dfp = hashlib.sha256(current_device_fingerprint.encode()).hexdigest()[:16]
            if payload.get("dfp") != expected_dfp:
                raise LicenseSecurityError("Dispositivo no autorizado para esta licencia.")
            
            # Validación de expiración
            if time.time() > payload.get("exp", 0):
                raise LicenseSecurityError("Licencia expirada.")
            
            return True, payload

        except Exception as e:
            if isinstance(e, LicenseSecurityError):
                raise
            raise LicenseSecurityError(f"Error de verificación: {e!s}")
