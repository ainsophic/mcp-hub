"""
MCP Hub - Orquestador Multitenant para Servidores MCP y MCP Apps
=================================================================

Este módulo proporciona la funcionalidad principal del MCP Hub, incluyendo:
- Orquestación de múltiples servidores MCP
- Sistema multitenant con aislamiento de configuraciones
- Enrutamiento dinámico de herramientas
- Gateway para MCP Apps con comunicación WebSocket

Autor: Ainsophic Team
Licencia: MIT
"""

__version__ = "0.1.0"
__author__ = "Ainsophic"
__license__ = "MIT"

from mcp_hub.core.registry import Registry
from mcp_hub.core.orchestrator import Orchestrator
from mcp_hub.core.router import DynamicToolRouter
from mcp_hub.core.multitenant import MultitenantManager

__all__ = [
    "Registry",
    "Orchestrator",
    "DynamicToolRouter",
    "MultitenantManager",
]
