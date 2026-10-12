"""
API Gateway de Producción para Axyntrax 2.0 (FastAPI).
Expone servicios REST de alta resiliencia con validación Pydantic v2,
detección antifraude en tiempo real y arquitectura lista para sincronización offline.
"""
import os

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.responses import HTMLResponse

from axyntrax_core.billing import BillingEngine, WebhookPaymentPayload
from axyntrax_core.engine import (
    FuelAnomalyError,
    HorometerFraudError,
    MaintenanceEngine,
)
from axyntrax_core.kpi_engine import KPIEngine
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
from axyntrax_core.security.integrity_guard import IntegrityGuard
from axyntrax_core.sync_engine import SyncBatchRequest, SyncBatchResponse, SyncEngine
from axyntrax_core.work_orders import WorkOrderError, WorkOrderManager

app = FastAPI(
    title="Axyntrax Industrial CMMS API",
    version="2.0.0",
    description="Motor de Mantenimiento Predictivo, Horómetro Antifraude y OTs Certificadas."
)

# Base de datos simulada en memoria para pruebas de la API (Multi-Tenant)
DB_EQUIPMENT: dict[str, Equipment] = {}
DB_PARTS: dict[str, SparePart] = {}
DB_WORK_ORDERS: dict[str, WorkOrder] = {}
# Clave de firma obligatoria por variable de entorno (fail-fast si no existe)
_signing_secret_raw = os.environ.get("AXYNTRAX_SIGNING_SECRET")
if not _signing_secret_raw:
    raise RuntimeError(
        "AXYNTRAX_SIGNING_SECRET environment variable is required. "
        "Set it via environment variable (e.g., $env:AXYNTRAX_SIGNING_SECRET='...') before starting the API."
    )
SIGNING_SECRET: bytes = _signing_secret_raw.encode("utf-8")


@app.on_event("startup")
def startup_populate():
    # Inicializar equipo de prueba
    DB_EQUIPMENT["EQ-CAT-320D-01"] = Equipment(
        id="EQ-CAT-320D-01",
        company_id="COMP-AXYNTRAX-MINING",
        name="Excavadora Caterpillar 320D",
        serial_number="CAT-SN-8921",
        brand="Caterpillar",
        model="320D",
        year=2021,
        current_horometer=1000.0,
        tank_capacity_liters=400.0,
        expected_burn_rate_lph=20.0
    )
    # Inicializar repuesto en stock
    DB_PARTS["PART-OIL-FILTER-01"] = SparePart(
        id="PART-OIL-FILTER-01",
        company_id="COMP-AXYNTRAX-MINING",
        name="Filtro de Aceite CAT",
        oem_code="1R-0739",
        alternative_codes=["Donaldson P551343"],
        unit_cost=95.0,
        stock_quantity=15
    )


@app.get("/health", tags=["Infraestructura"])
def health_check():
    sec_health = IntegrityGuard.run_health_check()
    return {
        "service": "Axyntrax Industrial CMMS API",
        "status": "OPERATIONAL",
        "security": sec_health
    }


@app.get("/dashboard", response_class=HTMLResponse, tags=["Interfaz Visual"])
@app.get("/", response_class=HTMLResponse, tags=["Interfaz Visual"])
def get_dashboard():
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Axyntrax 2.0 API Operational</h1>"


@app.post("/api/v1/horometer/record", tags=["Horómetro"])
def record_horometer(reading: HorometerReading):
    equipment = DB_EQUIPMENT.get(reading.equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipo no encontrado.")

    try:
        new_hours = MaintenanceEngine.validate_and_update_horometer(equipment, reading)
        maintenance_info = MaintenanceEngine.calculate_next_maintenance(new_hours)
        return {
            "success": True,
            "equipment_id": equipment.id,
            "current_horometer": new_hours,
            "maintenance_projection": maintenance_info
        }
    except HorometerFraudError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rechazado por Antifraude: {e!s}"
        )


