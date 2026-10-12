"""
Catálogo Industrial y Motor de Mantenimiento OEM para Axyntrax 2.0.
Valores y pautas ilustrativas para demostración y prototipado;
verifique siempre las especificaciones contra manuales de taller OEM oficiales.
"""
from typing import Any, ClassVar

from pydantic import BaseModel


class OEMTask(BaseModel):
    task_name: str
    interval_hours: int
    system: str  # Motor, Hidráulico, Transmisión, Estructura
    fluid_spec: str | None = None
    required_parts_oem: list[str] = []
    reference_manual: str


class OEMMaintenanceCatalog:
    _CATALOG: ClassVar[dict[tuple[str, str], dict[str, Any]]] = {
        ("caterpillar", "320d"): {
            "equipment_type": "Excavadora Hidráulica",
            "manual": "Caterpillar OMM SEBU8500",
            "tasks": [
                OEMTask(
                    task_name="Cambio de aceite de motor y filtro",
                    interval_hours=250,
                    system="Motor",
                    fluid_spec="Cat DEO-ULS 15W-40 (30 Litros)",
                    required_parts_oem=["1R-0739 (Filtro de Aceite)", "1R-0751 (Filtro de Combustible)"],
                    reference_manual="OMM SEBU8500 Sección Mantenimiento pág. 124"
                ),
                OEMTask(
                    task_name="Inspección y tensión de correas del alternador",
                    interval_hours=250,
                    system="Motor",
                    reference_manual="OMM SEBU8500 pág. 130"
                ),
                OEMTask(
                    task_name="Cambio de filtro primario de combustible y separador de agua",
                    interval_hours=500,
                    system="Combustible",
                    required_parts_oem=["326-1644 (Filtro Separador)"],
                    reference_manual="OMM SEBU8500 pág. 142"
                ),
                OEMTask(
                    task_name="Cambio de aceite hidráulico y filtros de retorno",
                    interval_hours=1000,
                    system="Hidráulico",
                    fluid_spec="Cat HYDO Advanced 10 (160 Litros)",
                    required_parts_oem=["1R-0777 (Filtro Hidráulico)"],
                    reference_manual="OMM SEBU8500 pág. 165"
                ),
                OEMTask(
                    task_name="Regulación de válvulas e inyectores",
                    interval_hours=2000,
                    system="Motor",
                    reference_manual="OMM SEBU8500 pág. 190"
                )
            ]
        },
        ("komatsu", "pc200"): {
            "equipment_type": "Excavadora sobre Orugas",
            "manual": "Komatsu Shop Manual SEAM020",
            "tasks": [
                OEMTask(
                    task_name="Cambio de aceite de motor y sustitución de cartucho",
                    interval_hours=250,
                    system="Motor",
                    fluid_spec="Komatsu Engine Oil 15W-40 DH-1 (24 Litros)",
                    required_parts_oem=["6736-51-5142 (Filtro Aceite)"],
                    reference_manual="Shop Manual SEAM020 pág. 88"
                ),
                OEMTask(
                    task_name="Engrase de pines de pluma, brazo y cucharón",
                    interval_hours=250,
                    system="Estructura",
                    fluid_spec="Grasa Litio EP-2",
                    reference_manual="Shop Manual SEAM020 pág. 94"
                ),
                OEMTask(
                    task_name="Sustitución de elemento de filtro de aire",
                    interval_hours=500,
                    system="Admisión",
                    required_parts_oem=["600-185-4100"],
                    reference_manual="Shop Manual SEAM020 pág. 112"
                ),
                OEMTask(
                    task_name="Cambio de aceite de mandos finales y tornamesa",
                    interval_hours=1000,
                    system="Transmisión",
                    fluid_spec="Komatsu TO-30 (8.5 Litros por mando)",
                    reference_manual="Shop Manual SEAM020 pág. 134"
                )
            ]
        },
        ("jlg", "600a"): {
            "equipment_type": "Elevador Articulado Manlift",
            "manual": "JLG Service & Maintenance Manual 3120840",
            "tasks": [
                OEMTask(
                    task_name="Inspección de mangueras hidráulicas y líneas de frenos",
                    interval_hours=250,
                    system="Hidráulico",
                    reference_manual="JLG Manual 3120840 pág. 52"
                ),
                OEMTask(
                    task_name="Servicio a motor diésel Deutz D2011 (Aceite y filtros)",
                    interval_hours=500,
                    system="Motor",
                    fluid_spec="Deutz Oil 15W-40 (10 Litros)",
                    required_parts_oem=["JLG-7024376 (Filtro Aceite)"],
                    reference_manual="JLG Manual 3120840 pág. 68"
                ),
                OEMTask(
                    task_name="Calibración anual del sensor de carga en plataforma",
                    interval_hours=1000,
                    system="Seguridad / Control",
                    reference_manual="JLG Manual 3120840 pág. 95"
                )
            ]
        }
    }

    @classmethod
    def get_oem_plan(cls, brand: str, model: str, year: int) -> dict[str, Any]:
        """
        Retorna el plan de mantenimiento OEM homologado con trazabilidad documental.
        Si el modelo no está en catálogo específico, aplica heurística industrial segura.
        """
        key = (brand.strip().lower(), model.strip().lower())
        entry = cls._CATALOG.get(key)
        
        if entry:
            return {
                "source": "CATALOGO_OFICIAL_OEM",
                "manual_reference": entry["manual"],
                "equipment_type": entry["equipment_type"],
                "tasks": [t.model_dump() for t in entry["tasks"]],
                "confidence": 1.0
            }
        
        # Heurística industrial por defecto (ISO 55000 / Estándar Minero)
        default_tasks = [
            OEMTask(
                task_name=f"Servicio PM1 ({brand} {model}) - Cambio de aceite y filtros de motor",
                interval_hours=250,
                system="Motor",
                fluid_spec="Multigrado 15W-40 CK-4 / CI-4",
                reference_manual="Estándar Industrial Preventivo ISO 55000"
            ),
            OEMTask(
                task_name="Servicio PM2 - Filtros de combustible, aire y correas",
                interval_hours=500,
                system="Admisión / Combustible",
                reference_manual="Estándar Industrial Preventivo ISO 55000"
            ),
            OEMTask(
                task_name="Servicio PM3 - Aceite de transmisión y fluidos hidráulicos",
                interval_hours=1000,
                system="Tren de Potencia",
                reference_manual="Estándar Industrial Preventivo ISO 55000"
            )
        ]
        return {
            "source": "HEURISTICA_INDUSTRIAL_ISO55000",
            "manual_reference": "Norma General de Mantenimiento Preventivo Maquinaria Pesada",
            "equipment_type": "Maquinaria Industrial General",
            "tasks": [t.model_dump() for t in default_tasks],
            "confidence": 0.85
        }
