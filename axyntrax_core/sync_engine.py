"""
Motor de Sincronización Transaccional Offline-First para Axyntrax 2.0.
Diseñado para operaciones en socavones mineros, canteras y zonas sin cobertura 4G/5G.
Permite encolar operaciones en SQLite local y conciliar lotes con resolución de conflictos.
"""
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from axyntrax_core.engine import HorometerFraudError, MaintenanceEngine
from axyntrax_core.models import Equipment, HorometerReading


class OfflineAction(BaseModel):
    action_id: str
    action_type: str  # RECORD_HOROMETER, LOG_FUEL, COMPLETE_WO
    company_id: str
    equipment_id: str
    payload: dict[str, Any]
    client_timestamp: datetime
    device_id: str


class SyncBatchRequest(BaseModel):
    company_id: str
    device_id: str
    actions: list[OfflineAction]


class SyncActionResult(BaseModel):
    action_id: str
    status: str  # APPLIED, CONFLICT_REJECTED, FRAUD_REJECTED
    message: str
    server_time: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SyncBatchResponse(BaseModel):
    total_received: int
    applied_count: int
    rejected_count: int
    results: list[SyncActionResult]
    server_state_delta: dict[str, Any] = Field(default_factory=dict)


class SyncEngine:
    @classmethod
    def process_sync_batch(
        cls, 
        batch: SyncBatchRequest, 
        equipment_db: dict[str, Equipment]
    ) -> SyncBatchResponse:
        """
        Procesa el lote de acciones generadas offline de forma atómica y determinista.
        Ordena cronológicamente por client_timestamp para preservar la flecha del tiempo.
        """
        # Ordenar acciones por tiempo del cliente
        sorted_actions = sorted(batch.actions, key=lambda x: x.client_timestamp)
        
        applied = 0
        rejected = 0
        results: list[SyncActionResult] = []
        updated_equipment: dict[str, Any] = {}

        for act in sorted_actions:
            equipment = equipment_db.get(act.equipment_id)
            if not equipment:
                results.append(SyncActionResult(
                    action_id=act.action_id,
                    status="REJECTED_NOT_FOUND",
                    message=f"Equipo {act.equipment_id} no existe en servidor."
                ))
                rejected += 1
                continue

            # Procesar según tipo de acción
            if act.action_type == "RECORD_HOROMETER":
                reading_hours = act.payload.get("reading_hours", 0.0)
                reading = HorometerReading(
                    equipment_id=equipment.id,
                    company_id=equipment.company_id,
                    operator_id=act.payload.get("operator_id", "OFFLINE_OPERATOR"),
                    reading_hours=reading_hours,
                    reading_timestamp=act.client_timestamp
                )
                try:
                    new_hours = MaintenanceEngine.validate_and_update_horometer(equipment, reading)
                    results.append(SyncActionResult(
                        action_id=act.action_id,
                        status="APPLIED",
                        message=f"Horómetro sincronizado con éxito a {new_hours} h."
                    ))
                    applied += 1
                    updated_equipment[equipment.id] = {
                        "current_horometer": new_hours,
                        "sync_status": "UP_TO_DATE"
                    }
                except HorometerFraudError as e:
                    results.append(SyncActionResult(
                        action_id=act.action_id,
                        status="FRAUD_REJECTED",
                        message=str(e)
                    ))
                    rejected += 1
            else:
                results.append(SyncActionResult(
                    action_id=act.action_id,
                    status="UNSUPPORTED_ACTION",
                    message=f"Tipo de acción '{act.action_type}' no soportado aún."
                ))
                rejected += 1

        return SyncBatchResponse(
            total_received=len(batch.actions),
            applied_count=applied,
            rejected_count=rejected,
            results=results,
            server_state_delta=updated_equipment
        )
