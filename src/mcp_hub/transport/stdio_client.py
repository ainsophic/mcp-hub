"""
Stdio Client Wrapper - Cliente MCP con Transporte Stdio
========================================================

Este módulo implementa un wrapper sobre el cliente MCP oficial para comunicación
vía stdio. Proporciona una interfaz simplificada y robusta para interactuar
con servidores MCP.

Funcionalidades:
- Inicialización automática de sesiones MCP
- Manejo de llamadas a herramientas (tools)
- Listado de herramientas y recursos
- Manejo de errores y reintentos
- Contexto async seguro

Patrones de Diseño Utilizados:
- Context Manager: Para gestión segura de recursos
- Facade: Para simplificar la interacción con el SDK MCP

Autor: Ainsophic Team
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


logger = logging.getLogger(__name__)


@dataclass
class ToolInfo:
    """
    Información sobre una herramienta MCP.
    
    Atributos:
        name: Nombre de la herramienta
        description: Descripción de la herramienta
        input_schema: Schema JSON para los argumentos de entrada
    """
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServerInfo:
    """
    Información sobre un servidor MCP.
    
    Atributos:
        name: Nombre del servidor
        version: Versión del protocolo MCP soportada
        capabilities: Lista de capacidades soportadas
        tools: Diccionario de herramientas disponibles
    """
    name: str
    version: str = "1.0.0"
    capabilities: Dict[str, Any] = field(default_factory=dict)
    tools: Dict[str, ToolInfo] = field(default_factory=dict)


class MCPConnectionError(Exception):
    """Excepción levantada cuando falla la conexión a un servidor MCP."""
    pass


class MCPInitializationError(Exception):
    """Excepción levantada cuando falla la inicialización de una sesión MCP."""
    pass


class MCPToolCallError(Exception):
    """Excepción levantada cuando falla una llamada a una herramienta MCP."""
    pass


class StdioClientWrapper:
    """
    Wrapper para cliente MCP con transporte stdio.
    
    Esta clase proporciona una interfaz simplificada para comunicarse
    con servidores MCP usando el protocolo stdio. Maneja automáticamente
    la inicialización de sesiones y proporciona métodos de alto nivel
    para interactuar con herramientas y recursos.
    
    Ejemplo de uso:
        >>> wrapper = StdioClientWrapper("python", ["-m", "mcp.server.sqlite"])
        >>> async with wrapper.connect():
        ...     tools = await wrapper.list_tools()
        ...     result = await wrapper.call_tool("query", {"sql": "SELECT * FROM users"})
        
    Nota: Esta clase debe usarse como contexto async para garantizar
    la liberación correcta de recursos.
    """
    
    def __init__(
        self,
        command: str,
        args: List[str],
        timeout: float = 30.0,
        max_retries: int = 3
    ):
        """
        Inicializa el wrapper del cliente MCP.
        
        Args:
            command: Comando para ejecutar el servidor MCP
            args: Argumentos del comando
            timeout: Timeout en segundos para operaciones MCP
            max_retries: Número máximo de reintentos para operaciones
        """
        self.command = command
        self.args = args
        self.timeout = timeout
        self.max_retries = max_retries
        
        self._session: Optional[ClientSession] = None
        self._stdio_context = None
        self._connected = False
        self._initialized = False
        self._server_info: Optional[ServerInfo] = None
        
        logger.debug(f"StdioClientWrapper inicializado para: {command} {' '.join(args)}")
    
    def _get_server_params(self) -> StdioServerParameters:
        """
        Crea los parámetros del servidor stdio.
        
        Returns:
            StdioServerParameters configurado para el servidor
        """
        return StdioServerParameters(
            command=self.command,
            args=self.args
        )
    
    async def connect(self) -> "StdioClientWrapper":
        """
        Establece conexión con el servidor MCP.
        
        Returns:
            Self para permitir encadenamiento
            
        Raises:
            MCPConnectionError: Si falla la conexión
        """
        if self._connected:
            logger.warning("Ya hay una conexión activa")
            return self
        
        try:
            # Crear contexto stdio
            server_params = self._get_server_params()
            self._stdio_context = stdio_client(server_params)
            read_stream, write_stream = await self._stdio_context.__aenter__()
            
            # Crear sesión MCP
            self._session = ClientSession(read_stream, write_stream)
            await self._session.__aenter__()
            
            self._connected = True
            logger.info(f"Conexión establecida con servidor: {self.command}")
            
            return self
            
        except Exception as e:
            logger.error(f"Error al conectar con servidor: {e}")
            await self.disconnect()
            raise MCPConnectionError(f"Fallo al conectar: {e}") from e
    
    async def initialize(self) -> ServerInfo:
        """
        Inicializa la sesión MCP y descubre capacidades.
        
        Returns:
            ServerInfo con información del servidor y herramientas disponibles
            
        Raises:
            MCPInitializationError: Si falla la inicialización
        """
        if not self._connected:
            raise MCPConnectionError("No hay conexión activa. Usar connect() primero.")
        
        if self._initialized:
            return self._server_info
        
        try:
            # Inicializar sesión
            init_result = await asyncio.wait_for(
                self._session.initialize(),
                timeout=self.timeout
            )
            
            # Extraer información del servidor
            capabilities = getattr(init_result, 'capabilities', {})
            server_info = getattr(init_result, 'serverInfo', {})
            
            # Crear objeto ServerInfo
            self._server_info = ServerInfo(
                name=server_info.get('name', 'unknown'),
                version=server_info.get('version', '1.0.0'),
                capabilities=capabilities
            )
            
            # Descubrir herramientas si está disponible
            if 'tools' in capabilities:
                tools_response = await self._session.list_tools()
                for tool in tools_response.tools:
                    self._server_info.tools[tool.name] = ToolInfo(
                        name=tool.name,
                        description=tool.description or "",
                        input_schema=tool.inputSchema or {}
                    )
            
            self._initialized = True
            logger.info(
                f"Sesión inicializada. Servidor: {self._server_info.name}, "
                f"Herramientas: {len(self._server_info.tools)}"
            )
            
            return self._server_info
            
        except asyncio.TimeoutError:
            error_msg = f"Timeout inicializando sesión ({self.timeout}s)"
            logger.error(error_msg)
            await self.disconnect()
            raise MCPInitializationError(error_msg)
            
        except Exception as e:
            logger.error(f"Error inicializando sesión: {e}")
            await self.disconnect()
            raise MCPInitializationError(f"Fallo al inicializar: {e}") from e
    
    async def list_tools(self) -> List[ToolInfo]:
        """
        Retorna la lista de herramientas disponibles.
        
        Returns:
            Lista de ToolInfo con información de cada herramienta
            
        Raises:
            MCPConnectionError: Si no hay conexión inicializada
        """
        if not self._initialized or self._server_info is None:
            raise MCPConnectionError("Sesión no inicializada. Usar initialize() primero.")
        
        return list(self._server_info.tools.values())
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: Optional[float] = None
    ) -> Any:
        """
        Ejecuta una llamada a una herramienta MCP.
        
        Args:
            tool_name: Nombre de la herramienta a invocar
            arguments: Argumentos para la herramienta (deben cumplir el schema)
            timeout: Timeout específico para esta llamada (usa el default si es None)
            
        Returns:
            Resultado de la ejecución de la herramienta
            
        Raises:
            MCPToolCallError: Si falla la llamada a la herramienta
            MCPConnectionError: Si no hay conexión inicializada
        """
        if not self._initialized or self._session is None:
            raise MCPConnectionError("Sesión no inicializada. Usar initialize() primero.")
        
        if tool_name not in self._server_info.tools:
            raise ValueError(f"Herramienta no encontrada: {tool_name}")
        
        timeout = timeout or self.timeout
        
        try:
            logger.debug(f"Llamando a herramienta: {tool_name} con args: {arguments}")
            
            # Ejecutar llamada con timeout y reintentos
            for attempt in range(self.max_retries):
                try:
                    result = await asyncio.wait_for(
                        self._session.call_tool(tool_name, arguments),
                        timeout=timeout
                    )
                    
                    logger.debug(f"Resultado exitoso de herramienta: {tool_name}")
                    return result
                    
                except asyncio.TimeoutError:
                    if attempt == self.max_retries - 1:
                        raise
                    logger.warning(
                        f"Timeout en llamada a herramienta {tool_name} "
                        f"(intentos {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(1)  # Esperar antes de reintentar
                    
        except asyncio.TimeoutError:
            error_msg = f"Timeout llamando a herramienta {tool_name} ({timeout}s)"
            logger.error(error_msg)
            raise MCPToolCallError(error_msg)
            
        except Exception as e:
            error_msg = f"Error llamando a herramienta {tool_name}: {e}"
            logger.error(error_msg)
            raise MCPToolCallError(error_msg) from e
    
    async def list_resources(self) -> List[Any]:
        """
        Retorna la lista de recursos disponibles.
        
        Returns:
            Lista de recursos del servidor
            
        Raises:
            MCPConnectionError: Si no hay conexión inicializada
        """
        if not self._initialized or self._session is None:
            raise MCPConnectionError("Sesión no inicializada. Usar initialize() primero.")
        
        if 'resources' not in self._server_info.capabilities:
            logger.warning("El servidor no soporta recursos")
            return []
        
        try:
            response = await self._session.list_resources()
            return response.resources
            
        except Exception as e:
            logger.error(f"Error listando recursos: {e}")
            return []
    
    async def read_resource(self, uri: str) -> str:
        """
        Lee el contenido de un recurso por su URI.
        
        Args:
            uri: URI del recurso a leer
            
        Returns:
            Contenido del recurso como string
            
        Raises:
            MCPConnectionError: Si no hay conexión inicializada
        """
        if not self._initialized or self._session is None:
            raise MCPConnectionError("Sesión no inicializada. Usar initialize() primero.")
        
        try:
            response = await self._session.read_resource(uri)
            return response.contents[0].text
            
        except Exception as e:
            logger.error(f"Error leyendo recurso {uri}: {e}")
            raise
    
    async def disconnect(self) -> None:
        """
        Cierra la conexión con el servidor MCP de forma segura.
        
        Este método debe llamarse para liberar recursos correctamente.
        """
        if not self._connected:
            return
        
        try:
            # Cerrar sesión MCP
            if self._session:
                await self._session.__aexit__(None, None, None)
                self._session = None
            
            # Cerrar contexto stdio
            if self._stdio_context:
                await self._stdio_context.__aexit__(None, None, None)
                self._stdio_context = None
            
            self._connected = False
            self._initialized = False
            self._server_info = None
            
            logger.info("Conexión cerrada exitosamente")
            
        except Exception as e:
            logger.error(f"Error al cerrar conexión: {e}")
    
    async def __aenter__(self):
        """
        Implementa el protocolo de contexto async para entrada.
        
        Returns:
            Self para permitir encadenamiento
        """
        await self.connect()
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Implementa el protocolo de contexto async para salida.
        """
        await self.disconnect()
    
    @property
    def is_connected(self) -> bool:
        """
        Indica si hay una conexión activa.
        
        Returns:
            True si está conectado, False en caso contrario
        """
        return self._connected
    
    @property
    def is_initialized(self) -> bool:
        """
        Indica si la sesión MCP ha sido inicializada.
        
        Returns:
            True si está inicializado, False en caso contrario
        """
        return self._initialized
    
    @property
    def server_info(self) -> Optional[ServerInfo]:
        """
        Retorna la información del servidor conectado.
        
        Returns:
            ServerInfo si está inicializado, None en caso contrario
        """
        return self._server_info
