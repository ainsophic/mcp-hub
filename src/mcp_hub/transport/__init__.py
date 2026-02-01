"""
Módulo Transport - Gestión de Conexiones a Servidores MCP
============================================================

Este paquete contiene los componentes para manejar diferentes tipos de transporte:
- Stdio Client: Comunicación vía stdio con servidores MCP
- Future: SSE Client, HTTP Client
"""

from mcp_hub.transport.stdio_client import StdioClientWrapper

__all__ = [
    "StdioClientWrapper",
]
