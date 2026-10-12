"""
Suite de Pruebas Unitarias para Facturación Automática SUNAT y KPIs de Flota.
Demuestra la precisión tributaria y el cálculo de confiabilidad industrial.
"""
import hashlib
import hmac
import unittest

from axyntrax_core.billing import BillingEngine, WebhookPaymentPayload
from axyntrax_core.kpi_engine import KPIEngine
from axyntrax_core.models import Equipment, PlanType, WorkOrder, WorkOrderStatus


class TestBillingAndKPI(unittest.TestCase):
    def setUp(self):
        self.secret_key = b"test-only-dummy-key-not-a-secret-32b"
        self.equipment = Equipment(
            id="EQ-CAT-TEST-KPI",
            company_id="COMP-AXYNTRAX",
            name="Caterpillar 320D",
            serial_number="CAT-SN-0099",
            brand="Caterpillar",
            model="320D",
            year=2021,
            current_horometer=2000.0,
            tank_capacity_liters=400.0,
            expected_burn_rate_lph=20.0
        )

    # --- 1. TESTS DE KPIS INDUSTRIALES (SMRP / ISO 14224) ---
    def test_kpi_availability_and_mtbf(self):
        # 3 órdenes preventivas (6h c/u = 18h) y 1 orden correctiva (14h) -> total parada = 32h en 30 días (720h)
        # Disponibilidad esperada: (720 - 32) / 720 = 95.56%
        orders = [
            WorkOrder(
                id="OT-P1", company_id="C1", equipment_id=self.equipment.id,
                plan_type=PlanType.PM1, status=WorkOrderStatus.COMPLETED,
                scheduled_horometer=1250.0, total_cost=250.0
            ),
            WorkOrder(
                id="OT-P2", company_id="C1", equipment_id=self.equipment.id,
                plan_type=PlanType.PM2, status=WorkOrderStatus.COMPLETED,
                scheduled_horometer=1500.0, total_cost=400.0
            ),
            WorkOrder(
                id="OT-P3", company_id="C1", equipment_id=self.equipment.id,
                plan_type=PlanType.PM1, status=WorkOrderStatus.COMPLETED,
                scheduled_horometer=1750.0, total_cost=250.0
            ),
            WorkOrder(
                id="OT-C1", company_id="C1", equipment_id=self.equipment.id,
                plan_type=PlanType.CORRECTIVE, status=WorkOrderStatus.COMPLETED,
                scheduled_horometer=1900.0, total_cost=800.0
            )
        ]
        metrics = KPIEngine.calculate_fleet_metrics(
            equipment=self.equipment,
            work_orders=orders,
            period_days=30,
            fuel_cost_total=4000.0
        )
        self.assertEqual(metrics["physical_availability_pct"], 95.56)
        self.assertEqual(metrics["mtbf_hours"], 2000.0)  # 2000h / 1 falla
        self.assertEqual(metrics["mttr_hours"], 14.0)
        self.assertEqual(metrics["preventive_compliance_pct"], 75.0)  # 3 de 4 son preventivas
        # Costo total: 1700 (OTs) + 4000 (combustible) = 5700 -> $/h: 5700 / 2000 = 2.85
        self.assertEqual(metrics["cost_per_operating_hour"], 2.85)

    # --- 2. TESTS DE FACTURACIÓN SUNAT Y WEBHOOKS ---
    def test_culqi_webhook_signature_verification(self):
        payload_bytes = b'{"event":"charge.succeeded","amount":119.00}'
        valid_sig = hmac.new(self.secret_key, payload_bytes, hashlib.sha256).hexdigest()
        
        is_valid = BillingEngine.verify_culqi_webhook(payload_bytes, valid_sig, self.secret_key)
        self.assertTrue(is_valid)

        forged_sig = "a" * 64
        is_invalid = BillingEngine.verify_culqi_webhook(payload_bytes, forged_sig, self.secret_key)
        self.assertFalse(is_invalid)

    def test_sunat_invoice_tax_and_hash_calculation(self):
        payment = WebhookPaymentPayload(
            event="charge.succeeded",
            company_id="COMP-DEMO-MINING",
            company_ruc="20601234567",
            customer_email="billing@example-mining.com",
            plan_name="Elite",
            amount_pen=119.00,  # S/ 119 incluido IGV
            device_fingerprint="HWID-TEST-001",
            payment_method="yape",
            culqi_charge_id="chr_test_987654"
        )
        invoice = BillingEngine.generate_sunat_invoice(payment, series="F001", correlative=500)
        
        self.assertEqual(invoice.invoice_number, "F001-00000500")
        self.assertEqual(invoice.total, 119.00)
        # Subtotal + IGV = Total
        self.assertAlmostEqual(invoice.subtotal + invoice.igv_18_pct, invoice.total, places=2)
        self.assertEqual(invoice.sunat_status, "SIMULATED_ACCEPTED")
        self.assertTrue(len(invoice.digest_value_hash) == 64)
        self.assertIn("20601234567", invoice.qr_data)

    def test_automated_subscription_and_license_issuance(self):
        payment = WebhookPaymentPayload(
            event="charge.succeeded",
            company_id="COMP-DEMO-MINING",
            company_ruc="20601234567",
            customer_email="billing@example-mining.com",
            plan_name="Elite",
            amount_pen=119.00,
            device_fingerprint="HWID-DEMO-TABLET",
            payment_method="visa",
            culqi_charge_id="chr_test_123"
        )
        invoice, license_token = BillingEngine.process_automated_subscription(payment, self.secret_key)
        self.assertIsNotNone(invoice.invoice_number)
        self.assertIn(".", license_token)  # Formato payload.signature


if __name__ == "__main__":
    unittest.main()

