#!/bin/bash
# ============================================================================
# Entrypoint Script - MCP Hub
# ============================================================================
# Autor: Equipo Ainsophic
# Enfoque: Validación previa y ejecución segura
#
# CONCEPTO FEYNMAN - Script de Entrada:
# -------------------------------------
# Imagina que estás entrando a un parque de diversiones. Antes de
# que puedas montar las atracciones (ejecutar la aplicación),
# el guardia de seguridad verifica:
# 1. Que tengas entrada (archivo de configuración existe)
# 2. Que la entrada sea válida (JSON es correcto)
# 3. Que el área esté limpia y lista (directorios creados)
#
# Este script hace exactamente eso para el contenedor Docker:
# - Valida configuración
# - Prepara entorno
# - Inicia la aplicación de forma segura
# ============================================================================

# Configurar bash para terminar en cualquier error
# ----------------------------------------------------------------------
# set -e: Terminar si algún comando falla
# set -u: Terminar si una variable no está definida
# set -o pipefail: Terminar si algún comando en un pipe falla
#
# ¿POR QUÉ ESTO ES IMPORTANTE?
# =============================
# Sin estas opciones, si un comando falla, el script podría continuar
# y ejecutar la aplicación con configuración incompleta o inválida,
# causando errores difíciles de debuggear.
# ----------------------------------------------------------------------
set -euo pipefail

echo "============================================================"
echo "MCP Hub - Inicializando Entrypoint"
echo "============================================================"

# ----------------------------------------------------------------------------
# FUNCIÓN: Mostrar mensaje con timestamp
# ----------------------------------------------------------------------------
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# ----------------------------------------------------------------------------
# FUNCIÓN: Mostrar error y salir
# ----------------------------------------------------------------------------
error_exit() {
    log "ERROR: $1"
    log "Iniciando shutdown..."
    exit 1
}

# ----------------------------------------------------------------------------
# VALIDACIÓN 1: Verificar que el archivo de configuración existe
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------
# ¿POR QUÉ ES NECESARIO?
# ========================
# La aplicación NO puede ejecutarse sin un archivo de configuración
# válido. Si falta, fallará con un críptico error de "file not found".
#
# Es mejor detectar esto en el entrypoint y mostrar un error claro
# antes de iniciar la aplicación.
# ----------------------------------------------------------------------
CONFIG_FILE="${MCP_HUB_CONFIG:-/app/config/servers.json}"

log "Validando archivo de configuración: $CONFIG_FILE"

if [ ! -f "$CONFIG_FILE" ]; then
    error_exit "Archivo de configuración no encontrado: $CONFIG_FILE"
fi

log "✓ Archivo de configuración encontrado"

# ----------------------------------------------------------------------------
# VALIDACIÓN 2: Validar que el archivo JSON sea sintácticamente correcto
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------
# ¿POR QUÉ VALIDAR ANTES?
# ========================
# Si el JSON tiene errores de sintaxis (ej: comas faltantes, llaves
# no cerradas), la aplicación fallará al iniciarse.
#
# Es mejor detectar esto aquí y mostrar un error claro que indique
# exactamente dónde está el problema, en lugar de un traceback
# complicado de Python.
# ----------------------------------------------------------------------
log "Validando sintaxis JSON"

if ! python -c "import json; json.load(open('$CONFIG_FILE'))" 2>/dev/null; then
    error_exit "Archivo de configuración JSON inválido. Ejecuta: python -m json.tool $CONFIG_FILE para ver el error."
fi

log "✓ Sintaxis JSON válida"

# ----------------------------------------------------------------------------
# PREPARACIÓN 1: Crear directorios necesarios
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------
# ¿POR QUÉ CREAR DIRECTORIOS AQUÍ?
# ===================================
# - /app/data: Para bases de datos SQLite u otros datos persistentes
# - /app/logs: Para archivos de log de la aplicación
#
# Estos directorios deben existir y tener los permisos correctos
# antes de iniciar la aplicación.
#
# ¿POR QUÉ NO CREARLOS EN EL DOCKERFILE?
# =========================================
# Podríamos crearse en el Dockerfile, pero si montamos volúmenes,
# los directorios creados en el Dockerfile podrían ser reemplazados.
# Es más seguro crearlos aquí, después de que los volúmenes
# sean montados pero antes de iniciar la aplicación.
# ----------------------------------------------------------------------
log "Preparando directorios necesarios"

