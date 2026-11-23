# RunLog: la app vista por quien la va a containerizar

Este documento describe **qué hay que empaquetar** y **cómo se comporta la app**,
sin entrar en Docker. Es la "ficha técnica" para escribir los Dockerfiles, el
`compose.yaml` y el `nginx.conf`.

## Estructura

```
.
├── api/                      # servicio "api" (Python 3.12 + FastAPI)
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py           # app FastAPI: endpoints, lifespan (crea tablas + seed)
│   │   ├── database.py       # engine/sesiones; lee DATABASE_URL
│   │   ├── models.py         # tabla "runs" (SQLAlchemy)
│   │   ├── schemas.py        # modelos Pydantic + cálculo de ritmo
│   │   └── seed.py           # datos de ejemplo si la tabla está vacía
│   ├── tests/                # pytest (SQLite en memoria, sin Postgres)
│   ├── requirements.txt      # runtime, versiones exactas  → VA en la imagen
│   ├── requirements-dev.txt  # pytest, httpx, ruff         → NO va en la imagen
│   └── pyproject.toml        # config de pytest y ruff (no es un paquete instalable)
├── web/
│   └── index.html            # servicio "web": un único archivo estático para nginx
├── SPEC-lab01.md
└── APP.md
```

## Servicio `api`

| Ítem | Valor |
|---|---|
| Runtime | Python 3.12 |
| Instalación | `pip install --no-cache-dir -r requirements.txt` |
| Módulo ASGI | `app.main:app` (el directorio de trabajo tiene que ser `api/`, el que contiene `app/`) |
| Arranque | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Puerto | **8000** (HTTP). Ojo: dentro de un contenedor hay que usar `--host 0.0.0.0`; el default de uvicorn (`127.0.0.1`) no es accesible desde fuera. |
| Healthcheck | `GET /api/health` → `200 {"status":"ok","database":"ok"}` o `503 {"status":"error","database":"unreachable"}` |
| Estado en disco | Ninguno con Postgres (stateless). Solo en modo SQLite escribe `runlog.db` en el directorio de trabajo. |
| Dependencias de sistema | Ninguna: `psycopg[binary]` trae libpq precompilada, así que en `python:3.12-slim` no hace falta `apt-get`. |

### Variables de entorno

| Variable | Default | Para qué |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./runlog.db` | URL de la base. Para Postgres: `postgresql+psycopg://USER:PASS@HOST:5432/DB`. También se acepta `postgresql://` o `postgres://`, que se convierten solas al driver psycopg 3. En compose, HOST es el nombre del servicio (`db`). |
| `SEED_SAMPLE_DATA` | `true` | Si es `true`, carga 5 salidas de ejemplo **solo si la tabla está vacía**. Es idempotente: reiniciar no duplica datos. |
| `LOG_LEVEL` | `INFO` | Nivel de log de la app. |
| `WEB_DIR` | *(sin definir)* | **Solo para desarrollo sin Docker.** Si apunta a la carpeta `web/`, la api también sirve el frontend en `/`. En contenedores **no se define**: eso lo hace nginx. |

> La api no lee `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`: esas son de la
> imagen de Postgres. En compose podés armar `DATABASE_URL` a partir de ellas,
> por ejemplo con `postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}`.

### Comportamiento al arrancar

1. Ejecuta `CREATE TABLE IF NOT EXISTS` (vía `metadata.create_all`). No hay migraciones.
2. Si la base todavía no responde, **reintenta 10 veces cada 2 s** (unos 20 s en total) y después falla
   y el proceso termina. Igual conviene `depends_on: condition: service_healthy` sobre `db`.
3. Carga los datos de ejemplo si corresponde.
4. Loguea en stdout/stderr, que es lo que esperan `docker logs` y `docker compose logs`.
   No escribe archivos de log.

### Healthcheck

