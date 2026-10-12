"""
Suite de Pruebas de Módulos Avanzados: Catálogo OEM y Sincronización Offline-First.
Demuestra la precisión de los manuales de fabricante y la resiliencia en zonas sin señal.
"""
import unittest
from datetime import UTC, datetime, timedelta

from axyntrax_core.models import Equipment
from axyntrax_core.oem_catalog import OEMMaintenanceCatalog
from axyntrax_core.sync_engine import OfflineAction, SyncBatchRequest, SyncEngine


class TestAdvancedModules(unittest.TestCase):
    def setUp(self):
        self.cat_equipment = Equipment(
            id="EQ-CAT-320D-TEST",
            company_id="COMP-AXYNTRAX-MINING",
            name="Excavadora Caterpillar 320D",
            serial_number="CAT-SN-001",
            brand="Caterpillar",
            model="320D",
            year=2020,
            current_horometer=1200.0,
            tank_capacity_liters=400.0,
            expected_burn_rate_lph=20.0
        )
        self.equipment_db = {self.cat_equipment.id: self.cat_equipment}

    # --- 1. TESTS DE CATÁLOGO OEM ---
    def test_oem_plan_cat_320d_exact_match(self):
        plan = OEMMaintenanceCatalog.get_oem_plan("Caterpillar", "320D", 2020)
        self.assertEqual(plan["source"], "CATALOGO_OFICIAL_OEM")
        self.assertIn("SEBU8500", plan["manual_reference"])
        self.assertEqual(len(plan["tasks"]), 5)
        
        # Verificar tarea PM1 de 250h
        pm1 = next(t for t in plan["tasks"] if t["interval_hours"] == 250)
        self.assertIn("15W-40", pm1["fluid_spec"])
        self.assertIn("1R-0739", pm1["required_parts_oem"][0])

    def test_oem_plan_unknown_machine_fallback(self):
        plan = OEMMaintenanceCatalog.get_oem_plan("MarcaDesconocida", "ModeloX", 2022)
        self.assertEqual(plan["source"], "HEURISTICA_INDUSTRIAL_ISO55000")
        self.assertTrue(len(plan["tasks"]) >= 3)

    # --- 2. TESTS DE SINCRONIZACIÓN OFFLINE-FIRST ---
    def test_sync_batch_chronological_application(self):
        # Operador en cantera registra 2 lecturas offline en un turno
        now = datetime.now(UTC)
        actions = [
            OfflineAction(
                action_id="ACT-01",
                action_type="RECORD_HOROMETER",
                company_id="COMP-AXYNTRAX-MINING",
                equipment_id=self.cat_equipment.id,
                payload={"reading_hours": 1204.0, "operator_id": "OP-SOCAVON-01"},
                client_timestamp=now - timedelta(hours=4),
                device_id="DEV-RUGGED-TABLET-01"
            ),
            OfflineAction(
                action_id="ACT-02",
                action_type="RECORD_HOROMETER",
                company_id="COMP-AXYNTRAX-MINING",
                equipment_id=self.cat_equipment.id,
                payload={"reading_hours": 1208.5, "operator_id": "OP-SOCAVON-01"},
                client_timestamp=now,
                device_id="DEV-RUGGED-TABLET-01"
            )
        ]
        batch = SyncBatchRequest(
            company_id="COMP-AXYNTRAX-MINING",
            device_id="DEV-RUGGED-TABLET-01",
            actions=actions
        )

        res = SyncEngine.process_sync_batch(batch, self.equipment_db)
        self.assertEqual(res.total_received, 2)
        self.assertEqual(res.applied_count, 2)
        self.assertEqual(res.rejected_count, 0)
        self.assertEqual(self.cat_equipment.current_horometer, 1208.5)

    def test_sync_batch_fraud_rejection_isolated(self):
        # Lote que contiene una lectura válida y luego un retroceso fraudulento
        now = datetime.now(UTC)
        actions = [
            OfflineAction(
                action_id="ACT-VALID",
                action_type="RECORD_HOROMETER",
                company_id="COMP-AXYNTRAX-MINING",
                equipment_id=self.cat_equipment.id,
                payload={"reading_hours": 1205.0},
                client_timestamp=now - timedelta(hours=2),
                device_id="DEV-01"
            ),
            OfflineAction(
                action_id="ACT-FRAUD",
                action_type="RECORD_HOROMETER",
                company_id="COMP-AXYNTRAX-MINING",
                equipment_id=self.cat_equipment.id,
                payload={"reading_hours": 1150.0},  # Retroceso
                client_timestamp=now,
                device_id="DEV-01"
            )
        ]
        batch = SyncBatchRequest(
            company_id="COMP-AXYNTRAX-MINING",
            device_id="DEV-01",
            actions=actions
        )

        res = SyncEngine.process_sync_batch(batch, self.equipment_db)
        self.assertEqual(res.applied_count, 1)
        self.assertEqual(res.rejected_count, 1)
        # La lectura fraudulenta fue rechazada y la válida se consolidó
        self.assertEqual(self.cat_equipment.current_horometer, 1205.0)

    # --- 3. TESTS DE CERTIFICADO PERICIAL DE OT ---
    def test_ot_certificate_generation(self):
        from axyntrax_core.models import (
            PartUsage,
            PlanType,
            SparePart,
            WorkOrder,
            WorkOrderStatus,
        )
        from axyntrax_core.ot_certificate import OTCertificateGenerator
        
        parts_db = {
            "P-OIL": SparePart(
                id="P-OIL", company_id="C1", name="Filtro CAT", oem_code="1R-0739",
                unit_cost=100.0, stock_quantity=5
            )
        }
        wo = WorkOrder(
            id="OT-PERICIAL-99",
            company_id="C1",
            equipment_id=self.cat_equipment.id,
            plan_type=PlanType.PM1,
            status=WorkOrderStatus.COMPLETED,
            scheduled_horometer=1200.0,
            actual_horometer=1205.0,
            total_cost=200.0,
            assigned_technician_id="TECH-MIGUEL",
            signature_hash="HASH_SHA256_PERICIAL_VALID",
            verification_qr_token="TOKEN_QR_AUTHENTICATED",
            completed_at=datetime.now(UTC),
            parts_consumed=[PartUsage(part_id="P-OIL", quantity=2, unit_cost_snapshot=100.0)],
            tasks_checklist=["Inspección de 250h", "Cambio de filtros"]
        )
        cert = OTCertificateGenerator.generate_markdown_certificate(wo, self.cat_equipment, parts_db)
        self.assertIn("CERTIFICADO DE ORDEN DE TRABAJO — OT-PERICIAL-99", cert)
        self.assertIn("1R-0739", cert)
        self.assertIn("S/ 200.00", cert)
        self.assertIn("TOKEN_QR_AUTHENTICATED", cert)


if __name__ == "__main__":
    unittest.main()