@app.get("/api/v1/equipment/{equipment_id}/maintenance-status", tags=["Mantenimiento"])
def get_maintenance_status(equipment_id: str):
    equipment = DB_EQUIPMENT.get(equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipo no encontrado.")

    info = MaintenanceEngine.calculate_next_maintenance(equipment.current_horometer)
    return {
        "equipment_id": equipment.id,
        "name": equipment.name,
        "current_horometer": equipment.current_horometer,
        "maintenance": info
    }


@app.post("/api/v1/fuel/record", tags=["Combustible"])
def record_fuel(fuel_log: FuelLog):
    equipment = DB_EQUIPMENT.get(fuel_log.equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipo no encontrado.")

    try:
        efficiency = MaintenanceEngine.evaluate_fuel_efficiency(
            equipment=equipment,
            fuel_log=fuel_log,
            previous_horometer=equipment.current_horometer
        )
        return {
            "success": True,
            "equipment_id": equipment.id,
            "liters_loaded": fuel_log.liters_loaded,
            "analysis": efficiency
        }
    except FuelAnomalyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rechazado por Anomalía de Combustible: {e!s}"
        )


@app.post("/api/v1/work-orders/{order_id}/complete", tags=["Órdenes de Trabajo"])
def complete_order(order_id: str, closing_horometer: float, signature_vector: str):
    work_order = DB_WORK_ORDERS.get(order_id)
    if not work_order:
        # Para testing: generar OT al vuelo si no existe
        work_order = WorkOrder(
            id=order_id,
            company_id="COMP-AXYNTRAX-MINING",
            equipment_id="EQ-CAT-320D-01",
            plan_type=PlanType.PM1,
            status=WorkOrderStatus.IN_PROGRESS,
            scheduled_horometer=1250.0,
            parts_consumed=[PartUsage(part_id="PART-OIL-FILTER-01", quantity=1, unit_cost_snapshot=95.0)]
        )
        DB_WORK_ORDERS[order_id] = work_order

    try:
        completed_wo, logs = WorkOrderManager.complete_work_order(
            work_order=work_order,
            closing_horometer=closing_horometer,
            inventory_parts=DB_PARTS,
            signature_vector=signature_vector,
            secret_key=SIGNING_SECRET
        )
        return {
            "success": True,
            "order_id": completed_wo.id,
            "status": completed_wo.status.value,
            "total_cost": completed_wo.total_cost,
            "verification_qr_token": completed_wo.verification_qr_token,
            "stock_remaining": DB_PARTS["PART-OIL-FILTER-01"].stock_quantity,
            "logs_generated": len(logs)
        }
    except WorkOrderError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/sync/batch", response_model=SyncBatchResponse, tags=["Sincronización Offline"])
def sync_batch(batch: SyncBatchRequest):
    """
    Endpoint para sincronización en lote desde terminales móviles en campo sin señal.
    """
    return SyncEngine.process_sync_batch(batch, DB_EQUIPMENT)


@app.get("/api/v1/equipment/{equipment_id}/kpis", tags=["Métricas y KPIs"])
def get_equipment_kpis(equipment_id: str, period_days: int = 30, fuel_cost_total: float = 0.0):
    """
    Retorna Disponibilidad Física, MTBF, MTTR y Costo por hora de operación ($/h).
    """
    equipment = DB_EQUIPMENT.get(equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipo no encontrado.")

    orders = list(DB_WORK_ORDERS.values())
    metrics = KPIEngine.calculate_fleet_metrics(
        equipment=equipment,
        work_orders=orders,
        period_days=period_days,
        fuel_cost_total=fuel_cost_total
    )
    return metrics


@app.post("/api/v1/billing/culqi-webhook", tags=["Facturación SUNAT"])
def culqi_webhook(
    payload: WebhookPaymentPayload,
    x_culqi_signature: str = Header(..., description="Firma criptográfica HMAC del webhook")
):
    """
    Webhook seguro de Culqi: emite la Factura Electrónica SUNAT con CDR y activa la licencia Axyntrax.
    """
    raw_payload_bytes = payload.model_dump_json().encode("utf-8")
    is_valid = BillingEngine.verify_culqi_webhook(raw_payload_bytes, x_culqi_signature, SIGNING_SECRET)
    if not is_valid:
        raise HTTPException(status_code=403, detail="Firma de webhook inválida. Intento de inyección de pago bloqueado.")

    invoice, license_token = BillingEngine.process_automated_subscription(payload, SIGNING_SECRET)
    return {
        "success": True,
        "invoice_number": invoice.invoice_number,
        "sunat_status": invoice.sunat_status,
        "cdr_code": invoice.cdr_response_code,
        "digest_value": invoice.digest_value_hash,
        "license_token": license_token
    }
