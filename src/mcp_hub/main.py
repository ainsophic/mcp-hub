"""
MCP Hub - Aplicación Principal con FastAPI y FastMCP
======================================================

Este módulo implementa la aplicación principal del MCP Hub,
integrando FastAPI para la API REST y FastMCP para el
protocolo MCP (Model Context Protocol).

Componentes:
- API REST para gestión de servidores y tenants
- Endpoint MCP para comunicación con agentes de IA (Claude Desktop)
- Gateway WebSocket para MCP Apps
- Proxy para recursos estáticos de Apps

Arquitectura:
- FastAPI: Servidor web HTTP
- FastMCP: Servidor MCP con herramientas de gestión
- Integration: Todos los componentes core integrados

Autor: Ainsophic Team
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Añadir directorio src al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_hub.core.registry import Registry
from mcp_hub.core.orchestrator import Orchestrator
from mcp_hub.core.router import DynamicToolRouter
from mcp_hub.core.multitenant import MultitenantManager
from mcp_hub.gateway.websocket import MCPAppGateway
from mcp_hub.gateway.ui_proxy import UIProxy
from mcp_hub.gateway.websocket import WebSocketMessage, MessageType


# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Componentes globales
_registry: Optional[Registry] = None
_orchestrator: Optional[Orchestrator] = None
_router: Optional[DynamicToolRouter] = None
_multitenant_manager: Optional[MultitenantManager] = None
_gateway: Optional[MCPAppGateway] = None
_ui_proxy: Optional[UIProxy] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Context manager para el ciclo de vida de la aplicación.
    
    Maneja el startup y shutdown del MCP Hub:
    - Startup: Cargar configuración, inicializar componentes
    - Shutdown: Detener servidores, limpiar recursos
    """
    global _registry, _orchestrator, _router, _multitenant_manager, _gateway, _ui_proxy
    
    logger.info("=" * 60)
    logger.info("MCP Hub - Iniciando...")
    logger.info("=" * 60)
    
    try:
        # Cargar configuración
        config_path = os.environ.get(
            "MCP_HUB_CONFIG",
            str(Path(__file__).parent.parent.parent / "config" / "servers.json")
        )
        
        logger.info(f"Cargando configuración desde: {config_path}")
        _registry = Registry.load(config_path)
        
        # Configurar logging según config
        logging.getLogger().setLevel(_registry.logging.level)
        
        # Inicializar componentes core
        logger.info("Inicializando Orchestrator...")
        _orchestrator = Orchestrator(_registry)
        
        logger.info("Inicializando Router dinámico...")
        _router = DynamicToolRouter(_orchestrator)
        
        logger.info("Inicializando MultitenantManager...")
        _multitenant_manager = MultitenantManager(
            _registry,
            _orchestrator,
            _router
        )
        
        # Inicializar gateway
        logger.info("Inicializando MCPAppGateway...")
        _gateway = MCPAppGateway(
            _orchestrator,
            _router,
            _multitenant_manager
        )
        
        # Inicializar UI Proxy
        logger.info("Inicializando UIProxy...")
        plugins_dir = os.environ.get(
            "MCP_HUB_PLUGINS_DIR",
            str(Path(__file__).parent.parent.parent / "plugins")
        )
        _ui_proxy = UIProxy(plugins_dir=plugins_dir)
        
        # Iniciar servidores si auto_start está habilitado
        if _registry.orchestrator.auto_start:
            logger.info("Auto-start habilitado, iniciando servidores...")
            for tenant_id in _registry.get_all_tenants():
                try:
                    await _multitenant_manager.start_tenant_servers(tenant_id)
                except Exception as e:
                    logger.error(f"Error iniciando servidores del tenant {tenant_id}: {e}")
        
        # Iniciar monitoreo de servidores
        await _orchestrator.start_monitoring(interval=5.0)
        
        logger.info("=" * 60)
        logger.info("MCP Hub - Inicialización completada exitosamente")
        logger.info("=" * 60)
        
        yield
        
    except Exception as e:
        logger.error(f"Error durante inicialización: {e}")
        raise
    
    finally:
        logger.info("MCP Hub - Iniciando shutdown...")
        
        # Detener monitoreo
        if _orchestrator:
            await _orchestrator.stop_monitoring()
        
        # Detener todos los servidores
        if _orchestrator:
            await _orchestrator.shutdown()
        
        logger.info("MCP Hub - Shutdown completado")


