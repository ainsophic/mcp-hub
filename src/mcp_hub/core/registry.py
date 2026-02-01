"""
Registry - Gestión de Configuración y Descubrimiento de Servidores
====================================================================

Este módulo implementa el registro de servidores MCP, permitiendo:
- Cargar configuración desde archivos JSON
- Gestionar metadatos de servidores
- Proveer interfaz de consulta para el Orchestrator

Patrones de Diseño Utilizados:
- Singleton: Para garantizar una única instancia del registry
- Factory: Para crear instancias de configuración

Autor: Ainsophic Team
"""

import json
import os
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime


logger = logging.getLogger(__name__)


@dataclass
class ServerConfig:
    """
    Configuración de un servidor MCP.
    
    Atributos:
        name: Nombre único del servidor
        type: Tipo de servidor (database, api, file, etc.)
        command: Comando para iniciar el servidor
        args: Argumentos del comando
        enabled: Indica si el servidor está habilitado
        capabilities: Lista de capacidades (tools, resources, prompts)
        transport: Tipo de transporte (stdio, http, sse)
        metadata: Metadatos adicionales del servidor
    """
    name: str
    type: str
    command: str
    args: List[str] = field(default_factory=list)
    enabled: bool = True
    capabilities: List[str] = field(default_factory=list)
    transport: str = "stdio"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_full_command(self) -> List[str]:
        """
        Retorna el comando completo con argumentos.
        
        Returns:
            Lista con el comando y sus argumentos
        """
        return [self.command] + self.args


@dataclass
class TenantConfig:
    """
    Configuración de un tenant (inquilino).
    
    Atributos:
        tenant_id: Identificador único del tenant
        description: Descripción del tenant
        servers: Diccionario de servidores configurados
    """
    tenant_id: str
    description: str = ""
    servers: Dict[str, ServerConfig] = field(default_factory=dict)
    
    def get_enabled_servers(self) -> List[ServerConfig]:
        """
        Retorna la lista de servidores habilitados.
        
        Returns:
            Lista de servidores configurados como enabled=True
        """
        return [server for server in self.servers.values() if server.enabled]


@dataclass
class GatewayConfig:
    """
    Configuración del gateway HTTP/WebSocket.
    
    Atributos:
        port: Puerto para la API REST
        mcp_port: Puerto para el servidor MCP
        websocket_port: Puerto para el gateway WebSocket
        host: Host donde escucharán los servicios
    """
    port: int = 8080
    mcp_port: int = 8000
    websocket_port: int = 8081
    host: str = "0.0.0.0"


@dataclass
class LoggingConfig:
    """
    Configuración de logging.
    
    Atributos:
        level: Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format: Formato de los mensajes de log
    """
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class OrchestratorConfig:
    """
    Configuración del orchestrator.
    
    Atributos:
        auto_start: Iniciar servidores automáticamente al cargar
        max_retries: Número máximo de reintentos al iniciar
        startup_timeout: Timeout en segundos para el inicio de servidores
    """
    auto_start: bool = False
    max_retries: int = 3
    startup_timeout: int = 30


