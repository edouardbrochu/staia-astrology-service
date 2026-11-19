# Staia Astrology Service

FastAPI astrology compute service powered by
[Kerykeion](https://github.com/g-battaglia/kerykeion).

This service is published separately from the private Staia/Staia app repository
to preserve the AGPL boundary around Kerykeion-derived code. The private backend
must call it over HTTP and must not import this package directly.

## API Surface

All v1 routes are mounted under `/api/v1` and require the internal service token
configured through `ASTROLOGY_SERVICE_TOKEN`.

- `POST /api/v1/astrology/profile`
- `POST /api/v1/astrology/profile/lookup`
- `POST /api/v1/astrology/profile/monthly`
- `POST /api/v1/astrology/profile/placements`
- `POST /api/v1/astrology/synastry`
- `POST /api/v1/astrology/composite`
- `POST /api/v1/astrology/transits/period`
- `GET /health`

Request models live in `app/models/requests.py`; response models live in
`app/models/responses.py`.

## Local Development

Create a virtual environment and install the standalone service dependencies:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
```

Run the service locally:

```bash
ENV=dev \
ASTROLOGY_SERVICE_TOKEN=dev-token \
PYTHONPATH=. \
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

Run the public service test suite:

```bash
PYTHONPATH=. pytest tests -v
```

## Runtime Boundary

Each endpoint under `app/api/v1/` includes a caller comment in this form:

```python
# Called by: backend/app/infrastructure/repositories/http_astrology_repository.py
```

Inside the private repository, the contract checker verifies endpoint ownership
and prevents cross-imports between the private backend and this service.

## License

This service is licensed under AGPL-3.0 because it uses Kerykeion. See
`LICENSE` for the full license text.
