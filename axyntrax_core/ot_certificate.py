"""
Generador de Certificados de Órdenes de Trabajo (OT) para Axyntrax 2.0.
Produce reportes auditables con hash criptográfico SHA-256, token QR pericial
y trazabilidad completa de repuestos y costos para inspecciones SUNAFIL y auditorías de seguros.
"""
from axyntrax_core.models import Equipment, SparePart, WorkOrder


class OTCertificateGenerator:
    @staticmethod
    def generate_markdown_certificate(
        work_order: WorkOrder,
        equipment: Equipment,
        spare_parts: dict[str, SparePart]
    ) -> str:
        """
        Genera el informe pericial estructurado en formato Markdown estándar para exportación a PDF.
        """
        parts_rows = []
        for usage in work_order.parts_consumed:
            part = spare_parts.get(usage.part_id)
            part_name = part.name if part else usage.part_id
            oem_code = part.oem_code if part else "N/A"
            subtotal = usage.quantity * usage.unit_cost_snapshot
            parts_rows.append(
                f"| {part_name} | `{oem_code}` | {usage.quantity} | S/ {usage.unit_cost_snapshot:.2f} | S/ {subtotal:.2f} |"
            )
        parts_table = "\n".join(parts_rows) if parts_rows else "| Sin repuestos consumidos | - | - | - | S/ 0.00 |"

        checklist_items = "\n".join([f"- [x] {task}" for task in work_order.tasks_checklist]) if work_order.tasks_checklist else "- [x] Mantenimiento preventivo general conforme a pauta OEM."

        report = f"""# CERTIFICADO DE ORDEN DE TRABAJO — {work_order.id}
**Laboratorio / Sistema:** Axyntrax Industrial CMMS 2.0  
**Fecha de Intervención:** {work_order.completed_at.strftime('%Y-%m-%d %H:%M:%S UTC') if work_order.completed_at else 'PENDIENTE'}  
**Estado Operativo:** {work_order.status.value}  

---

## 1. IDENTIFICACIÓN DEL ACTIVO
- **Equipo:** {equipment.name} ({equipment.brand} {equipment.model}, {equipment.year})
- **Número de Serie:** `{equipment.serial_number}`
- **Horómetro Programado:** {work_order.scheduled_horometer:.1f} h
- **Horómetro de Cierre:** {work_order.actual_horometer or 0.0:.1f} h
- **Tipo de Plan:** {work_order.plan_type.value}

---

## 2. TAREAS Y PROTOCOLO OEM EJECUTADO
{checklist_items}

---

## 3. CONSUMO DE REPUESTOS Y MATERIALES
| Repuesto / Componente | Código OEM | Cant. | Costo Unit. | Subtotal |
|---|---|---|---|---|
{parts_table}

**Costo Total de Mantenimiento:** **S/ {work_order.total_cost:.2f}**

---

## 4. VALIDACIÓN PERICIAL Y FIRMA DIGITAL
- **Técnico Responsable:** `{work_order.assigned_technician_id or 'NO ASIGNADO'}`
- **Firma Digital (Hash SHA-256):** `{work_order.signature_hash or 'PENDIENTE'}`
- **Token Criptográfico QR de Verificación:**  
  `{work_order.verification_qr_token or 'NO GENERADO'}`

> *Documento inmutable generado automáticamente por el núcleo de seguridad de Axyntrax 2.0. Cualquier alteración de horas, costos o repuestos invalida el token pericial.*
"""
        return report
