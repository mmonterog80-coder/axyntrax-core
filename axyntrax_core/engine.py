"""
Motor de Cálculo Industrial Axyntrax 2.0.
Implementa:
1. Validación de Horómetro Antifraude (Monotonía, Jitter Traccar y Límite Físico).
2. Cálculo de Intervalos Preventivos OEM (PM1=250h, PM2=500h, PM3=1000h, PM4=2000h).
3. Balance de Masa de Combustible y Detección de Fuga / Ordeño.
"""
from datetime import datetime
from typing import Any

from axyntrax_core.models import Equipment, FuelLog, HorometerReading, PlanType


class HorometerFraudError(Exception):
    """Lanzada ante intentos de adulteración o error físico de horómetro."""


class FuelAnomalyError(Exception):
    """Lanzada ante discrepancias físicas de combustible."""


class MaintenanceEngine:
    JITTER_THRESHOLD_HOURS = 0.05

    @classmethod
    def validate_and_update_horometer(cls, equipment: Equipment, 
                                      reading: HorometerReading,
                                      last_reading_time: datetime | None = None) -> float:
        """
        Valida que la lectura sea físicamente posible:
        1. Monotonía estricta: el horómetro no puede retroceder.
        2. Filtro de Jitter: descarta micro-oscilaciones espurias.
        3. Límite de velocidad física: delta horas no puede superar el tiempo transcurrido en el reloj.
        """
        new_hours = reading.reading_hours
        prev_hours = equipment.current_horometer
        delta_hours = new_hours - prev_hours

        # 1. Validación de retroceso
        if delta_hours < 0:
            raise HorometerFraudError(
                f"Alerta de Fraude: El nuevo horómetro ({new_hours} h) es inferior al actual ({prev_hours} h)."
            )

        # 2. Filtro de Jitter (si es menor al umbral de ruido, se descarta)
        if 0 < delta_hours < cls.JITTER_THRESHOLD_HOURS:
            return prev_hours

        # 3. Límite de velocidad física de reloj
        if last_reading_time:
            elapsed_seconds = (reading.reading_timestamp - last_reading_time).total_seconds()
            if elapsed_seconds > 0:
                elapsed_hours = elapsed_seconds / 3600.0
                # Si las horas de máquina crecieron más que el tiempo real transcurrido
                if delta_hours > (elapsed_hours + 0.1):  # Margen de 6 minutos de holgura
                    raise HorometerFraudError(
                        f"Anomalía Física: La máquina reportó {delta_hours:.2f} h en solo {elapsed_hours:.2f} h reales."
                    )

        equipment.current_horometer = new_hours
        return new_hours

    @classmethod
    def calculate_next_maintenance(cls, current_horometer: float) -> dict[str, Any]:
        """
        Calcula el próximo servicio preventivo según la escala estándar OEM:
        - PM1: cada 250 h
        - PM2: cada 500 h
        - PM3: cada 1000 h
        - PM4: cada 2000 h
        """
        # Calcular el próximo múltiplo de 250 h
        next_pm1 = ((int(current_horometer) // 250) + 1) * 250
        remaining_hours = next_pm1 - current_horometer

        # Determinar jerarquía del servicio
        if next_pm1 % 2000 == 0:
            service_type = PlanType.PM4
            priority = "CRITICAL"
        elif next_pm1 % 1000 == 0:
            service_type = PlanType.PM3
            priority = "HIGH"
        elif next_pm1 % 500 == 0:
            service_type = PlanType.PM2
            priority = "MEDIUM"
        else:
            service_type = PlanType.PM1
            priority = "STANDARD"

        is_due = remaining_hours <= 0
        is_warning = 0 < remaining_hours <= 50  # Alerta temprana 50 h antes

        return {
            "service_type": service_type.value,
            "target_horometer": next_pm1,
            "remaining_hours": round(remaining_hours, 2),
            "status": "OVERDUE" if is_due else ("WARNING" if is_warning else "OK"),
            "priority": priority
        }

    @classmethod
    def evaluate_fuel_efficiency(cls, equipment: Equipment, fuel_log: FuelLog, 
                                 previous_horometer: float) -> dict[str, Any]:
        """
        Valida carga contra volumen físico del tanque y evalúa ratio de consumo real (L/h).
        """
        # 1. Comprobación de capacidad de tanque (máximo 5% de holgura de cuello)
        max_allowed_liters = equipment.tank_capacity_liters * 1.05
        if fuel_log.liters_loaded > max_allowed_liters:
            raise FuelAnomalyError(
                f"Carga Imposible: Se cargaron {fuel_log.liters_loaded} L en un tanque con capacidad de {equipment.tank_capacity_liters} L."
            )

        # 2. Cálculo de consumo en L/h
        delta_hours = fuel_log.current_horometer - previous_horometer
        if delta_hours <= 0:
            return {"burn_rate_lph": 0.0, "status": "PENDING_HOURS", "deviation_pct": 0.0}

        actual_lph = fuel_log.liters_loaded / delta_hours
        expected_lph = equipment.expected_burn_rate_lph
        deviation_pct = ((actual_lph - expected_lph) / expected_lph) * 100.0

        anomaly = deviation_pct > 25.0  # Alerta si consume >25% sobre la norma OEM

        return {
            "burn_rate_lph": round(actual_lph, 2),
            "expected_lph": expected_lph,
            "deviation_pct": round(deviation_pct, 1),
            "status": "ANOMALY_THEFT_OR_LEAK" if anomaly else "NORMAL"
        }
