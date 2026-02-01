"""
Módulo Gateway - Gateway para MCP Apps
========================================

Este paquete contiene los componentes para el gateway de MCP Apps:
- WebSocket: Comunicación bidireccional en tiempo real
- UI Proxy: Proxy para recursos estáticos de las apps
"""

from mcp_hub.gateway.websocket import MCPAppGateway
from mcp_hub.gateway.ui_proxy import UIProxy

__all__ = [
    "MCPAppGateway",
    "UIProxy",
]