mkdir -p /app/data /app/logs

# Asegurar que el usuario mcpuser tiene permisos de escritura
# ----------------------------------------------------------------------
# El usuario mcpuser es el usuario no-root que ejecuta la aplicación.
# Si los directorios no tienen permisos correctos, la aplicación
# fallará al intentar escribir logs o datos.
# ----------------------------------------------------------------------
if [ "$(id -u)" = "0" ]; then
    # Si estamos ejecutando como root (solo en entrada), arreglar permisos
    chown -R mcpuser:mcpuser /app/data /app/logs
fi

log "✓ Directorios preparados"

# ----------------------------------------------------------------------------
# PREPARACIÓN 2: Mostrar información de configuración
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------
# ¿POR QUÉ MOSTRAR ESTO?
# ======================
# Para debugging y verificación rápida. Al iniciar el contenedor,
# podemos ver instantáneamente qué configuración está usando.
# ----------------------------------------------------------------------
log "Información de configuración:"
log "  - Archivo de configuración: $CONFIG_FILE"
log "  - Directorio de plugins: ${MCP_HUB_PLUGINS_DIR:-/app/plugins}"
log "  - Nivel de logging: ${LOG_LEVEL:-INFO}"
log "  - Usuario: $(whoami) (UID: $(id -u))"

# ----------------------------------------------------------------------------
# VALIDACIÓN 3: Verificar que Python esté disponible
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------
# Debería estar disponible porque estamos en un contenedor Python,
# pero es una buena práctica verificarlo para detectar problemas
# en la imagen.
# ----------------------------------------------------------------------
if ! command -v python &> /dev/null; then
    error_exit "Python no encontrado en PATH"
fi

log "✓ Python disponible: $(python --version)"

# ----------------------------------------------------------------------------
# PREPARACIÓN 3: Establecer permisos de ejecución en scripts (si existen)
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------
# Esto asegura que cualquier script en el directorio docker/
# tenga permisos de ejecución.
# ----------------------------------------------------------------------
if [ -d "/app/docker" ]; then
    find /app/docker -type f -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true
fi

# ----------------------------------------------------------------------------
# EJECUCIÓN: Iniciar la aplicación MCP Hub
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------
# Usamos "exec" por una razón CRÍTICA:
#
# ¿QUÉ HACE EXEC?
# ================
# exec reemplaza el proceso actual del script con el proceso de la
# aplicación.
#
# ¿POR QUÉ ES IMPORTANTE?
# =======================
# SIN exec:
# - El proceso padre es bash (el script)
# - La aplicación es un proceso hijo de bash
# - Cuando enviamos SIGTERM al contenedor para detenerlo, bash
#   recibe la señal pero NO la pasa a la aplicación
# - La aplicación NO se detiene correctamente
# - Docker debe matar forzosamente el contenedor después de un timeout
#
# CON exec:
# - La aplicación REEMPLAZA al script bash
# - La aplicación es el proceso principal (PID 1)
# - Cuando enviamos SIGTERM al contenedor, la aplicación la recibe
# - La aplicación puede cerrar graciosamente
# - No hay procesos zombies ni leaks de recursos
#
# "$@" permite pasar argumentos adicionales al comando.
# Esto es útil para debugging o sobrescribir el comando.
# ----------------------------------------------------------------------
log "Iniciando MCP Hub..."
echo "============================================================"

# Establecer variables de entorno por defecto si no están definidas
export MCP_HUB_CONFIG="${MCP_HUB_CONFIG:-/app/config/servers.json}"
export MCP_HUB_PLUGINS_DIR="${MCP_HUB_PLUGINS_DIR:-/app/plugins}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

# Ejecutar la aplicación
exec python -m mcp_hub.main --config "$MCP_HUB_CONFIG" "$@"
