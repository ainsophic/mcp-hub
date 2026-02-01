# Docker para MCP Hub

Este directorio contiene scripts y archivos de configuración específicos para Docker.

## 📚 Documentación

### Archivos

- **`entrypoint.sh`**: Script de entrada para el contenedor de producción
- **`healthcheck.sh`**: Script de verificación de salud del contenedor

## 🔧 Scripts

### Entrypoint Script (`entrypoint.sh`)

El script de entrada se ejecuta automáticamente cuando el contenedor se inicia.

#### Funcionalidades

1. **Validación de Configuración**
   - Verifica que el archivo de configuración existe
   - Valida que el JSON sea sintácticamente correcto
   - Proporciona mensajes de error claros si hay problemas

2. **Preparación de Entorno**
   - Crea directorios necesarios (`/app/data`, `/app/logs`)
   - Asegura permisos correctos para el usuario `mcpuser`
   - Valida que Python esté disponible

3. **Ejecución Segura**
   - Usa `exec` para reemplazar el proceso del script
   - Asegura que las señales (SIGTERM, SIGINT) llegan al proceso principal
   - Permite un shutdown graciosos del contenedor

#### ¿Por Qué Usar un Entrypoint Script?

**Sin Entrypoint:**
```bash
# Dockerfile
CMD ["python", "-m", "mcp_hub.main"]
```

Si el archivo de configuración no existe o es inválido:
- Python fallará con traceback críptico
- El contenedor se marcará como unhealthy
- Difícil de debuggear

**Con Entrypoint:**
```bash
# Entrypoint valida antes
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Archivo no encontrado"
    exit 1
fi
```

Si el archivo no existe:
- Entrypoint muestra error claro y específico
- El contenedor termina inmediatamente con código de error
- Fácil identificar el problema

### Health Check Script (`healthcheck.sh`)

El script de health check verifica periódicamente que el servicio esté funcionando correctamente.

#### Funcionalidades

1. **Verificación de API REST**
   - Hace una petición HTTP GET a `/health`
   - Verifica que responda con éxito (HTTP 200)
   - Implementa reintentos con backoff

2. **Validación de Respuesta**
   - Verifica que la respuesta sea JSON válido
   - Valida la estructura de la respuesta
   - Verifica que el status sea `"healthy"`

3. **Verificación de Componentes Internos**
   - Valida que cada componente (registry, orchestrator, etc.) esté activo
   - Marca como unhealthy si algún componente falla
   - Proporciona diagnóstico específico

#### ¿Por Qué Usar un Health Check?

**Sin Health Check:**
- Docker no sabe si la aplicación está funcionando
- El contenedor puede estar "corriendo" pero la app falló
- No hay auto-recuperación de fallos

**Con Health Check:**
- Docker verifica periódicamente la salud
- Si falla, Docker puede reiniciar automáticamente
- Load balancers envían tráfico solo a contenedores healthy
- Monitoreo y alertas basados en health status

## 🚀 Uso

### Desarrollo

Para desarrollo con hot-reload:

```bash
# Construir imagen de desarrollo
docker build -f Dockerfile.dev -t mcp-hub:dev .

# O usar Makefile
make build-dev
```

### Producción

Para producción:

```bash
# Construir imagen de producción
docker build -t mcp-hub:0.1.0 .

# O usar Makefile
make build
```

## 📝 Perfiles de Docker Compose

### Profile `postgres`

Incluye un contenedor PostgreSQL para desarrollo y producción:

```bash
# Desarrollo
docker-compose -f docker-compose.dev.yml --profile postgres up

# Producción
docker-compose -f docker-compose.prod.yml --profile postgres up -d
```

### Profile `redis`

Incluye un contenedor Redis para caché y message bus:

```bash
docker-compose --profile redis up -d
```

### Perfiles Combinados

```bash
# Todos los servicios
docker-compose --profile postgres --profile redis up -d

# Desarrollo con PostgreSQL
docker-compose -f docker-compose.dev.yml --profile postgres up

# Producción con PostgreSQL y Redis
docker-compose -f docker-compose.prod.yml --profile postgres --profile redis up -d
```

## 🔧 Construcción de Imágenes

### Imagen de Producción

```bash
docker build -t mcp-hub:0.1.0 .
```

### Imagen de Desarrollo

```bash
docker build -f Dockerfile.dev -t mcp-hub:dev .
```

