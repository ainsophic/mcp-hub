# MCP Hub

> Orquestador Multitenant para Servidores MCP y MCP Apps

**MCP Hub** es una plataforma centralizada diseñada para orquestar y gestionar múltiples servidores MCP (Model Context Protocol) y MCP Apps, proporcionando una capa de gestión superior similar a cómo Docker Swarm maneja contenedores, pero específicamente diseñado para el ecosistema MCP.

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-orange.svg)](https://github.com/ainsophic/mcp-hub)

## 🎯 Características Principales

### Orquestación de Servidores MCP
- **Gestión de Ciclo de Vida**: Inicia, detiene y monitorea múltiples servidores MCP
- **Transporte Stdio**: Soporte completo para comunicación vía stdio
- **Auto-descubrimiento**: Descubre automáticamente las herramientas y recursos de los servidores conectados
- **Reconexión Automática**: Manejo robusto de reconexiones con backoff exponencial

### Sistema Multitenant
- **Aislamiento Completo**: Cada tenant tiene su propio namespace y configuración
- **Gestión de Cuotas**: Límites configurables por tenant (servidores, herramientas, etc.)
- **Segregación de Recursos**: Aislamiento total entre diferentes organizaciones/proyectos
- **Gestión de Credenciales**: Variables de entorno por tenant para conexiones

### Enrutamiento Dinámico
- **Prefijos Namespaced**: Herramientas con prefijos `server.tool` (ej: `postgres.query`, `github.create_issue`)
- **Catálogo Centralizado**: Registro unificado de todas las herramientas disponibles
- **Proxy Transparente**: Los agentes de IA ven un "super-servidor" con todas las capacidades

### Gateway para MCP Apps
- **WebSocket Bidireccional**: Comunicación en tiempo real entre Apps y servidores MCP
- **Proxy de Recursos Estáticos**: Serve HTML/JS/CSS de las MCP Apps
- **Inyección de Configuración**: Configuración automática inyectada en las Apps
- **Múltiples Conexiones**: Soporte para múltiples Apps concurrentes

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                     Agentes de IA                            │
│              (Claude Desktop, Cursor, etc.)                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                      MCP Hub                                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  FastAPI + FastMCP (API REST + Protocolo MCP)        │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Core - Orchestration                               │  │
│  │  ├─ Registry (Configuración)                       │  │
│  │  ├─ Orchestrator (Ciclo de vida)                   │  │
│  │  ├─ Router (Enrutamiento)                          │  │
│  │  └─ MultitenantManager (Aislamiento)               │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Transport Layer                                   │  │
│  │  └─ StdioClientWrapper (Cliente MCP)               │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Gateway Layer                                     │  │
│  │  ├─ WebSocket Gateway (Apps)                       │  │
│  │  └─ UI Proxy (Recursos estáticos)                  │  │
│  └─────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│  Postgres│  │  GitHub  │  │  Custom  │
│   MCP    │  │   MCP    │  │   MCP    │
└──────────┘  └──────────┘  └──────────┘
```

## 📦 Instalación

### Requisitos Previos
- Python 3.11 o superior
- pip (gestor de paquetes de Python)

### Instalación desde Fuente

```bash
# Clonar el repositorio
git clone https://github.com/ainsophic/mcp-hub.git
cd mcp-hub

# Crear entorno virtual (opcional pero recomendado)
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Instalar dependencias de desarrollo (opcional)
pip install -r requirements-dev.txt

# Instalar el paquete en modo desarrollo
pip install -e .
```

## 🚀 Uso Rápido

### 1. Configurar Servidores MCP

Crea un archivo `config/servers.json` con la configuración de tus servidores:

```json
{
  "version": "1.0.0",
  "tenants": {
    "default": {
      "description": "Tenant por defecto",
      "servers": {
        "sqlite-demo": {
          "name": "sqlite-demo",
          "type": "database",
          "command": "python",
          "args": ["-m", "mcp.server.sqlite", "--db-path", "./data/demo.db"],
          "enabled": true,
          "capabilities": ["tools", "resources"],
          "transport": "stdio",
          "metadata": {
            "description": "Servidor SQLite de ejemplo"
          }
        }
      }
    }
  },
  "gateway": {
    "port": 8080,
    "mcp_port": 8000,
    "websocket_port": 8081,
    "host": "0.0.0.0"
  },
  "orchestrator": {
    "auto_start": false,
    "max_retries": 3,
    "startup_timeout": 30
  }
}
```

### 2. Iniciar el Hub

```bash
# Iniciar con configuración por defecto
python -m mcp_hub.main

# O especificar configuración personalizada
python -m mcp_hub.main --config config/servers.json

# Con recarga automática (desarrollo)
python -m mcp_hub.main --reload
```

### 3. Verificar Estado

```bash
# Salud del Hub
curl http://localhost:8080/health

# Listar tenants
curl http://localhost:8080/api/tenants

# Listar herramientas disponibles
curl http://localhost:8080/api/tools
```

### 4. Iniciar Servidores de un Tenant

```bash
# Iniciar todos los servidores del tenant "default"
curl -X POST http://localhost:8080/api/tenants/default/start

# Listar servidores activos
curl http://localhost:8080/api/servers
```

### 5. Llamar a una Herramienta

```bash
# Ejecutar una herramienta
curl -X POST http://localhost:8080/api/tools/sqlite-demo.query \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM users LIMIT 10"}'
```

## 🔧 Configuración

### Estructura de Archivos

```
mcp-hub/
├── config/
│   └── servers.json          # Configuración de servidores y tenants
├── plugins/
│   └── examples/             # Ejemplos de plugins y MCP Apps
├── src/
│   └── mcp_hub/
│       ├── core/             # Componentes core del Hub
│       ├── transport/        # Capa de transporte (stdio, etc.)
│       ├── gateway/          # Gateway para MCP Apps
│       └── main.py           # Aplicación principal
├── tests/                    # Tests unitarios y de integración
├── pyproject.toml           # Configuración del proyecto Python
├── requirements.txt          # Dependencias de producción
└── README.md                 # Este archivo
```

### Configuración de Servidores

Cada servidor MCP se configura con los siguientes campos:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `name` | string | Nombre único del servidor |
| `type` | string | Tipo de servidor (database, api, file, etc.) |
| `command` | string | Comando para iniciar el servidor |
| `args` | array | Argumentos del comando |
| `enabled` | boolean | Indica si el servidor está habilitado |
| `capabilities` | array | Capacidades (tools, resources, prompts) |
| `transport` | string | Tipo de transporte (stdio, http, sse) |
| `metadata` | object | Metadatos adicionales |

### Configuración de Gateway

```json
{
  "gateway": {
    "port": 8080,              // Puerto API REST
    "mcp_port": 8000,          // Puerto protocolo MCP
    "websocket_port": 8081,    // Puerto Gateway WebSocket
    "host": "0.0.0.0"          // Host donde escuchar
  }
}
```

## 📡 API REST

### Endpoints de Salud

- `GET /` - Información del Hub
- `GET /health` - Estado de componentes

### Gestión de Tenants

- `GET /api/tenants` - Listar todos los tenants
- `GET /api/tenants/{tenant_id}` - Obtener información de un tenant
- `GET /api/tenants/{tenant_id}/tools` - Listar herramientas de un tenant
- `POST /api/tenants/{tenant_id}/start` - Iniciar servidores del tenant
- `POST /api/tenants/{tenant_id}/stop` - Detener servidores del tenant

### Gestión de Servidores

- `GET /api/servers` - Listar todos los servidores
- `GET /api/servers/{tenant_id}/{server_name}` - Obtener estado de un servidor
- `POST /api/servers/{tenant_id}/{server_name}/start` - Iniciar servidor específico
- `POST /api/servers/{tenant_id}/{server_name}/stop` - Detener servidor específico

### Herramientas

- `GET /api/tools` - Listar todas las herramientas disponibles
- `POST /api/tools/{tool_name}/call` - Ejecutar una herramienta

### Gateway WebSocket

- `WS /ws/app/{app_id}/{tenant_id}` - Conexión WebSocket para MCP Apps

### Gateway UI

- `GET /api/apps` - Listar todas las MCP Apps disponibles
- `GET /api/apps/{app_id}` - Obtener información de una App
- `GET /apps/{app_id}` - Servir index.html de una App
- `GET /apps/{app_id}/{resource_path:path}` - Servir recursos estáticos de una App

## 🐳 Docker

El MCP Hub incluye soporte completo para Docker, permitiendo despliegue fácil y consistente en cualquier entorno.

### Instalación con Docker

```bash
# Clonar el repositorio
git clone https://github.com/ainsophic/mcp-hub.git
cd mcp-hub

# Construir imagen
docker build -t mcp-hub:0.1.0 .

# O construir con Docker Compose
docker-compose build
```

### Docker Compose

#### Entorno de Desarrollo

```bash
# Iniciar servicio de desarrollo con hot-reload
docker-compose -f docker-compose.dev.yml up

# Con PostgreSQL
docker-compose -f docker-compose.dev.yml --profile postgres up

# En modo detached
docker-compose -f docker-compose.dev.yml up -d

# Ver logs
docker-compose -f docker-compose.dev.yml logs -f
```

#### Entorno de Producción

```bash
# Iniciar servicio de producción
docker-compose -f docker-compose.prod.yml up -d

# Con todos los servicios dependientes
docker-compose -f docker-compose.prod.yml --profile postgres --profile redis up -d

# Ver logs
docker-compose -f docker-compose.prod.yml logs -f

# Detener servicios
docker-compose -f docker-compose.prod.yml down
```

### Comandos Útiles de Docker Compose

```bash
# Detener servicios
docker-compose down

# Detener con volúmenes
docker-compose down -v

# Reconstruir imagen
docker-compose build --no-cache

# Ejecutar tests en Docker
docker-compose run --rm mcp-hub pytest

# Acceder al contenedor
docker-compose exec mcp-hub bash

# Ver logs
docker-compose logs -f mcp-hub

# Verificar estado
docker-compose ps
```

### Variables de Entorno

Las siguientes variables de entorno pueden configurarse en `docker-compose.yml` o un archivo `.env`:

| Variable | Descripción | Por Defecto |
|----------|-------------|-------------|
| `MCP_HUB_CONFIG` | Ruta al archivo de configuración JSON | `/app/config/servers.json` |
| `MCP_HUB_PLUGINS_DIR` | Directorio de plugins MCP | `/app/plugins` |
| `LOG_LEVEL` | Nivel de logging | `INFO` |
| `POSTGRES_USER` | Usuario de PostgreSQL | `mcpuser` |
| `POSTGRES_PASSWORD` | Contraseña de PostgreSQL | `mcppassword` |
| `POSTGRES_DB` | Base de datos PostgreSQL | `mcpdb` |

### Volúmenes

- `mcp-hub-data`: Datos persistentes del Hub
- `mcp-hub-logs`: Logs de la aplicación
- `postgres-data`: Datos de PostgreSQL (si está habilitado)
- `redis-data`: Datos de Redis (si está habilitado)

### Redes

Los servicios se conectan a través de la red `mcp-hub-network`, lo que permite comunicación segura entre contenedores.

### Health Checks

El contenedor MCP Hub incluye health checks automáticos que verifican:
- API REST respondiendo en puerto 8080
- Estado de los componentes internos

Puedes ver el estado de health:
```bash
docker inspect mcp-hub | jq '.[0].State.Health'
```

### Makefile

Usa el Makefile para comandos más simples:

```bash
# Ver todos los comandos disponibles
make help

# Iniciar desarrollo
make up-dev

# Iniciar desarrollo con PostgreSQL
make up-dev-with-db

# Ver logs
make logs-dev

# Detener servicios
make down-dev

# Reconstruir todo
make rebuild-dev
```

### Documentación Completa de Docker

Para documentación detallada sobre Docker, ver [docker/README.md](docker/README.md).

## 🔌 Integración con Claude Desktop

Para integrar MCP Hub con Claude Desktop, agrega lo siguiente a tu configuración de Claude Desktop:

```json
{
  "mcpServers": {
    "mcp-hub": {
      "command": "python",
      "args": [
        "-m",
        "mcp_hub.main",
        "--config",
        "/ruta/a/config/servers.json"
      ]
    }
  }
}
```

Ahora Claude Desktop verá MCP Hub como un servidor MCP más, con todas las herramientas de tus servidores gestionados expuestas con prefijos (ej: `postgres.query`, `github.create_issue`).

## 🧪 Tests

El proyecto incluye tests unitarios y de integración para garantizar la calidad del código:

```bash
# Ejecutar todos los tests
pytest

# Ejecutar tests con cobertura
pytest --cov=mcp_hub --cov-report=html

# Ejecutar tests específicos
pytest tests/test_registry.py
pytest tests/test_multitenant.py
pytest tests/test_integration.py

# Ejecutar tests con verbosidad
pytest -v
```

## 📚 Ejemplos de Uso

### Ejemplo 1: Iniciar Servidores MCP

```python
import asyncio
from mcp_hub.main import app, _multitenant_manager

async def main():
    # Iniciar servidores del tenant "default"
    servers = await _multitenant_manager.start_tenant_servers("default")
    print(f"Servidores iniciados: {len(servers)}")

asyncio.run(main())
```

### Ejemplo 2: Llamar a una Herramienta

```python
import asyncio
from mcp_hub.main import _router

async def main():
    # Ejecutar una herramienta
    result = await _router.call_tool(
        "postgres.query",
        {"sql": "SELECT * FROM users LIMIT 10"}
    )
    print(f"Resultado: {result}")

asyncio.run(main())
```

### Ejemplo 3: Conexión WebSocket desde MCP App

```javascript
// Ejemplo de conexión WebSocket desde una MCP App
const ws = new WebSocket('ws://localhost:8081/ws/app/myapp/default');

ws.onopen = () => {
    console.log('Conectado al MCP Hub');
    
    // Enviar mensaje de ready
    ws.send(JSON.stringify({
        type: 'app_ready',
        data: {}
    }));
};

ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    
    switch (message.type) {
        case 'app_state':
            console.log('Estado de la App:', message.data);
            break;
        case 'tool_result':
            console.log('Resultado de herramienta:', message.data);
            break;
    }
};

