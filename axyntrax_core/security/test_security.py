"""
Suite de Pruebas Automatizadas de Seguridad y Anti-Piratería.
Valida matemáticamente la resistencia contra adulteración y bypass.
"""
import unittest

from axyntrax_core.security.integrity_guard import IntegrityGuard
from axyntrax_core.security.license_verifier import (
    LicenseSecurityError,
    LicenseVerifier,
)


class TestSecurityAndAntiTamper(unittest.TestCase):
    def setUp(self):
        self.signing_key = b"test-only-dummy-key-not-a-secret-32b"
        self.verifier = LicenseVerifier(self.signing_key)
        self.company_id = "EMP-DEMO-MINING-01"
        self.device_fp = "HWID-TEST-LAPTOP-0001"

    def test_valid_license_passes(self):
        token = self.verifier.generate_license_token(
            company_id=self.company_id,
            plan="Enterprise",
            max_assets=100,
            device_fingerprint=self.device_fp,
            duration_days=30
        )
        is_valid, payload = self.verifier.verify_license(token, self.company_id, self.device_fp)
        self.assertTrue(is_valid)
        self.assertEqual(payload["plan"], "Enterprise")
        self.assertEqual(payload["max_assets"], 100)

    def test_tampered_payload_fails(self):
        # Generar token legítimo para 15 máquinas
        token = self.verifier.generate_license_token(
            company_id=self.company_id,
            plan="Basico",
            max_assets=15,
            device_fingerprint=self.device_fp,
            duration_days=30
        )
        # Atacante intenta modificar el payload para elevar a 9999 máquinas
        parts = token.split(".")
        tampered_payload = parts[0][:-2] + "AA"  # Corromper bytes de base64
        tampered_token = f"{tampered_payload}.{parts[1]}"
        
        with self.assertRaises(LicenseSecurityError):
            self.verifier.verify_license(tampered_token, self.company_id, self.device_fp)

    def test_tampered_signature_fails(self):
        token = self.verifier.generate_license_token(
            company_id=self.company_id,
            plan="Pro",
            max_assets=30,
            device_fingerprint=self.device_fp,
            duration_days=30
        )
        parts = token.split(".")
        fake_signature = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        tampered_token = f"{parts[0]}.{fake_signature}"
        
        with self.assertRaises(LicenseSecurityError) as ctx:
            self.verifier.verify_license(tampered_token, self.company_id, self.device_fp)
        self.assertIn("Firma criptográfica inválida", str(ctx.exception))

    def test_expired_license_fails(self):
        # Token con duración negativa (ya expirado)
        token = self.verifier.generate_license_token(
            company_id=self.company_id,
            plan="Pro",
            max_assets=30,
            device_fingerprint=self.device_fp,
            duration_days=-1
        )
        with self.assertRaises(LicenseSecurityError) as ctx:
            self.verifier.verify_license(token, self.company_id, self.device_fp)
        self.assertIn("Licencia expirada", str(ctx.exception))

    def test_device_fingerprint_mismatch_fails(self):
        token = self.verifier.generate_license_token(
            company_id=self.company_id,
            plan="Pro",
            max_assets=30,
            device_fingerprint=self.device_fp,
            duration_days=30
        )
        attacker_device = "HWID-HACKER-LAPTOP-ROBADA-0000"
        with self.assertRaises(LicenseSecurityError) as ctx:
            self.verifier.verify_license(token, self.company_id, attacker_device)
        self.assertIn("Dispositivo no autorizado", str(ctx.exception))

    def test_integrity_guard_status(self):
        report = IntegrityGuard.run_health_check()
        self.assertIn("environment_safe", report)
        self.assertIn("status", report)

    def test_integrity_guard_debugger_attached_mock(self):
        import sys
        original_trace = sys.gettrace()
        try:
            sys.settrace(lambda *args: None)
            self.assertTrue(IntegrityGuard.is_debugger_attached())
            report = IntegrityGuard.run_health_check()
            self.assertTrue(report["debugger_detected"])
            self.assertFalse(report["environment_safe"])
            self.assertEqual(report["status"], "COMPROMISED")
        finally:
            sys.settrace(original_trace)

    def test_verify_file_checksum(self):
        import hashlib
        import os
        import tempfile
        
        # Test 1: Archivo inexistente
        self.assertFalse(IntegrityGuard.verify_file_checksum("archivo_inexistente_12345.bin", "abc"))

        # Test 2: Archivo existente con hash coincidente
        content = b"TEST INTEGRITY PAYLOAD 2026"
        expected_hash = hashlib.sha256(content).hexdigest()
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(content)
            temp_path = tf.name
        
        try:
            self.assertTrue(IntegrityGuard.verify_file_checksum(temp_path, expected_hash))
            self.assertFalse(IntegrityGuard.verify_file_checksum(temp_path, "hash_invalido_12345"))
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()

