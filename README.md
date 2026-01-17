# Taiga Backend

[![Managed with Taiga.io](https://img.shields.io/badge/managed%20with-TAIGA.io-709f14.svg)](https://tree.taiga.io/project/taiga/ "Managed with Taiga.io")

> **Fork UPC**: Esta versión incluye integración con Google SSO y sistema de métricas para Learning Dashboard.

## Tabla de Contenidos

- [Características Añadidas](#características-añadidas)
- [Requisitos](#requisitos)
- [Instalación para Desarrollo](#instalación-para-desarrollo)
- [Configuración](#configuración)
- [Variables de Entorno](#variables-de-entorno)
- [Google OAuth Setup](#google-oauth-setup)
- [Sistema de Métricas](#sistema-de-métricas)
- [Docker](#docker)
- [Tests](#tests)
- [API Documentation](#api-documentation)
- [Troubleshooting](#troubleshooting)

---

## Características Añadidas

Esta versión fork incluye las siguientes mejoras:

1. **Google SSO Authentication**: Login con cuentas Google institucionales (UPC)
2. **Sistema de Métricas Interno**: Cálculo de métricas de proyecto para Learning Dashboard
3. **Integración Learning Dashboard**: API para sincronización de métricas con LD-Taiga

---

## Requisitos

- Python 3.11+
- PostgreSQL 12+
- RabbitMQ 3.8+ (para eventos y tareas async)
- Redis (opcional, para caché)

---

## Instalación para Desarrollo

### 1. Clonar el repositorio

```bash
git clone <repository-url>
cd taiga-back
```

### 2. Crear entorno virtual

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# o en Windows: .venv\Scripts\activate
```

### 3. Instalar dependencias

```bash
pip install --upgrade pip wheel
pip install -r requirements.txt
pip install -r requirements-contribs.txt
pip install -r requirements-devel.txt  # Solo para desarrollo
```

### 4. Configurar settings

```bash
cp settings/config.py.dev.example settings/config.py
```

Edita `settings/config.py` según tu entorno (ver sección [Configuración](#configuración)).

### 5. Configurar base de datos

```bash
# Crear base de datos PostgreSQL
createdb taiga

# Aplicar migraciones
python manage.py migrate

# Cargar datos iniciales
python manage.py loaddata initial_project_templates

# Compilar mensajes de traducción
python manage.py compilemessages

# Recopilar archivos estáticos
python manage.py collectstatic --no-input
```

### 6. Crear superusuario

```bash
python manage.py createsuperuser
```

### 7. Ejecutar servidor de desarrollo

```bash
python manage.py runserver 0.0.0.0:8000
```

El backend estará disponible en `http://localhost:8000`

---

## Configuración

### Archivo de Configuración

El archivo principal de configuración es `settings/config.py`. Puedes partir de los ejemplos:

- `settings/config.py.dev.example` - Configuración para desarrollo local
- `settings/config.py.prod.example` - Configuración para producción

### Configuración Mínima para Desarrollo

```python
# settings/config.py
from .common import *

DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'taiga',
        'USER': 'taiga',
        'PASSWORD': 'taiga',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

SECRET_KEY = "development-secret-key-change-in-production"

TAIGA_SITES_SCHEME = "http"
TAIGA_SITES_DOMAIN = "localhost:9000"

# Deshabilitar telemetría en desarrollo
ENABLE_TELEMETRY = False
```

---

## Variables de Entorno

El backend soporta configuración mediante variables de entorno. Aquí está la referencia completa:

### Variables Principales

| Variable | Descripción | Valor por Defecto | Requerido |
|----------|-------------|-------------------|-----------|
| `POSTGRES_DB` | Nombre de la base de datos | `taiga` | Sí |
| `POSTGRES_USER` | Usuario PostgreSQL | `taiga` | Sí |
| `POSTGRES_PASSWORD` | Contraseña PostgreSQL | - | Sí |
| `POSTGRES_HOST` | Host PostgreSQL | `localhost` | Sí |
| `POSTGRES_PORT` | Puerto PostgreSQL | `5432` | No |
| `TAIGA_SECRET_KEY` | Clave secreta Django | - | **Sí (producción)** |
| `TAIGA_SITES_SCHEME` | Protocolo (`http`/`https`) | `http` | Sí |
| `TAIGA_SITES_DOMAIN` | Dominio de Taiga | `localhost:9000` | Sí |
| `TAIGA_SUBPATH` | Subpath (ej: `/taiga`) | `""` | No |
| `DEBUG` | Modo debug | `False` | No |

### Variables de Email

| Variable | Descripción | Valor por Defecto |
|----------|-------------|-------------------|
| `EMAIL_BACKEND` | Backend de email | `django.core.mail.backends.console.EmailBackend` |
| `EMAIL_HOST` | Servidor SMTP | `localhost` |
| `EMAIL_PORT` | Puerto SMTP | `587` |
| `EMAIL_HOST_USER` | Usuario SMTP | - |
| `EMAIL_HOST_PASSWORD` | Contraseña SMTP | - |
| `EMAIL_USE_TLS` | Usar TLS | `False` |
| `EMAIL_USE_SSL` | Usar SSL | `False` |
| `DEFAULT_FROM_EMAIL` | Email remitente | `system@taiga.io` |

### Variables de RabbitMQ

| Variable | Descripción | Valor por Defecto |
|----------|-------------|-------------------|
| `RABBITMQ_USER` | Usuario RabbitMQ | `guest` |
| `RABBITMQ_PASS` | Contraseña RabbitMQ | `guest` |
| `TAIGA_EVENTS_RABBITMQ_HOST` | Host RabbitMQ eventos | `taiga-events-rabbitmq` |
| `TAIGA_ASYNC_RABBITMQ_HOST` | Host RabbitMQ async | `taiga-async-rabbitmq` |

### Variables de Google SSO (NUEVO)

| Variable | Descripción | Valor por Defecto | Requerido |
|----------|-------------|-------------------|-----------|
| `GOOGLE_AUTH_ENABLED` | Habilitar Google SSO | `True` si hay Client IDs | No |
| `GOOGLE_AUTH_CLIENT_IDS` | Client IDs de Google OAuth (separados por coma) | - | **Sí para SSO** |
| `GOOGLE_AUTH_ALLOWED_DOMAINS` | Dominios permitidos (separados por coma) | `upc.edu,estudiantat.upc.edu` | **Sí para SSO** |
| `GOOGLE_AUTH_AUTO_CREATE` | Auto-crear usuarios en primer login | `True` | No |

### Variables de Métricas (NUEVO)

| Variable | Descripción | Valor por Defecto |
|----------|-------------|-------------------|
| `TAIGA_METRICS_PROVIDER` | Proveedor de métricas (`internal`/`external`) | `internal` |
| `TAIGA_METRICS_SNAPSHOT_TTL` | TTL del caché de métricas (minutos) | `60` |
| `LD_TAIGA_BACKEND_URL` | URL del backend Learning Dashboard | - |
| `LD_TAIGA_TIMEOUT` | Timeout para requests a LD (segundos) | `15` |

### Variables de Seguridad

| Variable | Descripción | Valor por Defecto |
|----------|-------------|-------------------|
| `SESSION_COOKIE_SECURE` | Cookie de sesión solo HTTPS | `True` |
| `CSRF_COOKIE_SECURE` | Cookie CSRF solo HTTPS | `True` |
| `PUBLIC_REGISTER_ENABLED` | Permitir registro público | `False` |
| `WEBHOOKS_ENABLED` | Habilitar webhooks | `True` |

### Variables de Integraciones OAuth (Opcionales)

| Variable | Descripción |
|----------|-------------|
| `ENABLE_GITHUB_AUTH` | Habilitar login con GitHub |
| `GITHUB_API_CLIENT_ID` | Client ID de GitHub |
| `GITHUB_API_CLIENT_SECRET` | Client Secret de GitHub |
| `ENABLE_GITLAB_AUTH` | Habilitar login con GitLab |
| `GITLAB_API_CLIENT_ID` | Client ID de GitLab |
| `GITLAB_API_CLIENT_SECRET` | Client Secret de GitLab |
| `GITLAB_URL` | URL de GitLab |

---

## Google OAuth Setup

### Paso 1: Crear Proyecto en Google Cloud Console

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un nuevo proyecto o selecciona uno existente
3. Ve a **APIs & Services > Credentials**

### Paso 2: Configurar OAuth Consent Screen

1. Ve a **OAuth consent screen**
2. Selecciona **Internal** (si es para organización) o **External**
3. Configura:
   - App name: `Taiga`
   - User support email: tu email
   - Authorized domains: tu dominio
4. En **Scopes**, añade:
   - `email`
   - `profile`
   - `openid`

### Paso 3: Crear OAuth Client ID

1. Ve a **Credentials > Create Credentials > OAuth client ID**
2. Application type: **Web application**
3. Name: `Taiga Web Client`
4. **Authorized JavaScript origins**:
   ```
   http://localhost:9000          # Desarrollo
   https://tu-dominio.com         # Producción
   ```
5. **Authorized redirect URIs**: No necesario (usamos popup flow)
6. Guarda el **Client ID** generado

### Paso 4: Configurar Backend

Añade las variables de entorno:

```bash
export GOOGLE_AUTH_CLIENT_IDS="tu-client-id.apps.googleusercontent.com"
export GOOGLE_AUTH_ALLOWED_DOMAINS="tu-dominio.com,otro-dominio.com"
export GOOGLE_AUTH_ENABLED="True"
export GOOGLE_AUTH_AUTO_CREATE="True"
```

O en `settings/config.py`:

```python
GOOGLE_AUTH = {
    "ENABLED": True,
    "CLIENT_IDS": ["tu-client-id.apps.googleusercontent.com"],
    "ALLOWED_DOMAINS": ["tu-dominio.com"],
    "AUTO_CREATE_USERS": True,
}
```

### Paso 5: Configurar Frontend

En `taiga-front/conf/conf.json`:

```json
{
    "googleAuth": {
        "enabled": true,
        "clientId": "tu-client-id.apps.googleusercontent.com",
        "allowedDomains": ["tu-dominio.com"]
    }
}
```

### Notas Importantes

- El **Client ID debe ser el mismo** en frontend y backend
- Los **dominios permitidos deben coincidir** en frontend y backend
- En producción, **HTTPS es obligatorio** para Google OAuth
- Si `AUTO_CREATE_USERS` es `True`, los usuarios se crean automáticamente en el primer login

---

## Sistema de Métricas

### Descripción

El sistema de métricas calcula estadísticas de proyecto para integración con Learning Dashboard:

- User Stories asignadas/completadas por usuario
- Tasks asignadas/completadas por usuario
- Puntos de historia por sprint
- Velocidad del equipo

### Módulo

```
taiga/projects/metrics/
├── __init__.py
├── api.py              # ViewSet de la API
├── base.py             # Clase base y utilidades
├── internal.py         # Calculador de métricas interno
├── models.py           # Modelo ProjectMetricsSnapshot
└── serializers.py      # Serializadores
```

### Endpoints API

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/v1/metrics/current` | GET | Métricas actuales del proyecto |
| `/api/v1/metrics/categories` | GET | Categorías de métricas disponibles |

### Parámetros

- `prj` (requerido): Slug del proyecto
- `profile` (opcional): ID del perfil/usuario

### Ejemplo de Uso

```bash
curl "http://localhost:8000/api/v1/metrics/current?prj=mi-proyecto"
```

### Configuración

```bash
# Usar calculador interno (por defecto)
TAIGA_METRICS_PROVIDER=internal

# TTL del caché de métricas (minutos)
TAIGA_METRICS_SNAPSHOT_TTL=60

# Para usar Learning Dashboard externo
TAIGA_METRICS_PROVIDER=external
LD_TAIGA_BACKEND_URL=https://ld-backend.example.com
```

---

## Docker

### Usando Docker Compose (Recomendado)

Ver el repositorio `taiga-docker` para instrucciones completas.

### Dockerfile Standalone

```bash
# Construir imagen
docker build -t taiga-back -f docker/Dockerfile .

# Ejecutar
docker run -d \
  -e POSTGRES_HOST=db \
  -e POSTGRES_USER=taiga \
  -e POSTGRES_PASSWORD=secret \
  -e TAIGA_SECRET_KEY=your-secret-key \
  -e TAIGA_SITES_DOMAIN=localhost:9000 \
  -p 8000:8000 \
  taiga-back
```

---

## Tests

### Ejecutar Tests

```bash
# Todos los tests
pytest

# Con cobertura
pytest --cov=taiga --cov-report=html

# Tests específicos
pytest tests/unit/projects/test_metrics.py -v

# Tests de integración
pytest tests/integration/ -v
```

### Configuración de Tests

El archivo `pytest.ini` contiene la configuración de pytest.

---

## API Documentation

- **API Reference**: https://docs.taiga.io/api.html
- **Taiga Documentation**: https://docs.taiga.io/

### Endpoints Principales

| Endpoint | Descripción |
|----------|-------------|
| `/api/v1/auth` | Autenticación |
| `/api/v1/users` | Gestión de usuarios |
| `/api/v1/projects` | Proyectos |
| `/api/v1/userstories` | User Stories |
| `/api/v1/tasks` | Tareas |
| `/api/v1/milestones` | Sprints |
| `/api/v1/metrics` | Métricas (NUEVO) |

---

## Estructura del Proyecto

```
taiga-back/
├── docker/                 # Archivos Docker
│   ├── Dockerfile
│   ├── config.py          # Config para Docker
│   └── entrypoint.sh
├── settings/              # Configuración Django
│   ├── common.py          # Settings comunes
│   ├── config.py          # Tu configuración local
│   ├── config.py.dev.example
│   └── config.py.prod.example
├── taiga/                 # Código fuente principal
│   ├── auth/              # Autenticación (incluye Google SSO)
│   ├── projects/          # Proyectos y métricas
│   │   └── metrics/       # Sistema de métricas (NUEVO)
│   └── ...
├── tests/                 # Tests
├── requirements.txt       # Dependencias principales
├── requirements-contribs.txt  # Contrib plugins
└── manage.py
```

---

## Troubleshooting

### Error: "Google token validation failed"

- Verifica que el `CLIENT_ID` sea correcto en backend y frontend
- Asegúrate de que el dominio del usuario esté en `ALLOWED_DOMAINS`

### Error: "CORS policy blocked"

Añade el origen a `CORS_ORIGIN_WHITELIST` en `settings/common.py` o configura:

```python
CORS_ORIGIN_WHITELIST = [
    "http://localhost:9000",
    "https://tu-dominio.com",
]
```

### Error: "Metrics endpoint returns 404"

Verifica que `taiga.projects.metrics` esté en `INSTALLED_APPS`.

### Database connection error

```bash
# Verificar que PostgreSQL esté corriendo
pg_isready -h localhost -p 5432

# Verificar credenciales
psql -h localhost -U taiga -d taiga
```

---

## Community

If you **need help to setup Taiga**, want to **talk about some cool enhancement** or you have **some questions**, please go to [Taiga community](https://community.taiga.io/).

## Contribute to Taiga

There are many different ways to contribute to Taiga's platform, from patches, to documentation and UI enhancements, just find the one that best fits with your skills. Check out our detailed [contribution guide](https://community.taiga.io/t/how-can-i-contribute/159)

## Code of Conduct

Help us keep the Taiga Community open and inclusive. Please read and follow our [Code of Conduct](https://github.com/taigaio/code-of-conduct/blob/main/CODE_OF_CONDUCT.md).

## License

Every code patch accepted in Taiga codebase is licensed under [MPL 2.0](LICENSE). You must be careful to not include any code that can not be licensed under this license.

Please read carefully [our license](LICENSE) and ask us if you have any questions as well as the [Contribution policy](https://github.com/taigaio/taiga-back/blob/main/CONTRIBUTING.md).

---

*Modificado por Pol Alcoverro* ❤️
