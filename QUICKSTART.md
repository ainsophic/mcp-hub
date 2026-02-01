# Guía de Inicio Rápido - MCP Hub

Esta guía te ayudará a comenzar a usar MCP Hub en minutos.

## 🐳 Docker (Método Recomendado)

### Iniciar con Docker Compose (Más Fácil)

```bash
# Clonar el repositorio
git clone https://github.com/ainsophic/mcp-hub.git
cd mcp-hub

# Iniciar con Docker Compose
docker-compose up -d

# Verificar estado
docker-compose ps
curl http://localhost:8080/health
```

### Desarrollar con Docker Compose

```bash
# Iniciar con hot-reload
docker-compose -f docker-compose.dev.yml up

# Con PostgreSQL
docker-compose -f docker-compose.dev.yml --profile postgres up

# Ver logs en tiempo real
docker-compose -f docker-compose.dev.yml logs -f
```

### Detener Servicios

```bash
# Detener todos los servicios
docker-compose down

# Detener y limpiar volúmenes
docker-compose down -v
```

### Comandos Útiles del Makefile

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

### Variables de Entorno para Docker

Crea un archivo `.env` basado en `.env.example`:

```bash
# Copiar ejemplo
cp .env.example .env

# Editar con tus valores
nano .env
```

Variables comunes:

```env
# MCP Hub Configuration
MCP_HUB_CONFIG=/app/config/servers.json
MCP_HUB_PLUGINS_DIR=/app/plugins
LOG_LEVEL=INFO

# PostgreSQL (opcional)
POSTGRES_USER=mcpuser
POSTGRES_PASSWORD=mcppassword
POSTGRES_DB=mcpdb
DATABASE_URL=postgresql://mcpuser:mcppassword@postgres:5432/mcpdb
```

---

## 📋 Opción: Instalación Manual (Sin Docker)

Si prefieres instalar sin Docker, sigue estos pasos:

## 📋 Requisitos Previos

- Python 3.11 o superior
- pip (gestor de paquetes de Python)
- (Opcional) Claude Desktop para probar la integración

## 🚀 Instalación

### 1. Clonar el Repositorio

```bash
git clone https://github.com/ainsophic/mcp-hub.git
cd mcp-hub
```

### 2. Crear Entorno Virtual (Opcional pero Recomendado)

```bash
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
```

### 3. Instalar Dependencias

```bash
pip install -r requirements.txt
```

## ⚙️ Configuración

El archivo de configuración `config/servers.json` ya incluye un ejemplo de servidor SQLite. Puedes usarlo directamente o modificarlo según tus necesidades.

### Configuración de Ejemplo (ya incluida):

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
          "transport": "stdio"
        }
      }
    }
  },
  "gateway": {
    "port": 8080,
    "mcp_port": 8000,
    "websocket_port": 8081,
    "host": "0.0.0.0"
  }
}
```

## 🏃 Iniciar el Hub

```bash
# Iniciar con configuración por defecto
python -m mcp_hub.main
```

Verás mensajes indicando que el Hub se está inicializando:

```
============================================================
MCP Hub - Iniciando...
============================================================
Cargando configuración desde: config/servers.json
Inicializando Orchestrator...
Inicializando Router dinámico...
Inicializando MultitenantManager...
Inicializando MCPAppGateway...
Inicializando UIProxy...
============================================================
MCP Hub - Inicialización completada exitosamente
============================================================
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080
```

## 🧪 Probar el Hub

### 1. Verificar Salud

```bash
curl http://localhost:8080/health
```

Deberías ver una respuesta JSON indicando que todos los componentes están activos:

```json
{
  "status": "healthy",
  "components": {
    "registry": true,
    "orchestrator": true,
    "router": true,
    "multitenant_manager": true,
    "gateway": true,
    "ui_proxy": true
  }
}
```

### 2. Listar Tenants

```bash
curl http://localhost:8080/api/tenants
```

### 3. Iniciar Servidores

```bash
curl -X POST http://localhost:8080/api/tenants/default/start
```

### 4. Listar Herramientas Disponibles

```bash
curl http://localhost:8080/api/tools
```

## 🔌 Integración con Claude Desktop

### 1. Abrir Configuración de Claude Desktop

En macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
En Windows: `%APPDATA%\Claude\claude_desktop_config.json`

### 2. Agregar el MCP Hub

```json
{
  "mcpServers": {
    "mcp-hub": {
      "command": "python",
      "args": [
        "-m",
        "mcp_hub.main",
        "--config",
        "/ruta/absoluta/a/config/servers.json"
      ]
    }
  }
}
```

**Importante:** Reemplaza `/ruta/absoluta/a/config/servers.json` con la ruta real al archivo de configuración en tu sistema.

### 3. Reiniciar Claude Desktop

Claude ahora detectará MCP Hub como un servidor MCP con todas las herramientas de tus servidores gestionados.

## 📝 Uso Básico

### Llamar a una Herramienta desde Claude

Una vez integrado con Claude Desktop, puedes llamar a las herramientas directamente:

```
Por favor, ejecuta una consulta en la base de datos SQLite usando la herramienta sqlite-demo.query.
```

Claude invocará la herramienta a través de MCP Hub, que la enrutará al servidor SQLite correspondiente.

### Ejemplo de Llamada HTTP Directa

```bash
curl -X POST http://localhost:8080/api/tools/sqlite-demo.query \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT name FROM sqlite_master WHERE type='table'"
  }'
```

## 🔧 Solución de Problemas

### El Hub no inicia

1. **Verificar que tienes la versión correcta de Python:**
   ```bash
   python --version  # Debe ser 3.11 o superior
   ```

2. **Verificar que las dependencias están instaladas:**
   ```bash
   pip list | grep -E "(fastapi|uvicorn|mcp)"
   ```

3. **Revisar los logs del Hub:**
   Los mensajes de error se muestran en la consola.

### Los servidores no inician

1. **Verificar que el comando del servidor es correcto:**
   Revisa el archivo `config/servers.json` y asegúrate de que el comando y los argumentos sean válidos.

2. **Verificar que las dependencias del servidor MCP estén instaladas:**
   ```bash
   # Por ejemplo, para el servidor SQLite
   pip install mcp-server-sqlite
   ```

### Claude Desktop no detecta el Hub

1. **Verifica la ruta del archivo de configuración:**
   Usa rutas absolutas, no relativas.

2. **Revisa el archivo de configuración de Claude:**
   Asegúrate de que el JSON sea válido.

3. **Reinicia Claude Desktop:**
   Los cambios en la configuración requieren un reinicio.

## 📚 Próximos Pasos

- Lee el [README.md](README.md) para documentación completa
- Explora los ejemplos en el directorio `plugins/examples/`
- Revisa los archivos de configuración en `config/`
- Mira los tests en `tests/` para ejemplos de uso

## 🆘 Ayuda

- **Issues**: https://github.com/ainsophic/mcp-hub/issues
- **Discusiones**: https://github.com/ainsophic/mcp-hub/discussions
- **Documentación**: https://github.com/ainsophic/mcp-hub

---

¡Disfruta usando MCP Hub! 🎉
