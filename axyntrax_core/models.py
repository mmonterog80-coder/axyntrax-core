"""
Esquemas Pydantic v2 de Dominio para Axyntrax 2.0 Industrial CMMS.
Diseñado con arquitectura Multi-Tenant, auditoría inmutable (Snipe-IT),
catálogo de partes cruzadas (InvenTree) y ciclo de vida de OTs (ERPNext).
"""
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    SUPERVISOR = "SUPERVISOR"
    TECHNICIAN = "TECHNICIAN"
    OPERATOR = "OPERATOR"


class PlanType(str, Enum):
    PM1 = "PM1_250H"
    PM2 = "PM2_500H"
    PM3 = "PM3_1000H"
    PM4 = "PM4_2000H"
    CORRECTIVE = "CORRECTIVE"


class WorkOrderStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# --- 1. EQUIPOS Y ACTIVOS ---
class Equipment(BaseModel):
    id: str = Field(..., description="ID único del activo")
    company_id: str
    name: str = Field(..., example="Caterpillar 320D")
    serial_number: str
    brand: str
    model: str
    year: int
    current_horometer: float = Field(0.0, ge=0.0)
    tank_capacity_liters: float = Field(..., gt=0.0, description="Capacidad física del tanque")
    expected_burn_rate_lph: float = Field(..., gt=0.0, description="Consumo esperado en litros/hora")
    location_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# --- 2. HORÓMETRO ANTIFRAUDE (TRACCAR JITTER & MONOTONÍA) ---
class HorometerReading(BaseModel):
    equipment_id: str
    company_id: str
    operator_id: str
    reading_hours: float = Field(..., ge=0.0)
    reading_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    photo_hash: str | None = Field(None, description="SHA-256 de la fotografía del horómetro")
    gps_lat: float | None = None
    gps_lng: float | None = None


# --- 3. REPUESTOS Y CATÁLOGO CRUZADO (INVENTREE) ---
class SparePart(BaseModel):
    id: str
    company_id: str
    name: str
    oem_code: str = Field(..., description="Código original de fábrica (ej. CAT 1R-0739)")
    alternative_codes: list[str] = Field(default_factory=list, description="Códigos alternativos (Donaldson, Baldwin)")
    unit_cost: float = Field(..., ge=0.0)
    stock_quantity: int = Field(default=0, ge=0)
    min_stock_alert: int = Field(default=2, ge=0)


# --- 4. CONTROL DE COMBUSTIBLE (BALANCE DE MASA) ---
class FuelLog(BaseModel):
    equipment_id: str
    company_id: str
    liters_loaded: float = Field(..., gt=0.0)
    current_horometer: float = Field(..., ge=0.0)
    fuel_cost_total: float = Field(..., ge=0.0)
    fuel_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ticket_photo_hash: str | None = None


# --- 5. ÓRDENES DE TRABAJO (ERPNEXT) ---
class PartUsage(BaseModel):
    part_id: str
    quantity: int = Field(..., gt=0)
    unit_cost_snapshot: float = Field(..., ge=0.0)


class WorkOrder(BaseModel):
    id: str
    company_id: str
    equipment_id: str
    plan_type: PlanType
    status: WorkOrderStatus = WorkOrderStatus.SCHEDULED
    scheduled_horometer: float
    actual_horometer: float | None = None
    tasks_checklist: list[str] = Field(default_factory=list)
    parts_consumed: list[PartUsage] = Field(default_factory=list)
    assigned_technician_id: str | None = None
    signature_hash: str | None = None
    verification_qr_token: str | None = None
    total_cost: float = 0.0
    completed_at: datetime | None = None


# --- 6. AUDITORÍA INMUTABLE (SNIPE-IT ACTIONLOG) ---
class ActionLog(BaseModel):
    id: str
    company_id: str
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