`GET /api/health` ejecuta `SELECT 1` contra la base, así que una api "healthy" significa que **la api
responde y la base también**. La imagen `python:3.12-slim` **no trae `curl` ni `wget`**, así que
para el `HEALTHCHECK` lo más simple es usar el propio Python:

```
python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health', timeout=3).status == 200 else 1)"
```

(`urlopen` lanza una excepción ante un 503, y eso también da exit code ≠ 0.)

### Endpoints

| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/api/health` | 200 / 503 (ver arriba) |
| GET | `/api/runs` | lista de salidas, de la más nueva a la más vieja |
| POST | `/api/runs` | body `{"date":"2026-11-20","distance_km":10,"duration_seconds":3000,"notes":""}` → 201 |
| DELETE | `/api/runs/{id}` | 204, o 404 si no existe |
| GET | `/api/stats` | `total_km`, `total_runs`, `avg_pace` (ponderado: tiempo total / km totales), `longest_run` |
| GET | `/docs` | Swagger UI autogenerada por FastAPI (útil para probar; queda **fuera** de `/api`) |

Cada salida devuelve además `pace` (`"5:30"`) y `pace_min_per_km` (`5.5`), que se calculan al
vuelo y no se guardan en la base.

## Servicio `web`

- Es **un único archivo estático**: `web/index.html` (con el CSS y el JS adentro). No tiene build
  ni dependencias.
- Llama a la api con **rutas relativas** (`/api/runs`, `/api/stats`…), así que el navegador le pide
  todo al mismo origen que sirvió la página. Por eso nginx tiene que:
  - servir `index.html` en `/`;
  - reenviar `/api/` a `http://api:8000` **conservando el prefijo `/api`**, porque la api tiene
    las rutas definidas con `/api` adelante. Ojo con la barra final en `proxy_pass`: con
    `proxy_pass http://api:8000;` (sin `/` al final) se conserva la ruta completa.
- Como todo pasa por el mismo origen, **no hace falta CORS** y la api no lo habilita.

## Qué NO debería ir dentro de una imagen

| Archivo / carpeta | Por qué |
|---|---|
| `api/.venv/` | venv local, atado a tu máquina (rutas absolutas y binarios del host). La imagen arma el suyo. |
| `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/` | artefactos generados, ensucian la imagen y rompen el cache de capas |
| `runlog.db` (y `*.db`) | base SQLite de pruebas local: son datos, no código |
| `api/tests/`, `requirements-dev.txt` | solo sirven para CI/desarrollo. La imagen de producción no necesita pytest ni ruff (menos tamaño y menos CVEs) |
| `.env` | **secretos**. Se inyectan en runtime (`env_file`/`environment`), nunca se copian a una capa |
| `.git/`, `.github/` | historia del repo y CI, pesados e irrelevantes en runtime |
| `*.md`, `SPEC-lab01.md` | documentación |
| `Dockerfile*`, `compose*.yaml`, `Makefile`, `.trivyignore` | infraestructura, no código de la app |
| `web/` (en la imagen de la **api**) | lo sirve nginx, que tiene su propia imagen |

Lo único que necesita la imagen de la api es **`requirements.txt` + `app/`**. La imagen de web solo
necesita **`index.html`** (y tu `nginx.conf`).

Además, hace falta un `.gitignore` (es parte de tu tarea) con al menos: `.venv/`, `__pycache__/`,
`*.db`, `.env`, `.pytest_cache/` y `.ruff_cache/`.

## Correrla local sin Docker

```bash
cd api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# tests y lint
pytest
ruff check app tests

# api + frontend en http://localhost:8000 (SQLite en ./runlog.db)
WEB_DIR=../web uvicorn app.main:app --reload --port 8000
```

Contra un Postgres que ya tengas corriendo:

```bash
DATABASE_URL=postgresql+psycopg://runlog:runlog@localhost:5432/runlog \
  WEB_DIR=../web uvicorn app.main:app --reload --port 8000
```
