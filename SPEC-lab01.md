# Especificación: Lab 01, App containerizada

## Objetivo
Primer laboratorio de mi portfolio DevOps. **No importa tanto la app como la forma de empaquetarla y correrla**: buenas prácticas de Docker, Docker Compose y seguridad de imágenes con Trivy. Cualquier persona tiene que poder clonar el repo y levantar todo con un comando.

Es un proyecto para aprender: el código tiene que ser claro y estar comentado donde haya una decisión importante (por qué multi-stage, por qué usuario no-root, etc.).

## La aplicación: "RunLog"
Un registro de salidas a correr (soy runner amateur). Simple, pero con una arquitectura de 3 servicios realista:

```
navegador ──► nginx (:8080) ──► /        → frontend estático (HTML + JS vanilla)
                            └─► /api/*   → api (FastAPI, Python)  ──► db (PostgreSQL)
```

- **api**: Python 3.12 + FastAPI + SQLAlchemy + psycopg.
  - `GET /api/health`: estado de la API y de la conexión a la base (para los healthchecks).
  - `GET /api/runs`: lista de salidas (fecha, distancia en km, duración, ritmo calculado en min/km, notas).
  - `POST /api/runs`: crear una salida.
  - `DELETE /api/runs/{id}`: borrar una salida.
  - `GET /api/stats`: km totales, cantidad de salidas, ritmo promedio y salida más larga.
  - Crea las tablas al iniciar y carga algunos datos de ejemplo si la base está vacía.
- **web**: nginx que sirve una página única (HTML + CSS + JS vanilla, sin frameworks) con las stats arriba, un formulario para agregar salidas y la tabla. Diseño oscuro y simple. También hace de reverse proxy de `/api` hacia la api.
- **db**: PostgreSQL 16 (alpine).

## Docker: lo que el lab tiene que mostrar
### Dockerfile de la api (`api/Dockerfile`)
- **Multi-stage**: una etapa `builder` que instala dependencias en un venv, y una etapa final `python:3.12-slim` que solo copia el venv y el código.
- **Usuario no-root** (uid fijo, por ejemplo 10001).
- `HEALTHCHECK` contra `/api/health`.
- Versiones fijadas (imagen base con tag específico y `requirements.txt` con versiones exactas).
- `PYTHONDONTWRITEBYTECODE`, `PYTHONUNBUFFERED`, `--no-cache-dir`.
- Labels OCI (`org.opencontainers.image.source`, `.description`, etc.).
- `.dockerignore`.

### Comparación "antes / después" (clave del lab)
- Incluir `api/Dockerfile.naive`: un Dockerfile **ingenuo a propósito** (imagen `python:3.12` completa, corre como root, sin multi-stage, copia todo).
- `make compare` construye las dos imágenes y muestra lado a lado:
  - el tamaño de cada imagen;
  - la cantidad de vulnerabilidades CRITICAL/HIGH según Trivy.
- Los resultados reales van a una tabla en el README.

### Docker Compose (`compose.yaml`)
- Los 3 servicios con **healthchecks**, y `depends_on` con `condition: service_healthy` (la api espera a la db y web espera a la api).
- **Dos redes**: `frontend` (web ↔ api) y `backend` (api ↔ db, `internal: true`). **La base no se expone al host.**
- Volumen nombrado para los datos de Postgres.
- Configuración por variables de entorno: `.env.example` versionado y `.env` en `.gitignore`.
- `restart: unless-stopped` y límites de recursos (`deploy.resources.limits`).
- El único puerto expuesto al host es el de web, 8080.
- Un `compose.override.yaml` opcional para desarrollo (hot reload de la api, montando el código como volumen).

## Seguridad con Trivy
- `make scan`: escanea la imagen de la api con Trivy (usando la imagen Docker oficial de Trivy, sin instalar nada) y **falla si hay vulnerabilidades CRITICAL**.
- `make scan-config`: escanea los Dockerfiles y el compose en busca de malas configuraciones (`trivy config`).
- Un `.trivyignore` vacío con un comentario que explique cuándo usarlo.

## CI mínimo (GitHub Actions)
`.github/workflows/ci.yml`, en cada push y PR:
1. Lint de Python (ruff) y tests (pytest).
2. Lint del Dockerfile con hadolint.
3. Build de la imagen.
4. Escaneo con Trivy: falla con CRITICAL y sube el reporte SARIF a la pestaña Security de GitHub.
5. Solo en `main`: publica la imagen en **GitHub Container Registry** (`ghcr.io/citurria24/devops-docker-app-api`), con tag `latest` y el SHA corto.

El pipeline completo (deploy, entornos) queda para el Lab 02; acá alcanza con build, test y scan.

## Tests
- pytest con al menos: health, crear salida, listar, cálculo de ritmo, stats y borrar.
- Pueden correr contra SQLite en memoria para no necesitar Postgres en CI.

## Makefile
`make help` (por defecto), `up`, `down`, `logs`, `ps`, `test`, `lint`, `scan`, `scan-config`, `compare`, `clean` (baja todo y borra volúmenes, avisando antes).

## README.md (en español, con una sección corta en inglés al final)
1. Qué es y qué demuestra, en 3 líneas.
2. Diagrama de arquitectura en Mermaid.
3. **Quickstart**: requisitos (Docker y Docker Compose) y `git clone` + `cp .env.example .env` + `make up`, después abrir http://localhost:8080.
4. Tabla **"Naive vs optimizado"** con los resultados reales de `make compare`.
5. **Decisiones técnicas**: por qué multi-stage, no-root, redes separadas, healthchecks, versiones fijadas y Trivy en CI.
6. Comandos útiles (la tabla del Makefile).
7. Qué aprendí y qué mejoraría.
8. Badge del workflow de CI.

## Criterios de aceptación
- `cp .env.example .env && make up` levanta todo, y en http://localhost:8080 se ve la app con datos de ejemplo.
- `docker compose ps` muestra los 3 servicios como `healthy`.
- La db no tiene puertos publicados al host.
- `make test`, `make scan` y `make compare` funcionan.
- `docker compose exec api whoami` no devuelve `root`.
- La tabla de la comparación en el README tiene números reales, no inventados.
