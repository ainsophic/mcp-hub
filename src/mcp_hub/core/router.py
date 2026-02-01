"""
Dynamic Tool Router - Enrutamiento Dinámico de Herramientas MCP
=================================================================

Este módulo implementa el router dinámico de herramientas MCP, permitiendo:
- Descubrir automáticamente herramientas de servidores MCP conectados
- Exponer herramientas con prefijos namespaced (ej: "postgres.query")
- Enrutar llamadas a herramientas al servidor correcto
- Agregar metadatos y documentación de herramientas

Patrones de Diseño Utilizados:
- Proxy: Para interceptar y enrutar llamadas
- Registry: Para mantener el catálogo de herramientas
- Factory: Para crear wrappers de herramientas dinámicamente

Autor: Ainsophic Team
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from functools import wraps

from mcp_hub.core.orchestrator import Orchestrator, ManagedServer
from mcp_hub.transport.stdio_client import ToolInfo, MCPToolCallError


logger = logging.getLogger(__name__)


@dataclass
class ToolRegistration:
    """
    Registro de una herramienta en el router.
    
    Atributos:
        tool_id: ID único de la herramienta (formato: "server_id:tool_name")
        server_id: ID del servidor que provee la herramienta
        original_name: Nombre original de la herramienta en el servidor
        prefixed_name: Nombre con prefijo namespaced (ej: "postgres.query")
        description: Descripción de la herramienta
        input_schema: Schema JSON para los argumentos de entrada
        metadata: Metadatos adicionales
    """
    tool_id: str
    server_id: str
    original_name: str
    prefixed_name: str
    description: str
    input_schema: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


class RouterError(Exception):
    """Excepción base para errores del router."""
    pass


class ToolNotFoundError(RouterError):
    """Excepción levantada cuando no se encuentra una herramienta."""
    pass


class ServerNotAvailableError(RouterError):
    """Excepción levantada cuando el servidor de una herramienta no está disponible."""
    pass


class DynamicToolRouter:
    """
    Router dinámico de herramientas MCP.
    
    Esta clase gestiona el descubrimiento y enrutamiento de herramientas
    provenientes de múltiples servidores MCP. Proporciona una interfaz
    unificada para acceder a todas las herramientas disponibles,
    independientemente del servidor que las provee.
    
    Funcionalidades:
    - Descubrimiento automático de herramientas de servidores conectados
    - Prefijos namespaced para evitar conflictos de nombres
    - Enrutamiento transparente de llamadas a herramientas
    - Catálogo centralizado de todas las herramientas disponibles
    - Soporte para metadatos y documentación de herramientas
    
    Ejemplo de uso:
        >>> router = DynamicToolRouter(orchestrator)
        >>> await router.discover_tools("default:postgres")
        >>> tools = router.list_tools()
        >>> result = await router.call_tool("postgres.query", {"sql": "SELECT *"})
        
    Arquitectura:
    Las herramientas se identifican con prefijos namespaced en el formato:
    "server_name.tool_name", donde "server_name" es el nombre del servidor
    MCP y "tool_name" es el nombre original de la herramienta.
    """
    
    def __init__(self, orchestrator: Orchestrator):
        """
        Inicializa el router dinámico.
        
        Args:
            orchestrator: Instancia del Orchestrator para acceder a servidores
        """
        self.orchestrator = orchestrator
        self.tools: Dict[str, ToolRegistration] = {}
        self._tool_handlers: Dict[str, Callable] = {}
        
        logger.info("DynamicToolRouter inicializado")
    
    def _generate_prefixed_name(self, server_id: str, tool_name: str) -> str:
        """
        Genera el nombre prefijado para una herramienta.
        
        El formato es "server_name.tool_name" donde server_name
        es el nombre del servidor sin el tenant_id.
        
        Args:
            server_id: ID completo del servidor ("tenant_id:server_name")
            tool_name: Nombre original de la herramienta
            
        Returns:
            Nombre prefijado de la herramienta
        """
        _, server_name = self.orchestrator._parse_server_id(server_id)
        return f"{server_name}.{tool_name}"
    
    def _generate_tool_id(self, server_id: str, tool_name: str) -> str:
        """
        Genera un ID único para una herramienta.
        
        Args:
            server_id: ID del servidor
            tool_name: Nombre de la herramienta
            
        Returns:
            ID único de la herramienta
        """
        return f"{server_id}:{tool_name}"
    
    async def discover_tools(self, server_id: str) -> List[ToolRegistration]:
        """
        Descubre las herramientas de un servidor específico.
        
        Este método conecta al servidor MCP, inicializa la sesión
        y lista todas las herramientas disponibles, registrándolas
        en el catálogo del router.
        
        Args:
            server_id: ID del servidor a descubrir
            
        Returns:
            Lista de ToolRegistration descubiertas
            
        Raises:
            ServerNotAvailableError: Si el servidor no está disponible
            RouterError: Si falla el descubrimiento
        """
        logger.info(f"Descubriendo herramientas del servidor: {server_id}")
        
        # Obtener cliente del servidor
        client = self.orchestrator.get_server_client(server_id)
        if not client:
            raise ServerNotAvailableError(
                f"Servidor no disponible o no iniciado: {server_id}"
            )
        
        # Verificar que el servidor está inicializado
        if not client.is_initialized:
            raise ServerNotAvailableError(
                f"Servidor no inicializado: {server_id}"
            )
        
        try:
            # Listar herramientas
            tools = await client.list_tools()
            discovered = []
            
            for tool in tools:
                # Generar IDs y nombres
                tool_id = self._generate_tool_id(server_id, tool.name)
                prefixed_name = self._generate_prefixed_name(server_id, tool.name)
                
                # Crear registro
                registration = ToolRegistration(
                    tool_id=tool_id,
                    server_id=server_id,
                    original_name=tool.name,
                    prefixed_name=prefixed_name,
                    description=tool.description,
                    input_schema=tool.input_schema
                )
                
                # Registrar herramienta
                self.tools[tool_id] = registration
                discovered.append(registration)
                
                logger.debug(
                    f"Herramienta registrada: {prefixed_name} "
                    f"(orig: {tool.name}, servidor: {server_id})"
                )
            
            logger.info(f"Herramientas descubiertas para {server_id}: {len(discovered)}")
            return discovered
            
        except Exception as e:
            logger.error(f"Error descubriendo herramientas de {server_id}: {e}")
            raise RouterError(f"Fallo al descubrir herramientas: {e}") from e
    
    async def discover_all_tools(self) -> List[ToolRegistration]:
        """
        Descubre las herramientas de todos los servidores activos.
        
        Returns:
            Lista de todas las ToolRegistration descubiertas
        """
        logger.info("Descubriendo herramientas de todos los servidores")
        
        all_tools = []
        servers_status = self.orchestrator.get_all_servers_status()
        
        for server_id, status in servers_status.items():
            if status["state"] == "RUNNING":
                try:
                    tools = await self.discover_tools(server_id)
                    all_tools.extend(tools)
                except Exception as e:
                    logger.warning(
                        f"Error descubriendo herramientas de {server_id}: {e}"
                    )
        
        logger.info(f"Total de herramientas descubiertas: {len(all_tools)}")
        return all_tools
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: Optional[float] = None
    ) -> Any:
        """
        Ejecuta una llamada a una herramienta MCP.
        
        Este método acepta el nombre prefijado de una herramienta
        y enruta la llamada al servidor MCP correspondiente.
        
        Args:
            tool_name: Nombre prefijado de la herramienta (ej: "postgres.query")
            arguments: Argumentos para la herramienta
            timeout: Timeout específico para esta llamada
            
        Returns:
            Resultado de la ejecución de la herramienta
            
        Raises:
            ToolNotFoundError: Si la herramienta no existe
            ServerNotAvailableError: Si el servidor no está disponible
            MCPToolCallError: Si falla la ejecución de la herramienta
        """
        logger.debug(f"Llamando a herramienta: {tool_name}")
        
        # Buscar la herramienta en el registro
        registration = None
        for reg in self.tools.values():
            if reg.prefixed_name == tool_name:
                registration = reg
                break
        
        if not registration:
            available = [reg.prefixed_name for reg in self.tools.values()]
            raise ToolNotFoundError(
                f"Herramienta no encontrada: {tool_name}. "
                f"Disponibles: {sorted(available)}"
            )
        
        # Obtener cliente del servidor
        client = self.orchestrator.get_server_client(registration.server_id)
        if not client:
            raise ServerNotAvailableError(
                f"Servidor no disponible: {registration.server_id}"
            )
        
        try:
            # Enrutar llamada al servidor
            result = await client.call_tool(
                tool_name=registration.original_name,
                arguments=arguments,
                timeout=timeout
            )
            
            logger.debug(f"Herramienta ejecutada exitosamente: {tool_name}")
            return result
            
        except MCPToolCallError as e:
            logger.error(f"Error ejecutando herramienta {tool_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error inesperado en herramienta {tool_name}: {e}")
            raise RouterError(f"Error ejecutando herramienta: {e}") from e
    
    def list_tools(self, server_id: Optional[str] = None) -> List[ToolRegistration]:
        """
        Lista las herramientas registradas.
        
        Args:
            server_id: Si se especifica, retorna solo herramientas de ese servidor
            
        Returns:
            Lista de ToolRegistration
        """
        if server_id:
            return [
                reg for reg in self.tools.values()
                if reg.server_id == server_id
            ]
        
        return list(self.tools.values())
    
    def get_tool(self, tool_name: str) -> Optional[ToolRegistration]:
        """
        Retorna el registro de una herramienta específica.
        
        Args:
            tool_name: Nombre prefijado de la herramienta
            
        Returns:
            ToolRegistration si existe, None en caso contrario
        """
        for reg in self.tools.values():
            if reg.prefixed_name == tool_name:
                return reg
        return None
    
    def get_tools_by_server(self, server_id: str) -> List[ToolRegistration]:
        """
        Retorna todas las herramientas de un servidor específico.
        
        Args:
            server_id: ID del servidor
            
        Returns:
            Lista de ToolRegistration del servidor
        """
        return [
            reg for reg in self.tools.values()
            if reg.server_id == server_id
        ]
    
    def get_tools_summary(self) -> Dict[str, Any]:
        """
        Retorna un resumen de las herramientas registradas.
        
        Returns:
            Diccionario con estadísticas y lista de herramientas
        """
        tools_by_server: Dict[str, List[str]] = {}
        
        for reg in self.tools.values():
            if reg.server_id not in tools_by_server:
                tools_by_server[reg.server_id] = []
            tools_by_server[reg.server_id].append(reg.prefixed_name)
        
        return {
            "total_tools": len(self.tools),
            "total_servers": len(tools_by_server),
            "tools_by_server": tools_by_server,
            "all_tools": sorted([reg.prefixed_name for reg in self.tools.values()])
        }
    
    async def register_tool_handler(
        self,
        tool_name: str,
        handler: Callable
    ) -> None:
        """
        Registra un handler personalizado para una herramienta.
        
        Esto permite interceptar y modificar el comportamiento
        de una herramienta específica.
        
        Args:
            tool_name: Nombre prefijado de la herramienta
            handler: Función que manejará las llamadas
        """
        self._tool_handlers[tool_name] = handler
        logger.debug(f"Handler registrado para herramienta: {tool_name}")
    
    def remove_tool_handler(self, tool_name: str) -> None:
        """
        Elimina un handler personalizado de una herramienta.
        
        Args:
            tool_name: Nombre prefijado de la herramienta
        """
        if tool_name in self._tool_handlers:
            del self._tool_handlers[tool_name]
            logger.debug(f"Handler eliminado de herramienta: {tool_name}")
    
    def clear_tools(self, server_id: Optional[str] = None) -> None:
        """
        Limpia el registro de herramientas.
        
        Args:
            server_id: Si se especifica, limpia solo herramientas de ese servidor
        """
        if server_id:
            to_remove = [
                tool_id for tool_id, reg in self.tools.items()
                if reg.server_id == server_id
            ]
            for tool_id in to_remove:
                del self.tools[tool_id]
            logger.info(f"Herramientas limpiadas para servidor: {server_id}")
        else:
            self.tools.clear()
            logger.info("Todas las herramientas limpiadas")
    
    async def refresh_tools(self, server_id: str) -> List[ToolRegistration]:
        """
        Refresca las herramientas de un servidor.
        
        Limpia las herramientas existentes del servidor y las
        redescubre desde cero.
        
        Args:
            server_id: ID del servidor a refrescar
            
        Returns:
            Lista de ToolRegistration redescubiertas
        """
        logger.info(f"Refrescando herramientas del servidor: {server_id}")
        
        # Limpiar herramientas existentes
        self.clear_tools(server_id)
        
        # Redescubrir
        return await self.discover_tools(server_id)
    
    def create_tool_wrapper(self, tool_name: str) -> Callable:
        """
        Crea un wrapper de alto nivel para una herramienta.
        
        Este método crea una función que puede ser registrada
        en FastMCP para exponer herramientas MCP del Hub
        como si fueran propias.
        
        Args:
            tool_name: Nombre prefijado de la herramienta
            
        Returns:
            Función wrapper que ejecuta la herramienta
            
        Raises:
            ToolNotFoundError: Si la herramienta no existe
        """
        registration = self.get_tool(tool_name)
        if not registration:
            raise ToolNotFoundError(f"Herramienta no encontrada: {tool_name}")
        
        @wraps(registration.original_name)
        async def wrapper(**kwargs) -> Any:
            return await self.call_tool(tool_name, kwargs)
        
        wrapper.__name__ = tool_name
        wrapper.__doc__ = registration.description
        
        return wrapper
    
    def create_all_tool_wrappers(self) -> Dict[str, Callable]:
        """
        Crea wrappers para todas las herramientas registradas.
        
        Returns:
            Diccionario mapeando nombres de herramientas a wrappers
        """
        wrappers = {}
        
        for registration in self.tools.values():
            try:
                wrapper = self.create_tool_wrapper(registration.prefixed_name)
                wrappers[registration.prefixed_name] = wrapper
            except ToolNotFoundError:
                continue
        
        logger.info(f"Wrappers creados para {len(wrappers)} herramientas")
        return wrappers
