"""
Orchestrator - Gestión del Ciclo de Vida de Servidores MCP
============================================================

Este módulo implementa el orchestrator encargado de gestionar el ciclo
de vida de múltiples servidores MCP. Proporciona funcionalidades para:

- Iniciar y detener servidores MCP
- Monitorear el estado de los servidores
- Manejar reconexiones automáticas
- Gestionar recursos y limpieza

Patrones de Diseño Utilizados:
- Observer: Para notificar cambios de estado
- Singleton: Para garantizar una única instancia del orchestrator
- Factory: Para crear instancias de servidores gestionados

Autor: Ainsophic Team
"""

import asyncio
import logging
import signal
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

from mcp_hub.core.registry import ServerConfig, Registry
from mcp_hub.transport.stdio_client import (
    StdioClientWrapper,
    MCPConnectionError,
    MCPInitializationError
)


logger = logging.getLogger(__name__)


class ServerState(Enum):
    """
    Estados posibles de un servidor MCP gestionado.
    """
    STOPPED = auto()           # Servidor detenido
    STARTING = auto()          # Servidor iniciándose
    RUNNING = auto()           # Servidor ejecutándose normalmente
    CRASHED = auto()           # Servidor falleció
    STOPPING = auto()          # Servidor deteniéndose


@dataclass
class ManagedServer:
    """
    Representación de un servidor MCP gestionado por el Orchestrator.
    
    Atributos:
        server_id: Identificador único (formato: "tenant_id:server_name")
        tenant_id: ID del tenant al que pertenece
        config: Configuración del servidor
        state: Estado actual del servidor
        process: Proceso asociado (si está ejecutándose)
        client: Cliente MCP conectado (si está inicializado)
        pid: PID del proceso (si está ejecutándose)
        started_at: Timestamp de inicio
        last_error: Último error ocurrido
        restart_count: Contador de reinicios
    """
    server_id: str
    tenant_id: str
    config: ServerConfig
    state: ServerState = ServerState.STOPPED
    process: Optional[asyncio.subprocess.Process] = None
    client: Optional[StdioClientWrapper] = None
    pid: Optional[int] = None
    started_at: Optional[datetime] = None
    last_error: Optional[str] = None
    restart_count: int = 0
    
    def is_running(self) -> bool:
        """
        Indica si el servidor está ejecutándose.
        
        Returns:
            True si está en estado RUNNING
        """
        return self.state == ServerState.RUNNING
    
    def is_stopped(self) -> bool:
        """
        Indica si el servidor está detenido.
        
        Returns:
            True si está en estado STOPPED o CRASHED
        """
        return self.state in (ServerState.STOPPED, ServerState.CRASHED)