# Crear aplicación FastAPI
app = FastAPI(
    title="MCP Hub",
    description="Orquestador Multitenant para Servidores MCP y MCP Apps",
    version="0.1.0",
    lifespan=lifespan
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Endpoints de Salud y Estado
# ============================================================================

@app.get("/")
async def root() -> JSONResponse:
    """
    Endpoint raíz con información del Hub.
    """
    return JSONResponse(content={
        "name": "MCP Hub",
        "version": "0.1.0",
        "status": "running",
        "description": "Orquestador Multitenant para Servidores MCP y MCP Apps"
    })


@app.get("/health")
async def health() -> JSONResponse:
    """
    Endpoint de salud para monitoreo.
    """
    return JSONResponse(content={
        "status": "healthy",
        "components": {
            "registry": _registry is not None,
            "orchestrator": _orchestrator is not None,
            "router": _router is not None,
            "multitenant_manager": _multitenant_manager is not None,
            "gateway": _gateway is not None,
            "ui_proxy": _ui_proxy is not None
        }
    })


# ============================================================================
# Endpoints de Gestión de Tenants
# ============================================================================

@app.get("/api/tenants")
async def list_tenants() -> JSONResponse:
    """
    Lista todos los tenants configurados.
    """
    if not _registry:
        return JSONResponse(content={"error": "Registry no inicializado"}, status_code=500)
    
    tenants_info = {}
    for tenant_id in _registry.get_all_tenants():
        tenant_status = _multitenant_manager.get_tenant_status(tenant_id)
        tenants_info[tenant_id] = tenant_status
    
    return JSONResponse(content={
        "tenants": tenants_info,
        "total": len(tenants_info)
    })


@app.get("/api/tenants/{tenant_id}")
async def get_tenant(tenant_id: str) -> JSONResponse:
    """
    Obtiene información detallada de un tenant.
    """
    if not _multitenant_manager:
        return JSONResponse(content={"error": "MultitenantManager no inicializado"}, status_code=500)
    
    status = _multitenant_manager.get_tenant_status(tenant_id)
    
    if not status:
        return JSONResponse(content={"error": "Tenant no encontrado"}, status_code=404)
    
    return JSONResponse(content=status)


@app.get("/api/tenants/{tenant_id}/tools")
async def get_tenant_tools(tenant_id: str) -> JSONResponse:
    """
    Lista las herramientas disponibles para un tenant.
    """
    if not _multitenant_manager:
        return JSONResponse(content={"error": "MultitenantManager no inicializado"}, status_code=500)
    
    tools_summary = _multitenant_manager.get_tenant_tools_summary(tenant_id)
    return JSONResponse(content=tools_summary)


@app.post("/api/tenants/{tenant_id}/start")
async def start_tenant(tenant_id: str) -> JSONResponse:
    """
    Inicia todos los servidores de un tenant.
    """
    if not _multitenant_manager:
        return JSONResponse(content={"error": "MultitenantManager no inicializado"}, status_code=500)
    
    try:
        servers = await _multitenant_manager.start_tenant_servers(tenant_id)
        return JSONResponse(content={
            "message": f"Servidores iniciados para tenant {tenant_id}",
            "servers_count": len(servers)
        })
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/api/tenants/{tenant_id}/stop")
async def stop_tenant(tenant_id: str) -> JSONResponse:
    """
    Detiene todos los servidores de un tenant.
    """
    if not _multitenant_manager:
        return JSONResponse(content={"error": "MultitenantManager no inicializado"}, status_code=500)
    
    try:
        await _multitenant_manager.stop_tenant_servers(tenant_id)
        return JSONResponse(content={
            "message": f"Servidores detenidos para tenant {tenant_id}"
        })
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


# ============================================================================
# Endpoints de Gestión de Servidores
# ============================================================================

@app.get("/api/servers")
async def list_servers() -> JSONResponse:
    """
    Lista todos los servidores gestionados.
    """
    if not _orchestrator:
        return JSONResponse(content={"error": "Orchestrator no inicializado"}, status_code=500)
    
    servers_status = _orchestrator.get_all_servers_status()
    return JSONResponse(content={
        "servers": servers_status,
        "total": len(servers_status)
    })


@app.get("/api/servers/{tenant_id}/{server_name}")
async def get_server(tenant_id: str, server_name: str) -> JSONResponse:
    """
    Obtiene el estado de un servidor específico.
    """
    if not _orchestrator:
        return JSONResponse(content={"error": "Orchestrator no inicializado"}, status_code=500)
    
    server_id = f"{tenant_id}:{server_name}"
    status = _orchestrator.get_server_status(server_id)
    
    if not status:
        return JSONResponse(content={"error": "Servidor no encontrado"}, status_code=404)
    
    return JSONResponse(content=status)


@app.post("/api/servers/{tenant_id}/{server_name}/start")
async def start_server(tenant_id: str, server_name: str) -> JSONResponse:
    """
    Inicia un servidor específico.
    """
    if not _orchestrator:
        return JSONResponse(content={"error": "Orchestrator no inicializado"}, status_code=500)
    
    try:
        server_id = f"{tenant_id}:{server_name}"
        server = await _orchestrator.start_server(server_id)
        
        # Descubrir herramientas
        await _router.discover_tools(server_id)
        
        return JSONResponse(content={
            "message": f"Servidor iniciado: {server_id}",
            "state": server.state.name
        })
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/api/servers/{tenant_id}/{server_name}/stop")
async def stop_server(tenant_id: str, server_name: str) -> JSONResponse:
    """
    Detiene un servidor específico.
    """
    if not _orchestrator:
        return JSONResponse(content={"error": "Orchestrator no inicializado"}, status_code=500)
    
    try:
        server_id = f"{tenant_id}:{server_name}"
        await _orchestrator.stop_server(server_id)
        
        return JSONResponse(content={
            "message": f"Servidor detenido: {server_id}"
        })
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


# ============================================================================
# Endpoints de Herramientas
# ============================================================================

@app.get("/api/tools")
async def list_tools() -> JSONResponse:
    """
    Lista todas las herramientas disponibles en el Hub.
    """
    if not _router:
        return JSONResponse(content={"error": "Router no inicializado"}, status_code=500)
    
    summary = _router.get_tools_summary()
    return JSONResponse(content=summary)


@app.post("/api/tools/{tool_name}/call")
async def call_tool(tool_name: str, request: Request) -> JSONResponse:
    """
    Ejecuta una llamada a una herramienta.
    """
    if not _router:
        return JSONResponse(content={"error": "Router no inicializado"}, status_code=500)
    
    try:
        arguments = await request.json()
        result = await _router.call_tool(tool_name, arguments)
        
        return JSONResponse(content={
            "tool": tool_name,
            "result": result
        })
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


# ============================================================================
# Endpoints del Gateway WebSocket
# ============================================================================

@app.websocket("/ws/app/{app_id}/{tenant_id}")
async def websocket_endpoint(websocket: WebSocket, app_id: str, tenant_id: str):
    """
    Endpoint WebSocket para MCP Apps.
    
    Este endpoint maneja conexiones WebSocket bidireccionales
    entre las MCP Apps y el Hub, permitiendo comunicación
    en tiempo real con los servidores MCP backend.
    """
    if not _gateway:
        await websocket.close(code=1011, reason="Gateway no inicializado")
        return
    
    await _gateway.handle_websocket(websocket, app_id, tenant_id)


# ============================================================================
# Endpoints del UI Proxy
# ============================================================================

@app.get("/api/apps")
async def list_apps() -> JSONResponse:
    """
    Lista todas las MCP Apps disponibles.
    """
    if not _ui_proxy:
        return JSONResponse(content={"error": "UIProxy no inicializado"}, status_code=500)
    
    return await _ui_proxy.list_apps()


@app.get("/api/apps/{app_id}")
async def get_app_info(app_id: str) -> JSONResponse:
    """
    Obtiene información detallada de una MCP App.
    """
    if not _ui_proxy:
        return JSONResponse(content={"error": "UIProxy no inicializado"}, status_code=500)
    
    try:
        return await _ui_proxy.get_app_info(app_id)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/apps/{app_id}")
async def serve_app(app_id: str, tenant_id: str = "default", request: Request = None) -> HTMLResponse:
    """
    Sirve el index.html de una MCP App con configuración inyectada.
    """
    if not _ui_proxy:
        return HTMLResponse(content="<h1>Error: UIProxy no inicializado</h1>", status_code=500)
    
    try:
        return await _ui_proxy.serve_app_index(
            app_id,
            tenant_id,
            request
        )
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error: {str(e)}</h1>", status_code=500)


@app.get("/apps/{app_id}/{resource_path:path}")
async def serve_app_resource(
    app_id: str,
    resource_path: str,
    request: Request
) -> JSONResponse:
    """
    Sirve recursos estáticos de una MCP App.
    """
    if not _ui_proxy:
        return JSONResponse(content={"error": "UIProxy no inicializado"}, status_code=500)
    
    try:
        return await _ui_proxy.serve_resource(
            app_id,
            resource_path,
            request
        )
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=404)


# ============================================================================
# Endpoints de Estado del Gateway
# ============================================================================

@app.get("/api/gateway/status")
async def gateway_status() -> JSONResponse:
    """
    Retorna el estado actual del gateway WebSocket.
    """
    if not _gateway:
        return JSONResponse(content={"error": "Gateway no inicializado"}, status_code=500)
    
    return JSONResponse(content=_gateway.get_gateway_status())


# ============================================================================
# CLI para iniciar el servidor
# ============================================================================

def cli():
    """
    Entry point para la CLI del MCP Hub.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Hub - Orquestador Multitenant")
    parser.add_argument(
        "--config",
        type=str,
        default="config/servers.json",
        help="Ruta al archivo de configuración JSON"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host donde escuchar el servidor"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Puerto para la API REST"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Habilitar recarga automática en desarrollo"
    )
    
    args = parser.parse_args()
    
    # Configurar variables de entorno
    os.environ["MCP_HUB_CONFIG"] = args.config
    
    logger.info(f"Iniciando MCP Hub en {args.host}:{args.port}")
    
    uvicorn.run(
        "mcp_hub.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


if __name__ == "__main__":
    cli()
