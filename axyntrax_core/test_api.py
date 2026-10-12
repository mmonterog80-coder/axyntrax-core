"""
Suite de Pruebas de Integración y API REST para Axyntrax 2.0.
Verifica endpoints de salud, horómetro, combustible y órdenes de trabajo.
"""
import unittest

from starlette.testclient import TestClient

from axyntrax_core.api import DB_PARTS, app, startup_populate


class TestAxyntraxAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        startup_populate()
        cls.client = TestClient(app)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "OPERATIONAL")
        self.assertEqual(data["security"]["status"], "SECURE")

    def test_dashboard_endpoint(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn("AXYNTRAX", response.text)
        self.assertIn("Disponibilidad Física", response.text)

    def test_record_horometer_success(self):
        payload = {
            "equipment_id": "EQ-CAT-320D-01",
            "company_id": "COMP-AXYNTRAX-MINING",
            "operator_id": "OP-OPERATOR-01",
            "reading_hours": 1025.0
        }
        response = self.client.post("/api/v1/horometer/record", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["current_horometer"], 1025.0)
        self.assertEqual(data["maintenance_projection"]["service_type"], "PM1_250H")

    def test_record_horometer_fraud_rejected(self):
        # Intento de retroceder el horómetro por debajo de 1025.0
        payload = {
            "equipment_id": "EQ-CAT-320D-01",
            "company_id": "COMP-AXYNTRAX-MINING",
            "operator_id": "OP-FRAUDE",
            "reading_hours": 950.0
        }
        response = self.client.post("/api/v1/horometer/record", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Rechazado por Antifraude", data["detail"])

    def test_get_maintenance_status(self):
        response = self.client.get("/api/v1/equipment/EQ-CAT-320D-01/maintenance-status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["equipment_id"], "EQ-CAT-320D-01")
        self.assertIn("maintenance", data)

    def test_record_fuel_overfill_rejected(self):
        # Capacidad de tanque es 400L, intentan cargar 600L
        payload = {
            "equipment_id": "EQ-CAT-320D-01",
            "company_id": "COMP-AXYNTRAX-MINING",
            "liters_loaded": 600.0,
            "current_horometer": 1025.0,
            "fuel_cost_total": 2400.0
        }
        response = self.client.post("/api/v1/fuel/record", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Rechazado por Anomalía de Combustible", data["detail"])

    def test_complete_work_order_and_deduct_stock(self):
        initial_stock = DB_PARTS["PART-OIL-FILTER-01"].stock_quantity
        response = self.client.post(
            "/api/v1/work-orders/OT-TEST-001/complete",
            params={
                "closing_horometer": 1026.0,
                "signature_vector": "SIGNATURE_BASE64_STREAM"
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "COMPLETED")
        self.assertEqual(data["total_cost"], 95.0)
        self.assertIsNotNone(data["verification_qr_token"])
        self.assertEqual(data["stock_remaining"], initial_stock - 1)

    def test_sync_batch_endpoint(self):
        payload = {
            "company_id": "COMP-AXYNTRAX-MINING",
            "device_id": "DEV-TABLET-01",
            "actions": [
                {
                    "action_id": "ACT-SYNC-API-01",
                    "action_type": "RECORD_HOROMETER",
                    "company_id": "COMP-AXYNTRAX-MINING",
                    "equipment_id": "EQ-CAT-320D-01",
                    "payload": {"reading_hours": 1030.0},
                    "client_timestamp": "2026-10-12T10:00:00Z",
                    "device_id": "DEV-TABLET-01"
                }
            ]
        }
        response = self.client.post("/api/v1/sync/batch", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["applied_count"], 1)
        self.assertEqual(data["rejected_count"], 0)

    def test_equipment_kpis_endpoint(self):
        response = self.client.get("/api/v1/equipment/EQ-CAT-320D-01/kpis?period_days=30&fuel_cost_total=1500")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("physical_availability_pct", data)
        self.assertIn("cost_per_operating_hour", data)

    def test_culqi_webhook_endpoint_security(self):
        import hashlib
        import hmac

        from axyntrax_core.api import SIGNING_SECRET

        payload = {
            "event": "charge.succeeded",
            "company_id": "COMP-AXYNTRAX-MINING",
            "company_ruc": "20609876543",
            "customer_email": "payments@example.com",
            "plan_name": "Pro",
            "amount_pen": 59.00,
            "currency": "PEN",
            "device_fingerprint": "HWID-TABLET-TEST",
            "payment_method": "yape",
            "culqi_charge_id": "chr_test_59_soles"
        }
        # 1. Con firma inválida -> 403
        bad_response = self.client.post(
            "/api/v1/billing/culqi-webhook",
            json=payload,
            headers={"x-culqi-signature": "FAKE_FORGED_SIGNATURE"}
        )
        self.assertEqual(bad_response.status_code, 403)

        # 2. Con firma legítima -> 200 y emisión automática de factura SUNAT
        from axyntrax_core.billing import WebhookPaymentPayload
        p_obj = WebhookPaymentPayload(**payload)
        raw_bytes = p_obj.model_dump_json().encode("utf-8")
        valid_sig = hmac.new(SIGNING_SECRET, raw_bytes, hashlib.sha256).hexdigest()

        good_response = self.client.post(
            "/api/v1/billing/culqi-webhook",
            json=payload,
            headers={"x-culqi-signature": valid_sig}
        )
        self.assertEqual(good_response.status_code, 200)
        res_data = good_response.json()
        self.assertTrue(res_data["success"])
        self.assertEqual(res_data["sunat_status"], "SIMULATED_ACCEPTED")
        self.assertIsNotNone(res_data["license_token"])


if __name__ == "__main__":
    unittest.main()

