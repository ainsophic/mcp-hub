"""
Multitenant Manager - Gestión Multitenant con Aislamiento de Namespaces
=========================================================================

Este módulo implementa el sistema multitenant del MCP Hub, permitiendo:
- Aislamiento de configuraciones y recursos por tenant
- Namespaces para herramientas y servidores
- Gestión de cuotas y límites por tenant
- Permisos y control de acceso

Patrones de Diseño Utilizados:
- Namespace: Para aislar recursos por tenant
- Facade: Para simplificar la interacción con múltiples componentes

Autor: Ainsophic Team
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

from mcp_hub.core.registry import Registry, TenantConfig, ServerConfig
from mcp_hub.core.orchestrator import Orchestrator, ManagedServer, ServerState
from mcp_hub.core.router import DynamicToolRouter


logger = logging.getLogger(__name__)


@dataclass
class TenantContext:
    """
    Contexto de ejecución para un tenant específico.
    
    Este contexto encapsula toda la información y recursos
    asociados con un tenant, proporcionando aislamiento completo.
    
    Atributos:
        tenant_id: Identificador único del tenant
        config: Configuración del tenant desde el Registry
        servers: Diccionario de servidores gestionados
        tools: Lista de herramientas disponibles (con prefijos)
        metrics: Métricas de uso del tenant
        created_at: Timestamp de creación del contexto
        last_activity: Última actividad del tenant
    """
    tenant_id: str
    config: TenantConfig
    servers: Dict[str, ManagedServer] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    
    def update_activity(self) -> None:
        """Actualiza el timestamp de última actividad."""
        self.last_activity = datetime.now()
    
    def get_active_servers(self) -> List[ManagedServer]:
        """
        Retorna los servidores activos del tenant.
        
        Returns:
            Lista de servidores en estado RUNNING
        """
        return [
            server for server in self.servers.values()
            if server.is_running()
        ]
    
    def is_active(self) -> bool:
        """
        Indica si el tenant tiene servidores activos.
        
        Returns:
            True si tiene al menos un servidor activo
        """
        return len(self.get_active_servers()) > 0


class TenantNotFoundError(Exception):
    """Excepción levantada cuando no se encuentra un tenant."""
    pass


class QuotaExceededError(Exception):
    """Excepción levantada cuando se excede una cuota del tenant."""
    pass


class MultitenantManager:
    """
    Gestor multitenant para el MCP Hub.
    
    Esta clase proporciona aislamiento completo entre diferentes tenants
    (inquilinos), permitiendo que múltiples organizaciones o proyectos
    usen el mismo Hub sin interferir entre sí.
    
    Funcionalidades:
    - Aislamiento de configuraciones y recursos por tenant
    - Namespaces para herramientas (ej: "postgres.query")
    - Gestión de cuotas y límites por tenant
    - Segregación de credenciales y configuraciones
    - Métricas de uso por tenant
    
    Estrategia de Aislamiento:
    Cada tenant tiene su propio namespace para:
    - Servidores: Identificados como "tenant_id:server_name"
    - Herramientas: Prefijadas como "server_name.tool_name"
    - Credenciales: Variables de entorno por tenant
    - Recursos: Aislamiento completo de datos
    
    Ejemplo de uso:
        >>> manager = MultitenantManager(registry, orchestrator, router)
        >>> context = manager.get_or_create_tenant("default")
        >>> await manager.start_tenant_servers("default")
        >>> tools = manager.get_tenant_tools("default")
    """
    
    def __init__(
        self,
        registry: Registry,
        orchestrator: Orchestrator,
        router: DynamicToolRouter
    ):
        """
        Inicializa el gestor multitenant.
        
        Args:
            registry: Instancia del Registry
            orchestrator: Instancia del Orchestrator
            router: Instancia del Router dinámico
        """
        self.registry = registry
        self.orchestrator = orchestrator
        self.router = router
        self.tenants: Dict[str, TenantContext] = {}
        
        # Configuración de cuotas por defecto
        self.default_quotas = {
            "max_servers": 10,
            "max_tools_per_server": 100,
            "max_concurrent_requests": 50
        }
        
        # Cuotas personalizadas por tenant
        self.quotas: Dict[str, Dict[str, int]] = {}
        
        logger.info("MultitenantManager inicializado")
    
    def set_quota(self, tenant_id: str, quota_type: str, limit: int) -> None:
        """
        Establece una cuota específica para un tenant.
        
        Args:
            tenant_id: ID del tenant
            quota_type: Tipo de cuota (max_servers, max_tools_per_server, etc.)
            limit: Límite de la cuota
        """
        if tenant_id not in self.quotas:
            self.quotas[tenant_id] = {}
        
        self.quotas[tenant_id][quota_type] = limit
        logger.info(
            f"Cuota establecida para tenant {tenant_id}: "
            f"{quota_type}={limit}"
        )
    
    def get_quota(self, tenant_id: str, quota_type: str) -> int:
        """
        Retorna el límite de una cuota para un tenant.
        
        Args:
            tenant_id: ID del tenant
            quota_type: Tipo de cuota
            
        Returns:
            Límite de la cuota
        """
        if tenant_id in self.quotas and quota_type in self.quotas[tenant_id]:
            return self.quotas[tenant_id][quota_type]
        
        return self.default_quotas.get(quota_type, float('inf'))
    
    def check_quota(self, tenant_id: str, quota_type: str) -> bool:
        """
        Verifica si un tenant ha excedido su cuota.
        
        Args:
            tenant_id: ID del tenant
            quota_type: Tipo de cuota
            
        Returns:
            True si no se ha excedido la cuota, False en caso contrario
            
        Raises:
            QuotaExceededError: Si se ha excedido la cuota
        """
        context = self.tenants.get(tenant_id)
        if not context:
            return True
        
        limit = self.get_quota(tenant_id, quota_type)
        
        if quota_type == "max_servers":
            current = len(context.servers)
            if current >= limit:
                raise QuotaExceededError(
                    f"Tenant {tenant_id} ha excedido su cuota de servidores "
                    f"({current}/{limit})"
                )
        
        elif quota_type == "max_tools_per_server":
            for server_id, server in context.servers.items():
                tools = len(self.router.get_tools_by_server(server_id))
                if tools > limit:
                    raise QuotaExceededError(
                        f"Tenant {tenant_id}: servidor {server_id} "
                        f"ha excedido su cuota de herramientas "
                        f"({tools}/{limit})"
                    )
        
        return True
    
    def get_or_create_tenant(self, tenant_id: str) -> TenantContext:
        """
        Obtiene o crea el contexto de un tenant.
        
        Args:
            tenant_id: ID del tenant
            
        Returns:
            TenantContext del tenant
            
        Raises:
            TenantNotFoundError: Si el tenant no existe en el Registry
        """
        if tenant_id in self.tenants:
            context = self.tenants[tenant_id]
            context.update_activity()
            return context
        
        # Verificar que el tenant existe en el Registry
        config = self.registry.get_tenant(tenant_id)
        if not config:
            raise TenantNotFoundError(f"Tenant no encontrado: {tenant_id}")
        
        # Crear contexto del tenant
        context = TenantContext(
            tenant_id=tenant_id,
            config=config
        )
        
        self.tenants[tenant_id] = context
        logger.info(f"Contexto de tenant creado: {tenant_id}")
        
        return context
    
    def get_tenant(self, tenant_id: str) -> Optional[TenantContext]:
        """
        Obtiene el contexto de un tenant existente.
        
        Args:
            tenant_id: ID del tenant
            
        Returns:
            TenantContext si existe, None en caso contrario
        """
        return self.tenants.get(tenant_id)
    
    async def start_tenant_servers(self, tenant_id: str) -> List[ManagedServer]:
        """
        Inicia todos los servidores habilitados de un tenant.
        
        Este método:
        1. Verifica las cuotas del tenant
        2. Inicia los servidores configurados
        3. Registra las herramientas en el router
        4. Actualiza el contexto del tenant
        
        Args:
            tenant_id: ID del tenant
            
        Returns:
            Lista de servidores iniciados
        """
        logger.info(f"Iniciando servidores del tenant: {tenant_id}")
        
        # Obtener o crear contexto del tenant
        context = self.get_or_create_tenant(tenant_id)
        
        # Verificar cuota de servidores
        self.check_quota(tenant_id, "max_servers")
        
        # Iniciar servidores usando el Orchestrator
        started_servers = await self.orchestrator.start_tenant_servers(tenant_id)
        
        # Actualizar contexto del tenant
        for server in started_servers:
            context.servers[server.server_id] = server
        
        # Descubrir y registrar herramientas
        for server in started_servers:
            try:
                await self.router.discover_tools(server.server_id)
            except Exception as e:
                logger.error(
                    f"Error descubriendo herramientas de {server.server_id}: {e}"
                )
        
        # Actualizar lista de herramientas del tenant
        context.tools = [
            reg.prefixed_name
            for server in started_servers
            for reg in self.router.get_tools_by_server(server.server_id)
        ]
        
        context.update_activity()
        logger.info(
            f"Servidores iniciados para tenant {tenant_id}: {len(started_servers)}"
        )
        
        return started_servers
    
    async def stop_tenant_servers(self, tenant_id: str) -> None:
        """
        Detiene todos los servidores de un tenant.
        
        Args:
            tenant_id: ID del tenant
        """
        logger.info(f"Deteniendo servidores del tenant: {tenant_id}")
        
        # Detener servidores usando el Orchestrator
        await self.orchestrator.stop_tenant_servers(tenant_id)
        
        # Actualizar contexto del tenant
        if tenant_id in self.tenants:
            context = self.tenants[tenant_id]
            
            # Limpiar herramientas del router
            for server_id in context.servers.keys():
                self.router.clear_tools(server_id)
            
            # Limpiar servidores del contexto
            context.servers.clear()
            context.tools.clear()
            context.update_activity()
        
        logger.info(f"Servidores detenidos para tenant: {tenant_id}")
    
    def get_tenant_tools(self, tenant_id: str) -> List[str]:
        """
        Retorna las herramientas disponibles para un tenant.
        
        Args:
            tenant_id: ID del tenant
            
        Returns:
            Lista de nombres de herramientas prefijadas
        """
        context = self.get_tenant(tenant_id)
        if not context:
            return []
        
        return context.tools.copy()
    
    def get_tenant_tools_summary(self, tenant_id: str) -> Dict[str, Any]:
        """
        Retorna un resumen de las herramientas de un tenant.
        
        Args:
            tenant_id: ID del tenant
            
        Returns:
            Diccionario con resumen de herramientas
        """
        context = self.get_tenant(tenant_id)
        if not context:
            return {
                "tenant_id": tenant_id,
                "exists": False,
                "tools": []
            }
        
        # Agrupar herramientas por servidor
        tools_by_server: Dict[str, List[str]] = {}
        for server in context.servers.values():
            tools_by_server[server.config.name] = [
                reg.prefixed_name
                for reg in self.router.get_tools_by_server(server.server_id)
            ]
        
        return {
            "tenant_id": tenant_id,
            "exists": True,
            "total_tools": len(context.tools),
            "active_servers": len(context.get_active_servers()),
            "tools_by_server": tools_by_server,
            "all_tools": sorted(context.tools)
        }
    
    def get_tenant_status(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """
        Retorna el estado completo de un tenant.
        
        Args:
            tenant_id: ID del tenant
            
        Returns:
            Diccionario con estado del tenant o None si no existe
        """
        context = self.get_tenant(tenant_id)
        if not context:
            return None
        
        return {
            "tenant_id": context.tenant_id,
            "is_active": context.is_active(),
            "total_servers": len(context.servers),
            "active_servers": len(context.get_active_servers()),
            "total_tools": len(context.tools),
            "created_at": context.created_at.isoformat(),
            "last_activity": context.last_activity.isoformat(),
            "servers": [
                {
                    "server_id": server.server_id,
                    "name": server.config.name,
                    "type": server.config.type,
                    "state": server.state.name
                }
                for server in context.servers.values()
            ]
        }
    
    def get_all_tenants_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Retorna el estado de todos los tenants.
        
        Returns:
            Diccionario con estado de cada tenant
        """
        return {
            tenant_id: self.get_tenant_status(tenant_id)
            for tenant_id in self.tenants.keys()
        }
    
    async def cleanup_inactive_tenants(self, idle_timeout: int = 3600) -> List[str]:
        """
        Limpia tenants inactivos.
        
        Args:
            idle_timeout: Tiempo de inactividad en segundos antes de limpiar
            
        Returns:
            Lista de IDs de tenants limpiados
        """
        now = datetime.now()
        cleaned_tenants = []
        
        for tenant_id, context in self.tenants.items():
            idle_seconds = (now - context.last_activity).total_seconds()
            
            if idle_seconds > idle_timeout and not context.is_active():
                logger.info(
                    f"Tenant inactivo limpiado: {tenant_id} "
                    f"(inactivo por {idle_seconds}s)"
                )
                await self.stop_tenant_servers(tenant_id)
                del self.tenants[tenant_id]
                cleaned_tenants.append(tenant_id)
        
        return cleaned_tenants
    
    def get_tenant_metrics(self, tenant_id: str) -> Dict[str, Any]:
        """
        Retorna las métricas de uso de un tenant.
        
        Args:
            tenant_id: ID del tenant
            
        Returns:
            Diccionario con métricas del tenant
        """
        context = self.get_tenant(tenant_id)
        if not context:
            return {}
        
        uptime = (datetime.now() - context.created_at).total_seconds()
        
        return {
            "tenant_id": tenant_id,
            "uptime_seconds": uptime,
            "uptime_hours": uptime / 3600,
            "servers": {
                "total": len(context.servers),
                "active": len(context.get_active_servers())
            },
            "tools": {
                "total": len(context.tools)
            },
            "last_activity": context.last_activity.isoformat()
        }
