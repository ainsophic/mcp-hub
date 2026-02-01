#!/bin/bash
# ============================================================================
# Health Check Script - MCP Hub
# ============================================================================
# Autor: Equipo Ainsophic
# Enfoque: Verificación de salud del servicio
#
# CONCEPTO FEYNMAN - Health Check:
# ---------------------------------
# Imagina que eres un médico haciendo un chequeo a un paciente.
# No solo preguntas "¿estás vivo?", sino que verificas:
# - El corazón late (API REST responde)
# - Los pulmones respiran (conexiones funcionan)
# - Los reflejos funcionan (componentes activos)
#
# El health check de Docker hace esto para el contenedor:
# - Verifica que el servicio esté funcionando
# - Verifica que responda correctamente
# - Retorna estado (healthy/unhealthy)
#
# ¿POR QUÉ ES IMPORTANTE?
# =========================
# - Docker puede reiniciar automáticamente contenedores unhealthy
# - Load balancers redirigen tráfico solo a contenedores healthy
# - Monitoreo y alertas se basan en health checks
# ============================================================================

# Configurar bash para no terminar en errores (el health check debe
# reportar el estado, no fallar completamente)
set +e

# ----------------------------------------------------------------------------
# FUNCIÓN: Mostrar mensaje de debug
# ----------------------------------------------------------------------------
# Solo mostramos logs si HEALTHCHECK_DEBUG=1 para no spammar logs
# ----------------------------------------------------------------------------
log_debug() {
    if [ "${HEALTHCHECK_DEBUG:-0}" = "1" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    fi
}

# ----------------------------------------------------------------------------
# FUNCIÓN: Verificar health check de API REST
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------
# ¿QUÉ ES /health?
# =================
# Es un endpoint HTTP que el Hub expone para verificar su estado.
# Retorna un JSON con el estado de cada componente interno:
# {
#   "status": "healthy",
#   "components": {
#     "registry": true,
#     "orchestrator": true,
#     "router": true,
#     "multitenant_manager": true,
#     "gateway": true,
#     "ui_proxy": true
#   }
# }
#
# ¿POR QUÉ VERIFICAR ESTE ENDPOINT?
# ==================================
# - Es el único lugar donde sabemos si TODOS los componentes están funcionando
# - Un contenedor puede estar "corriendo" (PID existe) pero la app no responder
# - Solo verificando la API REST sabemos que la app está realmente funcionando
#
# ¿POR QUÉ USAR curl EN VEZ DE python?
# =====================================
# - curl está disponible en casi todas las imágenes base
# - Más rápido (no necesita iniciar intérprete Python)
# - Dependencia externa menor
# ----------------------------------------------------------------------
check_api_health() {
    local health_url="http://localhost:8080/health"
    local timeout=5
    local max_retries=3
    local retry_count=0
    
    log_debug "Verificando health de API: $health_url"
    
    # Intentar hacer la petición con reintentos
    while [ $retry_count -lt $max_retries ]; do
        # ----------------------------------------------------------------------
        # curl options explicadas:
        # -s: Silent (sin mostrar progreso ni errores)
        # -f: Fail silently (retorna código de error si HTTP >= 400)
        # --max-time $timeout: Abortar después de X segundos
        # ----------------------------------------------------------------------
        if curl -sf --max-time "$timeout" "$health_url" > /dev/null 2>&1; then
            log_debug "✓ API REST respondiendo correctamente"
            return0
        fi
        
        retry_count=$((retry_count + 1))
        
        if [ $retry_count -lt $max_retries ]; then
            log_debug "Intento $retry_count/$max_retries falló, reintentando en 1s..."
            sleep 1
        fi
    done
    
    log_debug "✗ API REST no respondió después de $max_retries intentos"
    return 1
}

# ----------------------------------------------------------------------------
# FUNCIÓN: Validar respuesta JSON
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------
# ¿POR QUÉ VALIDAR EL JSON?
# =========================
# Es posible que el servidor responda, pero con:
# - HTML de error 500
# - Texto plano de error
# - JSON malformado
#
# En cualquier caso, el servicio no está realmente "healthy",
# aunque haya respondido HTTP 200.
# ----------------------------------------------------------------------
validate_json_response() {
    local health_url="http://localhost:8080/health"
    
    log_debug "Validando respuesta JSON..."
    
    # ----------------------------------------------------------------------
    # Usamos python para validar el JSON porque:
    # - Está disponible (es un contenedor Python)
    # - Puede validar cualquier estructura JSON
    # - Más robusto que regex o parsers simples
    # ----------------------------------------------------------------------
    if curl -sf http://localhost:8080/health | python -c "import sys, json; json.load(sys.stdin)" 2>/dev/null; then
        log_debug "✓ Respuesta JSON válida"
        return 0
    fi
    
    log_debug "✗ Respuesta inválida o no es JSON"
    return 1
}

# ----------------------------------------------------------------------------
# FUNCIÓN: Verificar estado de componentes internos
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------
# Este es un health check MÁS PROFUNDO.
# No solo verifica que el servidor responda, sino que los componentes
# internos estén en estado correcto.
# ----------------------------------------------------------------------
check_components_status() {
    local health_url="http://localhost:8080/health"
    
    log_debug "Verificando estado de componentes..."
    
    # Obtener respuesta JSON
    local health_response
    health_response=$(curl -sf http://localhost:8080/health 2>/dev/null)
    
    if [ -z "$health_response" ]; then
        log_debug "✗ No se pudo obtener respuesta del health endpoint"
        return 1
    fi
    
    # Verificar que el status sea "healthy"
    local status
    status=$(echo "$health_response" | python -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null)
    
    if [ "$status" = "healthy" ]; then
        log_debug "✓ Estado general: healthy"
    else
        log_debug "✗ Estado general: $status (debería ser 'healthy')"
        return 1
    fi
    
    # Verificar que todos los componentes estén activos (true)
    # ----------------------------------------------------------------------
    # Iteramos sobre cada componente y verificamos que sea true
    # ----------------------------------------------------------------------
    local components
    components=$(echo "$health_response" | python -c "
import sys, json
data = json.load(sys.stdin)
for comp, active in data.get('components', {}).items():
    if not active:
        print(f'{comp}:{active}')
" 2>/dev/null)
    
    if [ -n "$components" ]; then
        log_debug "✗ Componentes inactivos: $components"
        return 1
    fi
    
    log_debug "✓ Todos los componentes activos"
    return 0
}

# ----------------------------------------------------------------------------
# EJECUCIÓN PRINCIPAL - Ejecutar todas las verificaciones
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------
# Ejecutamos todas las verificaciones en secuencia.
# Si alguna falla, retornamos código de error (exit 1).
# ----------------------------------------------------------------------
main() {
    log_debug "Iniciando health check del MCP Hub..."
    
    # Verificación 1: API REST respondiendo
    if ! check_api_health; then
        echo "Health check failed: API REST no responde"
        exit 1
    fi
    
    # Verificación 2: Respuesta JSON válida
    if ! validate_json_response; then
        echo "Health check failed: Respuesta inválida"
        exit 1
    fi
    
    # Verificación 3: Estado de componentes internos
    if ! check_components_status; then
        echo "Health check failed: Componentes no saludables"
        exit 1
    fi
    
    # Si llegamos aquí, todo está bien
    log_debug "Health check exitoso"
    echo "Health check exitoso"
    exit 0
}

# Ejecutar función principal
main