// Llamar a una herramienta
function callTool(toolName, arguments) {
    ws.send(JSON.stringify({
        type: 'tool_call',
        data: {
            tool_name: toolName,
            arguments: arguments
        }
    }));
}
```

## 🛠️ Desarrollo

### Configuración para Desarrollo

```bash
# Instalar dependencias de desarrollo
pip install -r requirements-dev.txt

# Instalar pre-commit hooks
pre-commit install

# Ejecutar linters
ruff check src/mcp_hub/
black src/mcp_hub/

# Ejecutar type checking
mypy src/mcp_hub/
```

### Estructura del Código

El proyecto sigue principios de Clean Architecture y SOLID:

- **Core**: Lógica de negocio y orquestación
- **Transport**: Abstracción de transporte MCP
- **Gateway**: Integración con MCP Apps
- **Main**: Punto de entrada y API REST

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Por favor sigue estos pasos:

1. Fork el repositorio
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

### Código de Conducta

Al participar en este proyecto, te comprometes a respetar nuestro código de conducta.

## 📄 Licencia

Este proyecto está licenciado bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para detalles.

## 🙏 Agradecimientos

- **Model Context Protocol (MCP)** - Protocolo base para la comunicación
- **Anthropic** - Creadores de Claude y MCP
- **FastAPI** - Framework web moderno para Python
- **Python Community** - Ecosistema de herramientas y librerías

## 📞 Contacto

- **Proyecto**: https://github.com/ainsophic/mcp-hub
- **Issues**: https://github.com/ainsophic/mcp-hub/issues
- **Discusiones**: https://github.com/ainsophic/mcp-hub/discussions

## 🗺️ Roadmap

### Versión 0.2.0 (Próximo)
- [ ] Integración con Docker (despliegue de servidores en contenedores)
- [ ] Soporte para transporte HTTP y SSE
- [ ] Panel de administración web
- [ ] Métricas y monitoreo con Prometheus

### Versión 0.3.0
- [ ] Sistema de plugins y marketplace
- [ ] Soporte para escalamiento horizontal
- [ ] Balanceo de carga entre múltiples instancias del Hub
- [ ] Backup y restauración de configuraciones

### Versión 1.0.0
- [ ] Estabilidad y producción-ready
- [ ] Documentación completa y tutoriales
- [ ] Extensas pruebas de integración
- [ ] Compatibilidad con todos los servidores MCP estándar

---

**Construido con ❤️ por Ainsophic Team**

*Ainsophic Foundation*
