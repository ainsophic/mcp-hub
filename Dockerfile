# ============================================================================
# Dockerfile de Producción - MCP Hub
# ============================================================================
# Autor: Equipo Ainsophic
# Enfoque: Optimización multi-stage para producción
#
# CONCEPTO FEYNMAN - Multi-Stage Build:
# ---------------------------------------
# Imagina que estás construyendo una computadora. Primero ensamblas
# todas las piezas (compilación, construcción, herramientas). Pero
# cuando terminas, NO necesitas las herramientas de montaje en la
# computadora final.
#
# El multi-stage build hace exactamente esto:
# - Stage 1 (builder): Tiene todas las herramientas para construir
# - Stage 2 (producción): Solo tiene lo necesario para ejecutar
#
# RESULTADO: Imagen más pequeña, más segura, más rápida de desplegar.
# ============================================================================

# ============================================================================
# STAGE 1: BUILDER
# ============================================================================
# Este stage tiene todas las herramientas necesarias para construir
# la aplicación, pero NO se usará en producción.

FROM python:3.11-slim as builder

# Variables de entorno para optimizar pip
# ----------------------------------------------------------------------
# PYTHONUNBUFFERED=1: Salida inmediata (sin buffer) para ver logs en tiempo real
# PYTHONDONTWRITEBYTECODE=1: No crear archivos .pyc (optimiza inicio)
# PIP_NO_CACHE_DIR=1: No cachear descargas (reduce tamaño de imagen)
# ----------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Directorio de trabajo del stage de construcción
WORKDIR /build

# Instalar dependencias de sistema necesarias para compilar paquetes Python
# ----------------------------------------------------------------------
# GCC y G++ son compiladores necesarios para compilar extensiones C
# de algunos paquetes Python (como numpy, bcrypt, etc.)
# Después de usarlos, se eliminarán para reducir el tamaño
# ----------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copiar archivos de dependencias
# ----------------------------------------------------------------------
# Copiamos requirements.txt antes que el código fuente porque:
# 1. Cambian con menos frecuencia que el código
# 2. Docker puede cachear esta capa
# 3. Acelera reconstrucciones cuando solo cambia el código
# ----------------------------------------------------------------------
COPY requirements.txt .
COPY requirements-dev.txt .

# Actualizar pip e instalar dependencias Python
# ----------------------------------------------------------------------
# --upgrade pip: Usar la versión más reciente de pip (mejor seguridad)
# -r requirements.txt: Instalar todas las dependencias de producción
# ----------------------------------------------------------------------
RUN pip install --upgrade pip && \
    pip install -r requirements.txt


# ============================================================================
# STAGE 2: PRODUCCIÓN
# ============================================================================
# Este stage contiene SOLO lo necesario para ejecutar la aplicación.
# Es mucho más pequeño y seguro porque no tiene herramientas de construcción.

FROM python:3.11-slim

# Variables de entorno para ejecución
# ----------------------------------------------------------------------
# PATH: Añadir directorio local de usuario al PATH para ejecutar comandos
# ----------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/home/mcpuser/.local/bin:${PATH}"

# Crear usuario no-root por seguridad
# ----------------------------------------------------------------------
# ¿POR QUÉ USUARIO NO-ROOT?
# ================================
# Si el contenedor es comprometido y corre como root:
# - El atacante tiene acceso total al sistema
# - Puede modificar cualquier archivo
# - Puede instalar software malicioso
#
# Si corre como usuario no-root:
# - El atacante solo puede acceder a archivos del usuario
# - No puede modificar archivos del sistema
# - Ataca mucho más difícil y menos dañino
#
# Usuario: mcpuser con UID 1000 (común en sistemas Linux)
# ----------------------------------------------------------------------
RUN useradd -m -u 1000 mcpuser && \
    mkdir -p /app/config /app/data /app/logs && \
    chown -R mcpuser:mcpuser /app

# Directorio de trabajo de la aplicación
WORKDIR /app

# Copiar dependencias instaladas desde el stage builder
# ----------------------------------------------------------------------
# Copiamos solo las librerías Python instaladas, no todo el sistema
# ----------------------------------------------------------------------
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copiar código fuente de la aplicación
# ----------------------------------------------------------------------
# --chown=mcpuser:mcpuser: Asegurar que el usuario mcpuser es propietario
# ----------------------------------------------------------------------
COPY --chown=mcpuser:mcpuser src/ ./src/
COPY --chown=mcpuser:mcpuser config/ ./config/

# Cambiar a usuario no-root para ejecutar la aplicación
USER mcpuser

# Exponer puertos que usa la aplicación
# ----------------------------------------------------------------------
# 8080: API REST (FastAPI) - Para llamadas HTTP
# 8000: Protocolo MCP (si se expone directamente) - Para clientes MCP
# 8081: Gateway WebSocket - Para MCP Apps en tiempo real
# ----------------------------------------------------------------------
EXPOSE 8080 8000 8081

# Health Check integrado
# ----------------------------------------------------------------------
# ¿QUÉ ES UN HEALTH CHECK?
# =======================
# Es un mecanismo para verificar que la aplicación está funcionando.
# Docker ejecuta periódicamente este comando.
#
# ¿POR QUÉ ES IMPORTANTE?
# =====================
# - Si falla, Docker puede reiniciar automáticamente el contenedor
# - Los orquestadores (Kubernetes, Swarm) pueden redirigir tráfico
# - Los load balancers pueden enviar tráfico solo a contenedores saludables
#
# CONFIGURACIÓN:
# - interval=30s: Verificar cada 30 segundos
# - timeout=10s: Esperar máximo 10 segundos por verificación
# - start-period=5s: Esperar 5s antes de empezar las verificaciones
# - retries=3: Si falla 3 veces seguidas, marcar como unhealthy
#
# COMANDO:
# Usa urllib.request (biblioteca estándar Python) para hacer una petición
# HTTP GET a /health y verifica que responda exitosamente.
# ----------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Comando de entrada del contenedor
# ----------------------------------------------------------------------
# CMD: Comando que se ejecuta al iniciar el contenedor
# --config /app/config/servers.json: Ruta al archivo de configuración
#
# ¿POR QUÉ NO USAR ENTRYPOINT?
# =============================
# ENTRYPOINT se usa cuando quieres que el contenedor ejecute siempre
# el mismo comando, y los argumentos pueden ser agregados.
#
# CMD es más flexible porque puedes sobrescribirlo completamente con
# docker run. Para este caso, CMD es suficiente y más simple.
# ----------------------------------------------------------------------
CMD ["python", "-m", "mcp_hub.main", "--config", "/app/config/servers.json"]