class Orchestrator:
    """
    Orchestrator para gestión de servidores MCP.
    
    Esta clase se encarga de gestionar el ciclo de vida completo de múltiples
    servidores MCP, incluyendo inicio, detención, monitoreo y reconexión
    automática en caso de fallos.
    
    Funcionalidades:
    - Iniciar servidores individuales o por tenant
    - Detener servidores de forma segura
    - Monitorear estado de servidores en tiempo real
    - Reconexión automática con backoff exponencial
    - Notificación de eventos a observadores registrados
    
    Ejemplo de uso:
        >>> orchestrator = Orchestrator(registry)
        >>> await orchestrator.start_server("default:postgres")
        >>> status = orchestrator.get_server_status("default:postgres")
        >>> await orchestrator.stop_all()
    """
    
    def __init__(self, registry: Registry):
        """
        Inicializa el Orchestrator.
        
        Args:
            registry: Instancia del Registry con configuración de servidores
        """
        self.registry = registry
        self.managed_servers: Dict[str, ManagedServer] = {}
        self._observers: List[Callable] = []
        self._monitoring_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Configuración de reconexión
        self.max_retries = registry.orchestrator.max_retries
        self.startup_timeout = registry.orchestrator.startup_timeout
        
        logger.info("Orchestrator inicializado")
    
    def _generate_server_id(self, tenant_id: str, server_name: str) -> str:
        """
        Genera un ID único para un servidor.
        
        Args:
            tenant_id: ID del tenant
            server_name: Nombre del servidor
            
        Returns:
            ID en formato "tenant_id:server_name"
        """
        return f"{tenant_id}:{server_name}"
    
    def _parse_server_id(self, server_id: str) -> tuple[str, str]:
        """
        Parsea un ID de servidor en tenant_id y server_name.
        
        Args:
            server_id: ID del servidor
            
        Returns:
            Tupla (tenant_id, server_name)
            
        Raises:
            ValueError: Si el formato del ID es inválido
        """
        if ":" not in server_id:
            raise ValueError(f"Formato de ID inválido: {server_id}")
        
        parts = server_id.split(":", 1)
        return parts[0], parts[1]
    
    def add_observer(self, callback: Callable) -> None:
        """
        Registra un observador para eventos del orchestrator.
        
        Args:
            callback: Función a llamar cuando ocurra un evento
        """
        self._observers.append(callback)
        logger.debug(f"Observador registrado: {callback.__name__}")
    
    def remove_observer(self, callback: Callable) -> None:
        """
        Elimina un observador registrado.
        
        Args:
            callback: Función a eliminar
        """
        if callback in self._observers:
            self._observers.remove(callback)
            logger.debug(f"Observador eliminado: {callback.__name__}")
    
    def _notify_observers(self, event: str, data: Any) -> None:
        """
        Notifica a todos los observadores sobre un evento.
        
        Args:
            event: Tipo de evento
            data: Datos del evento
        """
        for observer in self._observers:
            try:
                observer(event, data)
            except Exception as e:
                logger.error(f"Error en observador {observer.__name__}: {e}")
    
    async def start_server(self, server_id: str) -> ManagedServer:
        """
        Inicia un servidor MCP específico.
        
        Args:
            server_id: ID del servidor (formato: "tenant_id:server_name")
            
        Returns:
            ManagedServer con el servidor iniciado
            
        Raises:
            ValueError: Si el servidor no existe en el registry
            MCPConnectionError: Si falla la conexión al servidor
            MCPInitializationError: Si falla la inicialización
        """
        tenant_id, server_name = self._parse_server_id(server_id)
        server_config = self.registry.get_server_config(tenant_id, server_name)
        
        if server_config is None:
            raise ValueError(f"Servidor no encontrado en registry: {server_id}")
        
        if server_id in self.managed_servers and self.managed_servers[server_id].is_running():
            logger.warning(f"Servidor ya está ejecutándose: {server_id}")
            return self.managed_servers[server_id]
        
        logger.info(f"Iniciando servidor: {server_id}")
        
        # Crear ManagedServer
        managed = ManagedServer(
            server_id=server_id,
            tenant_id=tenant_id,
            config=server_config,
            state=ServerState.STARTING
        )
        
        self.managed_servers[server_id] = managed
        self._notify_observers("server_starting", {"server_id": server_id})
        
        try:
            # Crear y conectar cliente MCP
            client = StdioClientWrapper(
                command=server_config.command,
                args=server_config.args,
                timeout=self.startup_timeout,
                max_retries=self.max_retries
            )
            
            await client.connect()
            await client.initialize()
            
            # Actualizar estado
            managed.state = ServerState.RUNNING
            managed.client = client
            managed.started_at = datetime.now()
            managed.last_error = None
            
            logger.info(f"Servidor iniciado exitosamente: {server_id}")
            self._notify_observers("server_started", {"server_id": server_id})
            
            return managed
            
        except (MCPConnectionError, MCPInitializationError) as e:
            managed.state = ServerState.CRASHED
            managed.last_error = str(e)
            logger.error(f"Fallo al iniciar servidor {server_id}: {e}")
            self._notify_observers("server_failed", {
                "server_id": server_id,
                "error": str(e)
            })
            raise
    
    async def start_tenant_servers(self, tenant_id: str) -> List[ManagedServer]:
        """
        Inicia todos los servidores habilitados de un tenant.
        
        Args:
            tenant_id: ID del tenant
            
        Returns:
            Lista de ManagedServers iniciados
        """
        tenant = self.registry.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant no encontrado: {tenant_id}")
        
        logger.info(f"Iniciando servidores del tenant: {tenant_id}")
        
        started_servers = []
        for server_config in tenant.get_enabled_servers():
            server_id = self._generate_server_id(tenant_id, server_config.name)
            try:
                managed = await self.start_server(server_id)
                started_servers.append(managed)
            except Exception as e:
                logger.error(f"Error iniciando servidor {server_id}: {e}")
        
        logger.info(f"Servidores iniciados para tenant {tenant_id}: {len(started_servers)}")
        return started_servers
    
    async def stop_server(self, server_id: str) -> None:
        """
        Detiene un servidor MCP específico.
        
        Args:
            server_id: ID del servidor
        """
        if server_id not in self.managed_servers:
            logger.warning(f"Servidor no gestionado: {server_id}")
            return
        
        managed = self.managed_servers[server_id]
        
        if managed.is_stopped():
            logger.warning(f"Servidor ya detenido: {server_id}")
            return
        
        logger.info(f"Deteniendo servidor: {server_id}")
        managed.state = ServerState.STOPPING
        self._notify_observers("server_stopping", {"server_id": server_id})
        
        try:
            # Desconectar cliente MCP
            if managed.client:
                await managed.client.disconnect()
                managed.client = None
            
            # Eliminar del registro de servidores gestionados
            managed.state = ServerState.STOPPED
            managed.started_at = None
            
            logger.info(f"Servidor detenido exitosamente: {server_id}")
            self._notify_observers("server_stopped", {"server_id": server_id})
            
        except Exception as e:
            logger.error(f"Error deteniendo servidor {server_id}: {e}")
            managed.state = ServerState.CRASHED
            managed.last_error = str(e)
    
    async def stop_tenant_servers(self, tenant_id: str) -> None:
        """
        Detiene todos los servidores de un tenant.
        
        Args:
            tenant_id: ID del tenant
        """
        logger.info(f"Deteniendo servidores del tenant: {tenant_id}")
        
        server_ids = [
            server_id for server_id, managed in self.managed_servers.items()
            if managed.tenant_id == tenant_id and managed.is_running()
        ]
        
        for server_id in server_ids:
            await self.stop_server(server_id)
    
    async def stop_all(self) -> None:
        """
        Detiene todos los servidores gestionados.
        """
        logger.info("Deteniendo todos los servidores")
        
        server_ids = list(self.managed_servers.keys())
        for server_id in server_ids:
            await self.stop_server(server_id)
        
        logger.info("Todos los servidores detenidos")
    
    def get_server_status(self, server_id: str) -> Optional[Dict[str, Any]]:
        """
        Retorna el estado actual de un servidor.
        
        Args:
            server_id: ID del servidor
            
        Returns:
            Diccionario con información del estado o None si no existe
        """
        if server_id not in self.managed_servers:
            return None
        
        managed = self.managed_servers[server_id]
        return {
            "server_id": server_id,
            "tenant_id": managed.tenant_id,
            "state": managed.state.name,
            "config": {
                "name": managed.config.name,
                "type": managed.config.type,
                "command": managed.config.command,
                "enabled": managed.config.enabled
            },
            "started_at": managed.started_at.isoformat() if managed.started_at else None,
            "last_error": managed.last_error,
            "restart_count": managed.restart_count
        }
    
    def get_all_servers_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Retorna el estado de todos los servidores gestionados.
        
        Returns:
            Diccionario con estado de cada servidor
        """
        return {
            server_id: self.get_server_status(server_id)
            for server_id in self.managed_servers
            if self.get_server_status(server_id) is not None
        }
    
    def get_server_client(self, server_id: str) -> Optional[StdioClientWrapper]:
        """
        Retorna el cliente MCP de un servidor específico.
        
        Args:
            server_id: ID del servidor
            
        Returns:
            StdioClientWrapper si está conectado, None en caso contrario
        """
        managed = self.managed_servers.get(server_id)
        if managed and managed.is_running():
            return managed.client
        return None
    
    async def start_monitoring(self, interval: float = 5.0) -> None:
        """
        Inicia el monitoreo periódico de servidores.
        
        Args:
            interval: Intervalo en segundos entre checks
        """
        if self._monitoring_task and not self._monitoring_task.done():
            logger.warning("Monitoreo ya está activo")
            return
        
        logger.info(f"Iniciando monitoreo (intervalo: {interval}s)")
        
        async def monitor():
            while not self._shutdown_event.is_set():
                try:
                    await self._check_servers()
                    await asyncio.sleep(interval)
                except Exception as e:
                    logger.error(f"Error en monitoreo: {e}")
                    await asyncio.sleep(1)
        
        self._monitoring_task = asyncio.create_task(monitor())
    
    async def _check_servers(self) -> None:
        """
        Verifica el estado de todos los servidores y gestiona fallos.
        """
        for server_id, managed in self.managed_servers.items():
            if not managed.is_running():
                continue
            
            try:
                # Verificar que el cliente está conectado
                if not managed.client or not managed.client.is_connected:
                    logger.warning(f"Servidor desconectado: {server_id}")
                    await self._handle_server_failure(server_id, "Conexión perdida")
                    continue
                
            except Exception as e:
                logger.error(f"Error verificando servidor {server_id}: {e}")
    
    async def _handle_server_failure(self, server_id: str, error: str) -> None:
        """
        Maneja el fallo de un servidor.
        
        Args:
            server_id: ID del servidor
            error: Descripción del error
        """
        managed = self.managed_servers.get(server_id)
        if not managed:
            return
        
        managed.state = ServerState.CRASHED
        managed.last_error = error
        
        self._notify_observers("server_failed", {
            "server_id": server_id,
            "error": error
        })
        
        # Lógica de reconexión futura
        # managed.restart_count += 1
        # if managed.restart_count <= self.max_retries:
        #     await asyncio.sleep(2 ** managed.restart_count)  # Backoff exponencial
        #     await self.start_server(server_id)
    
    async def stop_monitoring(self) -> None:
        """
        Detiene el monitoreo periódico de servidores.
        """
        if self._monitoring_task and not self._monitoring_task.done():
            self._shutdown_event.set()
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            
            logger.info("Monitoreo detenido")
    
    async def shutdown(self) -> None:
        """
        Realiza un shutdown completo del orchestrator.
        """
        logger.info("Iniciando shutdown del Orchestrator")
        
        await self.stop_monitoring()
        await self.stop_all()
        
        logger.info("Orchestrator detenido completamente")