### Multi-Stage Build

Las imágenes usan **multi-stage builds** para optimización:

**Stage 1 (Builder):**
- Contiene herramientas de construcción (gcc, g++)
- Instala dependencias Python
- No se usa en producción final

**Stage 2 (Producción):**
- Solo contiene Python y dependencias instaladas
- No tiene herramientas de construcción
- Mucho más pequeña y segura

**Beneficios:**
- Tamaño de imagen reducido (~50% más pequeña)
- Superficie de ataque reducida (menos herramientas)
- Build cache más eficiente (solo reconstruye lo necesario)
- Imágenes más rápidas de desplegar

## 🔒 Seguridad

### Usuario No-Root

El contenedor corre como usuario `mcpuser` (UID 1000), no como root.

**Ventajas:**
- Si el contenedor es comprometido, el atacante tiene menos privilegios
- No puede modificar archivos del sistema
- No puede instalar software malicioso a nivel de sistema
- Cumple con mejores prácticas de seguridad de contenedores

### Volúmenes Read-Only

La configuración se monta como volumen read-only:

```yaml
volumes:
  - ./config:/app/config:ro  # ro = read-only
```

**Ventajas:**
- La aplicación no puede corromper su configuración
- Protección contra bugs que escriben archivos
- Claridad: solo el host puede modificar la configuración

### Health Checks Automatizados

Docker verifica periódicamente la salud del contenedor:

```yaml
healthcheck:
  test: ["CMD", "python", "-c", "..."]
  interval: 30s
  timeout: 10s
  retries: 3
```

**Ventajas:**
- Auto-recuperación de fallos
- Notificación de problemas
- Despliegues automatizados más seguros

## 🐛 Debugging

### Ver Logs del Entrypoint

Para ver qué hace el entrypoint:

```bash
docker-compose up

# O ver logs en tiempo real
docker-compose logs -f mcp-hub
```

### Ver Logs del Health Check

Para ver resultados de health checks:

```bash
# Ver estado de health
docker inspect mcp-hub | jq '.[0].State.Health'

# Ver logs de health check
docker inspect mcp-hub | jq '.[0].State.Health.Log'
```

### Habilitar Debug Mode del Health Check

```bash
# Añadir variable HEALTHCHECK_DEBUG=1
HEALTHCHECK_DEBUG=1 docker-compose up
```

### Acceder al Contenedor

Para acceder a un contenedor corriendo:

```bash
# Entrar al contenedor
docker-compose exec mcp-hub bash

# Ejecutar comando específico
docker-compose exec mcp-hub python -c "print('Hola')"

# Ver procesos
docker-compose exec mcp-hub ps aux
```

## 📊 Métricas y Monitoreo

### Verificar Salud del Servicio

```bash
# Usar Makefile
make healthcheck

# Manual
curl http://localhost:8080/health
```

### Ver Métricas de Docker

```bash
# Ver uso de recursos
docker stats mcp-hub

# Ver información del contenedor
docker inspect mcp-hub

# Ver eventos del contenedor
docker events --filter container=mcp-hub
```

## 🔧 Troubleshooting

### Problema: El contenedor no inicia

**Solución:**
```bash
# Ver logs del contenedor
docker-compose logs mcp-hub

# Ver si el contenedor está corriendo
docker-compose ps
```

### Problema: El contenedor se marca unhealthy

**Solución:**
```bash
# Ver estado detallado de health
docker inspect mcp-hub | jq '.[0].State.Health'

# Ejecutar health check manualmente
docker-compose exec mcp-hub bash
docker/healthcheck.sh
```

### Problema: Permisos de archivos

**Solución:**
```bash
# Reconstruir imagen (el entrypoint arregla permisos)
make rebuild

# O arreglar permisos manualmente
docker-compose exec mcp-hub chown -R mcpuser:mcpuser /app
```

### Problema: No se pueden conectar servicios

**Solución:**
```bash
# Ver redes
docker network ls | grep mcp-hub

# Ver contenedores en la red
docker network inspect mcp-hub-network
```

## 📚 Referencias

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Best Practices for Dockerfiles](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)
- [Docker Health Checks](https://docs.docker.com/engine/reference/builder/#healthcheck)

---

**Documentación mantenida por:** Equipo Ainsophic  
**Última actualización:** 2025-02-01
