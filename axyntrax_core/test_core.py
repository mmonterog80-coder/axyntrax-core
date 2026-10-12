"""
Suite de Pruebas Unitarias Automatizadas para Axyntrax 2.0 Core.
Valida la resiliencia y corrección de los motores de horómetro, combustible y OTs.
"""
import unittest
from datetime import UTC, datetime, timedelta

from axyntrax_core.engine import (
    FuelAnomalyError,
    HorometerFraudError,
    MaintenanceEngine,
)
from axyntrax_core.models import (
    Equipment,
    FuelLog,
    HorometerReading,
    PartUsage,
    PlanType,
    SparePart,
    WorkOrder,
    WorkOrderStatus,
)
from axyntrax_core.work_orders import WorkOrderManager


class TestAxyntraxCore(unittest.TestCase):
    def setUp(self):
        self.equipment = Equipment(
            id="EQ-CAT-320D-01",
            company_id="COMP-DEMO-MINING",
            name="Excavadora Caterpillar 320D",
            serial_number="CAT320D-2019-981",
            brand="Caterpillar",
            model="320D",
            year=2019,
            current_horometer=1490.0,
            tank_capacity_liters=410.0,
            expected_burn_rate_lph=22.0  # Consumo normal 22 L/h
        )
        self.secret_key = b"test-only-dummy-key-not-a-secret-32b"

    # --- 1. TESTS DE HORÓMETRO Y PREVENCIÓN DE FRAUDE ---
    def test_horometer_valid_increment(self):
        reading = HorometerReading(
            equipment_id=self.equipment.id,
            company_id=self.equipment.company_id,
            operator_id="OP-OPERATOR-01",
            reading_hours=1498.5
        )
        new_hours = MaintenanceEngine.validate_and_update_horometer(self.equipment, reading)
        self.assertEqual(new_hours, 1498.5)
        self.assertEqual(self.equipment.current_horometer, 1498.5)

    def test_horometer_backwards_rollback_raises_fraud(self):
        reading = HorometerReading(
            equipment_id=self.equipment.id,
            company_id=self.equipment.company_id,
            operator_id="OP-FRAUDE",
            reading_hours=1450.0  # Intento de retroceder 40 horas
        )
        with self.assertRaises(HorometerFraudError) as ctx:
            MaintenanceEngine.validate_and_update_horometer(self.equipment, reading)
        self.assertIn("Alerta de Fraude", str(ctx.exception))

    def test_horometer_jitter_filtering(self):
        # Ruido de 0.02 horas (menor al umbral de 0.05h)
        reading = HorometerReading(
            equipment_id=self.equipment.id,
            company_id=self.equipment.company_id,
            operator_id="OP-OPERATOR-01",
            reading_hours=1490.03
        )
        new_hours = MaintenanceEngine.validate_and_update_horometer(self.equipment, reading)
        self.assertEqual(new_hours, 1490.0)  # Se descarta el jitter espurio

    def test_horometer_impossible_speed_raises_fraud(self):
        # 10 horas de máquina reportadas en solo 1 hora de reloj
        t1 = datetime.now(UTC)
        t2 = t1 + timedelta(hours=1)
        reading = HorometerReading(
            equipment_id=self.equipment.id,
            company_id=self.equipment.company_id,
            operator_id="OP-APURADO",
            reading_hours=1500.0,  # +10 horas de máquina
            reading_timestamp=t2
        )
        with self.assertRaises(HorometerFraudError) as ctx:
            MaintenanceEngine.validate_and_update_horometer(self.equipment, reading, last_reading_time=t1)
        self.assertIn("Anomalía Física", str(ctx.exception))

    # --- 2. TESTS DE MANTENIMIENTO PREVENTIVO OEM ---
    def test_preventive_maintenance_schedule(self):
        # Horómetro en 1490h -> El próximo múltiplo de 250h es 1500h (PM3 de 1000h o PM1)
        # 1500 % 500 == 0 -> PM2
        calc = MaintenanceEngine.calculate_next_maintenance(1490.0)
        self.assertEqual(calc["target_horometer"], 1500)
        self.assertEqual(calc["remaining_hours"], 10.0)
        self.assertEqual(calc["status"], "WARNING")  # Faltan 10h (< 50h de alerta)
        self.assertEqual(calc["service_type"], PlanType.PM2.value)

    # --- 3. TESTS DE CONTROL DE COMBUSTIBLE ---
    def test_fuel_impossible_tank_overfill(self):
        fuel_log = FuelLog(
            equipment_id=self.equipment.id,
            company_id=self.equipment.company_id,
            liters_loaded=550.0,  # Tanque es de 410 L
            current_horometer=1500.0,
            fuel_cost_total=2200.0
        )
        with self.assertRaises(FuelAnomalyError) as ctx:
            MaintenanceEngine.evaluate_fuel_efficiency(self.equipment, fuel_log, previous_horometer=1470.0)
        self.assertIn("Carga Imposible", str(ctx.exception))

    def test_fuel_theft_or_leak_detection(self):
        # 300 Litros cargados en solo 5 horas de trabajo -> 60 L/h (Norma es 22 L/h, desvío > 170%)
        fuel_log = FuelLog(
            equipment_id=self.equipment.id,
            company_id=self.equipment.company_id,
            liters_loaded=300.0,
            current_horometer=1495.0,
            fuel_cost_total=1200.0
        )
        res = MaintenanceEngine.evaluate_fuel_efficiency(self.equipment, fuel_log, previous_horometer=1490.0)
        self.assertEqual(res["status"], "ANOMALY_THEFT_OR_LEAK")
        self.assertEqual(res["burn_rate_lph"], 60.0)

    # --- 4. TESTS DE ÓRDENES DE TRABAJO E INVENTARIO ---
    def test_work_order_completion_and_stock_deduction(self):
        parts_db = {
            "P-OIL-CAT": SparePart(
                id="P-OIL-CAT",
                company_id=self.equipment.company_id,
                name="Filtro de Aceite CAT",
                oem_code="1R-0739",
                alternative_codes=["Donaldson P551343", "Baldwin BF7587"],
                unit_cost=85.0,
                stock_quantity=10
            )
        }
        wo = WorkOrder(
            id="OT-2026-001",
            company_id=self.equipment.company_id,
            equipment_id=self.equipment.id,
            plan_type=PlanType.PM1,
            scheduled_horometer=1500.0,
            parts_consumed=[PartUsage(part_id="P-OIL-CAT", quantity=2, unit_cost_snapshot=85.0)]
        )
        # 1. Iniciar OT
        wo = WorkOrderManager.start_work_order(wo, technician_id="TECH-MIGUEL")
        self.assertEqual(wo.status, WorkOrderStatus.IN_PROGRESS)

        # 2. Cerrar OT
        completed_wo, logs = WorkOrderManager.complete_work_order(
            work_order=wo,
            closing_horometer=1502.0,
            inventory_parts=parts_db,
            signature_vector="COORDS_X10_Y20_TOUCH_SIGNED",
            secret_key=self.secret_key
        )
        self.assertEqual(completed_wo.status, WorkOrderStatus.COMPLETED)
        self.assertEqual(parts_db["P-OIL-CAT"].stock_quantity, 8)  # Descontó 2 piezas
        self.assertEqual(completed_wo.total_cost, 170.0)  # 2 * 85
        self.assertIsNotNone(completed_wo.verification_qr_token)
        self.assertEqual(len(logs), 2)  # Log de deducción + Log de cierre


if __name__ == "__main__":
    unittest.main()