class Registry:
    """
    Registro centralizado de configuración del MCP Hub.
    
    Esta clase implementa el patrón Singleton para garantizar
    una única instancia del registry en toda la aplicación.
    
    Funcionalidades:
    - Cargar configuración desde archivos JSON
    - Gestionar tenants y sus servidores
    - Proveer acceso a configuraciones de gateway y logging
    
    Ejemplo de uso:
        >>> registry = Registry.load("config/servers.json")
        >>> tenant = registry.get_tenant("default")
        >>> servers = tenant.get_enabled_servers()
    """
    
    _instance: Optional["Registry"] = None
    
    def __init__(self):
        """
        Inicializa una nueva instancia del Registry.
        
        Nota: Este constructor debería ser llamado a través del método
        load() para garantizar el patrón Singleton.
        """
        self.version: str = "0.1.0"
        self.tenants: Dict[str, TenantConfig] = {}
        self.gateway: GatewayConfig = GatewayConfig()
        self.logging: LoggingConfig = LoggingConfig()
        self.orchestrator: OrchestratorConfig = OrchestratorConfig()
        self._config_path: Optional[Path] = None
        self._last_modified: Optional[datetime] = None
    
    @classmethod
    def load(cls, config_path: str) -> "Registry":
        """
        Carga la configuración desde un archivo JSON.
        
        Args:
            config_path: Ruta al archivo de configuración JSON
            
        Returns:
            Instancia del Registry con la configuración cargada
            
        Raises:
            FileNotFoundError: Si el archivo no existe
            json.JSONDecodeError: Si el JSON no es válido
        """
        if cls._instance is None:
            cls._instance = cls()
        
        instance = cls._instance
        instance._load_from_file(config_path)
        return instance
    
    @classmethod
    def get_instance(cls) -> "Registry":
        """
        Retorna la instancia existente del Registry.
        
        Returns:
            Instancia del Registry
            
        Raises:
            RuntimeError: Si no se ha inicializado el Registry
        """
        if cls._instance is None:
            raise RuntimeError("Registry no inicializado. Usar Registry.load() primero.")
        return cls._instance
    
    def _load_from_file(self, config_path: str) -> None:
        """
        Carga la configuración desde el archivo JSON especificado.
        
        Args:
            config_path: Ruta al archivo de configuración
            
        Raises:
            FileNotFoundError: Si el archivo no existe
            json.JSONDecodeError: Si el JSON no es válido
        """
        path = Path(config_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Archivo de configuración no encontrado: {config_path}")
        
        # Cargar JSON del archivo
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Guardar información del archivo
        self._config_path = path
        self._last_modified = datetime.fromtimestamp(path.stat().st_mtime)
        
        # Parsear configuración
        self.version = data.get("version", "0.1.0")
        self._parse_tenants(data.get("tenants", {}))
        self._parse_gateway(data.get("gateway", {}))
        self._parse_logging(data.get("logging", {}))
        self._parse_orchestrator(data.get("orchestrator", {}))
        
        logger.info(f"Configuración cargada exitosamente desde {config_path}")
        logger.info(f"Tenants cargados: {list(self.tenants.keys())}")
    
    def _parse_tenants(self, tenants_data: Dict[str, Any]) -> None:
        """
        Parsea la configuración de tenants.
        
        Args:
            tenants_data: Diccionario con datos de tenants
        """
        self.tenants.clear()
        
        for tenant_id, tenant_info in tenants_data.items():
            servers = {}
            
            for server_name, server_info in tenant_info.get("servers", {}).items():
                # Crear configuración del servidor
                server_config = ServerConfig(
                    name=server_name,
                    type=server_info.get("type", "unknown"),
                    command=server_info["command"],
                    args=server_info.get("args", []),
                    enabled=server_info.get("enabled", True),
                    capabilities=server_info.get("capabilities", []),
                    transport=server_info.get("transport", "stdio"),
                    metadata=server_info.get("metadata", {})
                )
                servers[server_name] = server_config
            
            # Crear configuración del tenant
            tenant_config = TenantConfig(
                tenant_id=tenant_id,
                description=tenant_info.get("description", ""),
                servers=servers
            )
            
            self.tenants[tenant_id] = tenant_config
    
    def _parse_gateway(self, gateway_data: Dict[str, Any]) -> None:
        """
        Parsea la configuración del gateway.
        
        Args:
            gateway_data: Diccionario con datos del gateway
        """
        self.gateway = GatewayConfig(
            port=gateway_data.get("port", 8080),
            mcp_port=gateway_data.get("mcp_port", 8000),
            websocket_port=gateway_data.get("websocket_port", 8081),
            host=gateway_data.get("host", "0.0.0.0")
        )
    
    def _parse_logging(self, logging_data: Dict[str, Any]) -> None:
        """
        Parsea la configuración de logging.
        
        Args:
            logging_data: Diccionario con datos de logging
        """
        self.logging = LoggingConfig(
            level=logging_data.get("level", "INFO"),
            format=logging_data.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
    
    def _parse_orchestrator(self, orchestrator_data: Dict[str, Any]) -> None:
        """
        Parsea la configuración del orchestrator.
        
        Args:
            orchestrator_data: Diccionario con datos del orchestrator
        """
        self.orchestrator = OrchestratorConfig(
            auto_start=orchestrator_data.get("auto_start", False),
            max_retries=orchestrator_data.get("max_retries", 3),
            startup_timeout=orchestrator_data.get("startup_timeout", 30)
        )
    
    def get_tenant(self, tenant_id: str) -> Optional[TenantConfig]:
        """
        Retorna la configuración de un tenant específico.
        
        Args:
            tenant_id: Identificador del tenant
            
        Returns:
            TenantConfig si existe, None en caso contrario
        """
        return self.tenants.get(tenant_id)
    
    def get_all_tenants(self) -> List[str]:
        """
        Retorna la lista de todos los tenant IDs.
        
        Returns:
            Lista de IDs de tenants
        """
        return list(self.tenants.keys())
    
    def get_server_config(self, tenant_id: str, server_name: str) -> Optional[ServerConfig]:
        """
        Retorna la configuración de un servidor específico.
        
        Args:
            tenant_id: Identificador del tenant
            server_name: Nombre del servidor
            
        Returns:
            ServerConfig si existe, None en caso contrario
        """
        tenant = self.get_tenant(tenant_id)
        if tenant:
            return tenant.servers.get(server_name)
        return None
    
    def get_all_servers(self) -> Dict[str, ServerConfig]:
        """
        Retorna todos los servidores de todos los tenants.
        
        El formato de las llaves es: "tenant_id:server_name"
        
        Returns:
            Diccionario de configuraciones de servidores
        """
        all_servers = {}
        for tenant_id, tenant in self.tenants.items():
            for server_name, server_config in tenant.servers.items():
                key = f"{tenant_id}:{server_name}"
                all_servers[key] = server_config
        return all_servers
    
    def reload(self) -> None:
        """
        Recarga la configuración desde el archivo original.
        
        Raises:
            RuntimeError: Si no se ha cargado configuración previamente
        """
        if self._config_path is None:
            raise RuntimeError("No hay archivo de configuración cargado.")
        
        self._load_from_file(str(self._config_path))
        logger.info("Configuración recargada exitosamente")
    
    def is_modified(self) -> bool:
        """
        Verifica si el archivo de configuración ha sido modificado.
        
        Returns:
            True si el archivo fue modificado desde la última carga
        """
        if self._config_path is None or self._last_modified is None:
            return False
        
        current_mtime = datetime.fromtimestamp(self._config_path.stat().st_mtime)
        return current_mtime > self._last_modified
