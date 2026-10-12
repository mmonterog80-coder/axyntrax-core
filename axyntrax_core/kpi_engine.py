"""
Motor de Métricas y KPIs Industriales para Axyntrax 2.0 (Normas SMRP / ISO 14224).
Calcula indicadores de confiabilidad, disponibilidad física y costo operativo por hora.
"""
from typing import Any

from axyntrax_core.models import Equipment, PlanType, WorkOrder, WorkOrderStatus


class KPIEngine:
    @staticmethod
    def calculate_fleet_metrics(
        equipment: Equipment,
        work_orders: list[WorkOrder],
        period_days: int = 30,
        fuel_cost_total: float = 0.0
    ) -> dict[str, Any]:
        """
        Calcula:
        1. Disponibilidad Física (%): Tiempo operativo vs tiempo total nominal.
        2. MTBF (Mean Time Between Failures): Horas promedio entre mantenimientos correctivos.
        3. MTTR (Mean Time To Repair): Horas promedio de duración de parada.
        4. TCO / Costo por Hora ($/h): (Repuestos + Combustible) / Horas de operación.
        """
        nominal_period_hours = period_days * 24.0
        completed_orders = [wo for wo in work_orders if wo.status == WorkOrderStatus.COMPLETED and wo.equipment_id == equipment.id]

        corrective_orders = [wo for wo in completed_orders if wo.plan_type == PlanType.CORRECTIVE]
        preventive_orders = [wo for wo in completed_orders if wo.plan_type != PlanType.CORRECTIVE]

        # Costos acumulados de repuestos
        parts_cost_total = sum(wo.total_cost for wo in completed_orders)
        grand_total_cost = parts_cost_total + fuel_cost_total

        # Cálculo de tiempo de inactividad estimado (Downtime: asumimos 6h promedio por preventivo y 14h por correctivo)
        downtime_hours = (len(preventive_orders) * 6.0) + (len(corrective_orders) * 14.0)
        uptime_hours = max(nominal_period_hours - downtime_hours, 0.0)

        # 1. Disponibilidad Física
        physical_availability_pct = (uptime_hours / nominal_period_hours) * 100.0 if nominal_period_hours > 0 else 0.0

        # 2. MTBF (Horas de máquina entre fallas no programadas)
        operating_hours = equipment.current_horometer
        corrective_count = len(corrective_orders)
        mtbf_hours = (operating_hours / corrective_count) if corrective_count > 0 else operating_hours

        # 3. MTTR
        mttr_hours = (len(corrective_orders) * 14.0 / corrective_count) if corrective_count > 0 else 0.0

        # 4. Costo por hora de operación ($/h)
        cost_per_operating_hour = (grand_total_cost / operating_hours) if operating_hours > 0 else 0.0

        # 5. Cumplimiento Preventivo (%)
        total_orders_count = len(completed_orders)
        preventive_compliance_pct = (len(preventive_orders) / total_orders_count * 100.0) if total_orders_count > 0 else 100.0

        return {
            "equipment_id": equipment.id,
            "operating_horometer": equipment.current_horometer,
            "physical_availability_pct": round(physical_availability_pct, 2),
            "mtbf_hours": round(mtbf_hours, 1),
            "mttr_hours": round(mttr_hours, 1),
            "preventive_compliance_pct": round(preventive_compliance_pct, 1),
            "total_maintenance_cost": round(parts_cost_total, 2),
            "total_fuel_cost": round(fuel_cost_total, 2),
            "grand_total_operating_cost": round(grand_total_cost, 2),
            "cost_per_operating_hour": round(cost_per_operating_hour, 2)
        }
