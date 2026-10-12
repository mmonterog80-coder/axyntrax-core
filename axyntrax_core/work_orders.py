"""
Gestor del Ciclo de Vida de Órdenes de Trabajo (OT) e Inventario.
Inspirado en ERPNext (ciclo de estados y consumo de repuestos)
y Snipe-IT (ActionLog inmutable y firmas verificables).
"""
import hashlib
import hmac
from datetime import UTC, datetime

from axyntrax_core.models import (
    ActionLog,
    SparePart,
    WorkOrder,
    WorkOrderStatus,
)


class WorkOrderError(Exception):
    """Excepción para violaciones de flujo de Órdenes de Trabajo."""


class WorkOrderManager:
    @staticmethod
    def start_work_order(work_order: WorkOrder, technician_id: str) -> WorkOrder:
        """
        Pasa la OT de SCHEDULED a IN_PROGRESS asignando al técnico ejecutor.
        """
        if work_order.status != WorkOrderStatus.SCHEDULED:
            raise WorkOrderError(f"No se puede iniciar una OT con estado {work_order.status}.")
        
        work_order.status = WorkOrderStatus.IN_PROGRESS
        work_order.assigned_technician_id = technician_id
        return work_order

    @staticmethod
    def complete_work_order(
        work_order: WorkOrder,
        closing_horometer: float,
        inventory_parts: dict[str, SparePart],
        signature_vector: str,
        secret_key: bytes
    ) -> tuple[WorkOrder, list[ActionLog]]:
        """
        Cierra formalmente la OT:
        1. Descuenta automáticamente el stock de repuestos consumidos.
        2. Calcula el costo total del servicio.
        3. Genera el token criptográfico de validación pericial para el código QR.
        4. Produce el log de auditoría inmutable.
        """
        if work_order.status != WorkOrderStatus.IN_PROGRESS:
            raise WorkOrderError("Solo se pueden cerrar OTs que estén en proceso (IN_PROGRESS).")

        total_parts_cost = 0.0
        logs: list[ActionLog] = []

        # 1. Deducción de repuestos en inventario (InvenTree pattern)
        for usage in work_order.parts_consumed:
            part = inventory_parts.get(usage.part_id)
            if not part:
                raise WorkOrderError(f"El repuesto con ID '{usage.part_id}' no existe en inventario.")
            
            if part.stock_quantity < usage.quantity:
                raise WorkOrderError(
                    f"Stock insuficiente para '{part.name}'. Disponible: {part.stock_quantity}, requerido: {usage.quantity}."
                )
            
            part.stock_quantity -= usage.quantity
            total_parts_cost += (usage.quantity * usage.unit_cost_snapshot)

            logs.append(ActionLog(
                id=f"LOG-DEDUCT-{part.id}-{int(datetime.now(UTC).timestamp())}",
                company_id=work_order.company_id,
                actor_id=work_order.assigned_technician_id or "SYSTEM",
                action="DEDUCT_STOCK_WORK_ORDER",
                entity_type="SPARE_PART",
                entity_id=part.id,
                details={"deducted": usage.quantity, "remaining_stock": part.stock_quantity}
            ))

        # 2. Asignar horas finales y costos
        work_order.actual_horometer = closing_horometer
        work_order.total_cost = total_parts_cost
        work_order.status = WorkOrderStatus.COMPLETED
        work_order.completed_at = datetime.now(UTC)

        # 3. Firma digital y token QR de verificación pericial
        sig_hash = hashlib.sha256(signature_vector.encode()).hexdigest()
        work_order.signature_hash = sig_hash

        qr_payload = f"{work_order.id}|{work_order.company_id}|{work_order.actual_horometer}|{sig_hash}"
        qr_sig = hmac.new(secret_key, qr_payload.encode(), hashlib.sha256).hexdigest()[:16]
        work_order.verification_qr_token = f"{qr_payload}|{qr_sig}"

        logs.append(ActionLog(
            id=f"LOG-WO-CLOSE-{work_order.id}",
            company_id=work_order.company_id,
            actor_id=work_order.assigned_technician_id or "SYSTEM",
            action="COMPLETE_WORK_ORDER",
            entity_type="WORK_ORDER",
            entity_id=work_order.id,
            details={"actual_horometer": closing_horometer, "total_cost": total_parts_cost}
        ))

        return work_order, logs
