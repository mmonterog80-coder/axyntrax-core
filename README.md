# Axyntrax Core

Industrial equipment telemetry, anti-fraud horometer verification, and maintenance management API.

> **Status:** Working prototype. API state is managed in-memory with seed fixtures and resets on process restart.

---

## Overview

Axyntrax Core provides an API gateway and calculation engine built with FastAPI and Pydantic v2. It validates telemetry data from heavy machinery, prevents fraudulent hour-meter manipulation, monitors fuel consumption efficiency, and manages preventative maintenance schedules.

### Key Capabilities
- **Anti-Fraud Horometer Engine:** Strict monotonicity validation, clock physical delta checks, and sample Traccar-style jitter filtering.
- **Preventative Maintenance Scheduler:** Sample OEM standard service interval projections (PM1 to PM4, 250h to 2000h) for Caterpillar and Komatsu equipment.
- **Fuel Mass-Balance Verification:** Tank capacity overfill prevention and burn-rate anomaly detection (L/h).
- **Offline-First Synchronization:** Batch processing for field data collected without network connectivity.
- **HMAC Work Order Integrity:** Cryptographic sealing of completed work orders with tamper detection.
- **Simulated Invoicing & Webhook Verification:** IGV 18% calculation and a simulated invoice record (fixed series F001 and correlative 1001, so every invoice gets the same number); no UBL XML is generated and no external SUNAT or payment gateway API call is made.

---

## Architecture

```
axyntrax_core/
├── api.py               # FastAPI REST endpoints & dependency wiring
├── models.py            # Pydantic v2 domain schemas
├── engine.py            # Horometer fraud & fuel calculation engine
├── oem_catalog.py       # Standard OEM maintenance intervals
├── sync_engine.py       # Offline batch sync processing
├── work_orders.py       # Lifecycle & cryptographic signing
├── billing.py           # Invoicing calculations and webhook validation (simulated)
├── kpi_engine.py        # Equipment availability and MTBF metrics
└── security/
    ├── integrity_guard.py   # Runtime environment & checksum verification
    └── license_verifier.py  # Hardware fingerprint license tokens
```

---

## Installation & Running

### Requirements
- Python 3.11+ (Tested on Windows with Python 3.14)
- `uv` (recommended) or `pip`

### Setup

```bash
# Clone the repository
git clone https://github.com/mmonterog80-coder/axyntrax-core.git
cd axyntrax-core

# Create virtual environment and install dependencies
uv venv
uv pip install -e ".[dev]"

# Set required signing key in your shell (.env files are not loaded automatically)
# PowerShell:
$env:AXYNTRAX_SIGNING_SECRET="your-32-byte-secret-key-here"
# Linux / macOS:
export AXYNTRAX_SIGNING_SECRET="your-32-byte-secret-key-here"
```

### Run API Server

```bash
uv run uvicorn axyntrax_core.api:app --host 127.0.0.1 --port 8000 --reload
```

Interactive documentation is available at `http://localhost:8000/docs`.

> **Security Note:** In this working prototype, a single signing key (`AXYNTRAX_SIGNING_SECRET`) is used across work order certification, licensing, and webhook demo fixtures; in production environments, use distinct isolated keys per purpose.

---

## Automated Testing & Quality

Tests cover the core calculation engine, security guardrails, offline sync, and API endpoints:

```bash
# Run tests with pytest (conftest.py automatically provides the test signing secret):
pytest --cov=axyntrax_core

# Or using uv directly in dev environment:
uv run --with pytest-cov pytest --cov=axyntrax_core
```

- **Environment Tested:** Windows (Python 3.14).
- **Suite Status:** 35 passed tests.
- **Production Code Coverage:** ~94% (411/437 covered statements across production modules).

---

## License

Copyright (c) 2026 Miguel Montero. All rights reserved. Source published for portfolio review.
