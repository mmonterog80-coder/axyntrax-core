"""
Módulo de cálculo de facturación simulada (IGV 18%) y verificación criptográfica de webhooks de pago.
Genera registros de facturación estructurados con hash tributario y emite licencias instantáneamente.
No realiza llamadas externas a SUNAT ni pasarelas en tiempo de ejecución.
"""
import hashlib
import hmac
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from axyntrax_core.security.license_verifier import LicenseVerifier


class WebhookPaymentPayload(BaseModel):
    event: str  # charge.succeeded
    company_id: str
    company_ruc: str
    customer_email: str
    plan_name: str
    amount_pen: float  # Monto en Soles (PEN)
    currency: str = "PEN"
    device_fingerprint: str
    payment_method: str  # yape, visa, mastercard
    culqi_charge_id: str


class SunatInvoiceResult(BaseModel):
    invoice_number: str  # F001-000123
    company_ruc: str
    subtotal: float
    igv_18_pct: float
    total: float
    digest_value_hash: str
    sunat_status: str  # SIMULATED_ACCEPTED
    cdr_response_code: str = "0"
    qr_data: str
    issued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BillingEngine:
    IGV_RATE = 0.18

    @classmethod
    def verify_culqi_webhook(cls, raw_payload: bytes, signature_header: str, secret_key: bytes) -> bool:
        """
        Verificación de firma criptográfica de webhook de pasarela para prevenir ataques de inyección de pagos falsos.
        """
        computed_sig = hmac.new(secret_key, raw_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed_sig, signature_header)

    @classmethod
    def generate_sunat_invoice(cls, payment: WebhookPaymentPayload, series: str = "F001", correlative: int = 1001) -> SunatInvoiceResult:
        """
        Genera el comprobante electrónico simulado con cálculo de IGV (18%) y hash criptográfico.
        """
        total = payment.amount_pen
        subtotal = round(total / (1.0 + cls.IGV_RATE), 2)
        igv = round(total - subtotal, 2)

        invoice_id = f"{series}-{correlative:08d}"
        
        # Cálculo de DigestValue simulado (hash SHA-256 de campos clave para integridad)
        hash_seed = f"{payment.company_ruc}|01|{series}|{correlative}|{igv}|{total}|{payment.customer_email}"
        digest_value = hashlib.sha256(hash_seed.encode()).hexdigest()

        # Cadena estructurada para código QR simulado
        qr_string = f"{payment.company_ruc}|01|{series}|{correlative}|{igv:.2f}|{total:.2f}|{datetime.now(UTC).strftime('%Y-%m-%d')}|1|{digest_value[:8]}"

        return SunatInvoiceResult(
            invoice_number=invoice_id,
            company_ruc=payment.company_ruc,
            subtotal=subtotal,
            igv_18_pct=igv,
            total=total,
            digest_value_hash=digest_value,
            sunat_status="SIMULATED_ACCEPTED",
            cdr_response_code="0",
            qr_data=qr_string
        )

    @classmethod
    def process_automated_subscription(
        cls,
        payment: WebhookPaymentPayload,
        license_signing_key: bytes
    ) -> tuple[SunatInvoiceResult, str]:
        """
        Flujo de activación automática sin fricción (simulado):
        1. Emite el registro simulado de factura electrónica con status aceptado.
        2. Emite la licencia criptográfica Axyntrax vinculada al hardware.
        """
        invoice = cls.generate_sunat_invoice(payment)
        
        # Determinar límite de máquinas según plan
        asset_limits = {"Basico": 15, "Pro": 30, "Elite": 100, "Enterprise": 500}
        max_assets = asset_limits.get(payment.plan_name, 30)

        verifier = LicenseVerifier(license_signing_key)
        license_token = verifier.generate_license_token(
            company_id=payment.company_id,
            plan=payment.plan_name,
            max_assets=max_assets,
            device_fingerprint=payment.device_fingerprint,
            duration_days=30
        )

        return invoice, license_token
