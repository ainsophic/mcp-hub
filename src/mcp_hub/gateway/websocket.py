"""
WebSocket Gateway - Gateway para MCP Apps
=========================================

Este módulo implementa el gateway WebSocket para MCP Apps, permitiendo:
- Comunicación bidireccional en tiempo real con MCP Apps
- Proxy de mensajes entre Apps y servidores MCP
- Gestión de conexiones WebSocket múltiples
- Soporte para eventos y notificaciones

Patrones de Diseño Utilizados:
- Observer: Para notificar cambios de estado
- Proxy: Para intermediar comunicación
- Factory: Para crear manejadores de conexión

Autor: Ainsophic Team
"""

import asyncio
import json
import logging
from typing import Dict, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

from fastapi import WebSocket, WebSocketDisconnect


logger = logging.getLogger(__name__)


class MessageType(Enum):
    """
    Tipos de mensajes soportados por el gateway WebSocket.
    """
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    APP_READY = "app_ready"
    APP_STATE = "app_state"
    SERVER_EVENT = "server_event"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"


@dataclass
class WebSocketMessage:
    """
    Mensaje del protocolo WebSocket del gateway.
    
    Atributos:
        type: Tipo del mensaje
        data: Datos del mensaje (JSON-serializable)
        timestamp: Timestamp del mensaje
        message_id: ID único del mensaje (para correlación)
    """
    type: MessageType
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    message_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convierte el mensaje a diccionario para serialización JSON.
        
        Returns:
            Diccionario serializable
        """
        return {
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "message_id": self.message_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WebSocketMessage":
        """
        Crea un mensaje desde un diccionario.
        
        Args:
            data: Diccionario con datos del mensaje
            
        Returns:
            Instancia de WebSocketMessage
        """
        message_type = MessageType(data.get("type"))
        return cls(
            type=message_type,
            data=data.get("data", {}),
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
            message_id=data.get("message_id")
        )


@dataclass
class AppConnection:
    """
    Representación de una conexión de MCP App.
    
    Atributos:
        connection_id: ID único de la conexión
        app_id: ID de la aplicación MCP
        tenant_id: ID del tenant
        websocket: Instancia de WebSocket de FastAPI
        connected_at: Timestamp de conexión
        last_activity: Última actividad
        state: Estado de la aplicación
    """
    connection_id: str
    app_id: str
    tenant_id: str
    websocket: WebSocket
    connected_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    state: Dict[str, Any] = field(default_factory=dict)
    
    def update_activity(self) -> None:
        """Actualiza el timestamp de última actividad."""
        self.last_activity = datetime.now()
    
    async def send_message(self, message: WebSocketMessage) -> None:
        """
        Envía un mensaje a través del WebSocket.
        
        Args:
            message: Mensaje a enviar
        """
        await self.websocket.send_json(message.to_dict())
        self.update_activity()
    
    async def send_data(self, data: Dict[str, Any]) -> None:
        """
        Envía datos JSON a través del WebSocket.
        
        Args:
            data: Datos a enviar
        """
        await self.websocket.send_json(data)
        self.update_activity()
    
    async def send_error(self, error: str, details: Optional[Dict[str, Any]] = None) -> None:
        """
        Envía un mensaje de error.
        
        Args:
            error: Mensaje de error
            details: Detalles adicionales del error
        """
        message = WebSocketMessage(
            type=MessageType.ERROR,
            data={
                "error": error,
                "details": details or {}
            }
        )
        await self.send_message(message)


class MCPAppGateway:
    """
    Gateway WebSocket para MCP Apps.
    
    Esta clase gestiona las conexiones WebSocket de MCP Apps,
    permitiendo comunicación bidireccional en tiempo real entre
    las aplicaciones y los servidores MCP backend.
    
    Funcionalidades:
    - Gestión de múltiples conexiones WebSocket concurrentes
    - Enrutamiento de mensajes entre Apps y servidores MCP
    - Comunicación bidireccional en tiempo real
    - Soporte para eventos y notificaciones
    - Heartbeat para detectar conexiones muertas
    
    Flujo de Comunicación:
    1. MCP App → Gateway → Servidor MCP (llamada a herramienta)
    2. Servidor MCP → Gateway → MCP App (resultado de herramienta)
    3. Eventos del servidor → Gateway → MCP App (notificaciones)
    
    Ejemplo de uso:
        >>> gateway = MCPAppGateway(orchestrator, router, multitenant_manager)
        >>> await gateway.handle_websocket(websocket, "myapp", "default")
    """
    
    def __init__(self, orchestrator, router, multitenant_manager):
        """
        Inicializa el gateway WebSocket.
        
        Args:
            orchestrator: Instancia del Orchestrator
            router: Instancia del Router dinámico
            multitenant_manager: Instancia del MultitenantManager
        """
        self.orchestrator = orchestrator
        self.router = router
        self.multitenant_manager = multitenant_manager
        
        self.connections: Dict[str, AppConnection] = {}
        self._connection_counter = 0
        
        # Observadores de eventos
        self._event_observers: List[Callable] = []
        
        logger.info("MCPAppGateway inicializado")
    
    def _generate_connection_id(self, app_id: str, tenant_id: str) -> str:
        """
        Genera un ID único para una conexión.
        
        Args:
            app_id: ID de la aplicación
            tenant_id: ID del tenant
            
        Returns:
            ID único de conexión
        """
        self._connection_counter += 1
        return f"{tenant_id}:{app_id}:{self._connection_counter}"
    
    def add_event_observer(self, callback: Callable) -> None:
        """
        Registra un observador de eventos del gateway.
        
        Args:
            callback: Función a llamar cuando ocurra un evento
        """
        self._event_observers.append(callback)
        logger.debug(f"Observador de eventos registrado: {callback.__name__}")
    
    def remove_event_observer(self, callback: Callable) -> None:
        """
        Elimina un observador de eventos.
        
        Args:
            callback: Función a eliminar
        """
        if callback in self._event_observers:
            self._event_observers.remove(callback)
            logger.debug(f"Observador de eventos eliminado: {callback.__name__}")
    
    def _notify_observers(self, event: str, data: Any) -> None:
        """
        Notifica a todos los observadores sobre un evento.
        
        Args:
            event: Tipo de evento
            data: Datos del evento
        """
        for observer in self._event_observers:
            try:
                observer(event, data)
            except Exception as e:
                logger.error(f"Error en observador {observer.__name__}: {e}")
    
    async def handle_websocket(
        self,
        websocket: WebSocket,
        app_id: str,
        tenant_id: str
    ) -> None:
        """
        Maneja una conexión WebSocket entrante.
        
        Este método:
        1. Acepta la conexión WebSocket
        2. Crea un objeto AppConnection
        3. Inicia el loop de procesamiento de mensajes
        4. Maneja desconexiones
        
        Args:
            websocket: Instancia de WebSocket de FastAPI
            app_id: ID de la aplicación MCP
            tenant_id: ID del tenant
        """
        # Aceptar conexión WebSocket
        await websocket.accept()
        
        # Crear conexión
        connection_id = self._generate_connection_id(app_id, tenant_id)
        connection = AppConnection(
            connection_id=connection_id,
            app_id=app_id,
            tenant_id=tenant_id,
            websocket=websocket
        )
        
        self.connections[connection_id] = connection
        logger.info(f"Conexión WebSocket aceptada: {connection_id}")
        self._notify_observers("connection_opened", {
            "connection_id": connection_id,
            "app_id": app_id,
            "tenant_id": tenant_id
        })
        
        try:
            # Enviar estado inicial
            await self._send_initial_state(connection)
            
            # Loop de procesamiento de mensajes
            while True:
                # Recibir mensaje
                data = await websocket.receive_json()
                message = WebSocketMessage.from_dict(data)
                
                # Actualizar actividad
                connection.update_activity()
                
                # Procesar mensaje según tipo
                await self._handle_message(connection, message)
                
        except WebSocketDisconnect:
            logger.info(f"Conexión WebSocket cerrada: {connection_id}")
        except Exception as e:
            logger.error(f"Error en conexión WebSocket {connection_id}: {e}")
            await connection.send_error(str(e))
        finally:
            # Limpiar conexión
            await self._cleanup_connection(connection_id)
    
    async def _send_initial_state(self, connection: AppConnection) -> None:
        """
        Envía el estado inicial a una conexión recién establecida.
        
        Args:
            connection: Conexión de la App
        """
        # Obtener herramientas disponibles para el tenant
        tools = self.multitenant_manager.get_tenant_tools(connection.tenant_id)
        
        # Obtener estado de servidores
        tenant_status = self.multitenant_manager.get_tenant_status(connection.tenant_id)
        
        state_message = WebSocketMessage(
            type=MessageType.APP_STATE,
            data={
                "app_id": connection.app_id,
                "tenant_id": connection.tenant_id,
                "available_tools": tools,
                "servers_status": tenant_status
            }
        )
        
        await connection.send_message(state_message)
    
    async def _handle_message(
        self,
        connection: AppConnection,
        message: WebSocketMessage
    ) -> None:
        """
        Maneja un mensaje recibido de una App.
        
        Args:
            connection: Conexión de la App
            message: Mensaje recibido
        """
        try:
            if message.type == MessageType.TOOL_CALL:
                await self._handle_tool_call(connection, message)
            elif message.type == MessageType.APP_READY:
                await self._handle_app_ready(connection, message)
            elif message.type == MessageType.PING:
                await self._handle_ping(connection)
            else:
                logger.warning(f"Tipo de mensaje desconocido: {message.type}")
                await connection.send_error(
                    f"Tipo de mensaje desconocido: {message.type.value}"
                )
                
        except Exception as e:
            logger.error(f"Error manejando mensaje: {e}")
            await connection.send_error(str(e))
    
    async def _handle_tool_call(
        self,
        connection: AppConnection,
        message: WebSocketMessage
    ) -> None:
        """
        Maneja una llamada a herramienta desde una App.
        
        Args:
            connection: Conexión de la App
            message: Mensaje con la llamada a herramienta
        """
        tool_name = message.data.get("tool_name")
        arguments = message.data.get("arguments", {})
        
        if not tool_name:
            await connection.send_error("Falta el nombre de la herramienta")
            return
        
        try:
            # Ejecutar herramienta a través del router
            result = await self.router.call_tool(tool_name, arguments)
            
            # Enviar resultado
            result_message = WebSocketMessage(
                type=MessageType.TOOL_RESULT,
                data={
                    "tool_name": tool_name,
                    "result": result,
                    "correlation_id": message.message_id
                }
            )
            
            await connection.send_message(result_message)
            
        except Exception as e:
            logger.error(f"Error ejecutando herramienta {tool_name}: {e}")
            
            # Enviar error
            error_message = WebSocketMessage(
                type=MessageType.TOOL_ERROR,
                data={
                    "tool_name": tool_name,
                    "error": str(e),
                    "correlation_id": message.message_id
                }
            )
            
            await connection.send_message(error_message)
    
    async def _handle_app_ready(
        self,
        connection: AppConnection,
        message: WebSocketMessage
    ) -> None:
        """
        Maneja el mensaje de que la App está lista.
        
        Args:
            connection: Conexión de la App
            message: Mensaje de ready
        """
        logger.info(f"App lista: {connection.app_id} (tenant: {connection.tenant_id})")
        
        # Actualizar estado de la conexión
        connection.state["ready"] = True
        connection.state["ready_at"] = datetime.now().isoformat()
        
        # Reenviar estado actualizado
        await self._send_initial_state(connection)
    
    async def _handle_ping(self, connection: AppConnection) -> None:
        """
        Maneja un mensaje PING.
        
        Args:
            connection: Conexión de la App
        """
        pong_message = WebSocketMessage(type=MessageType.PONG, data={})
        await connection.send_message(pong_message)
    
    async def _cleanup_connection(self, connection_id: str) -> None:
        """
        Limpia una conexión WebSocket.
        
        Args:
            connection_id: ID de la conexión a limpiar
        """
        if connection_id in self.connections:
            connection = self.connections[connection_id]
            logger.info(f"Limpiando conexión: {connection_id}")
            
            del self.connections[connection_id]
            self._notify_observers("connection_closed", {
                "connection_id": connection_id,
                "app_id": connection.app_id,
                "tenant_id": connection.tenant_id
            })
    
    def get_connection(self, connection_id: str) -> Optional[AppConnection]:
        """
        Obtiene una conexión por su ID.
        
        Args:
            connection_id: ID de la conexión
            
        Returns:
            AppConnection si existe, None en caso contrario
        """
        return self.connections.get(connection_id)
    
    def get_connections_by_app(self, app_id: str) -> List[AppConnection]:
        """
        Obtiene todas las conexiones de una App específica.
        
        Args:
            app_id: ID de la aplicación
            
        Returns:
            Lista de conexiones de la App
        """
        return [
            conn for conn in self.connections.values()
            if conn.app_id == app_id
        ]
    
    def get_connections_by_tenant(self, tenant_id: str) -> List[AppConnection]:
        """
        Obtiene todas las conexiones de un tenant específico.
        
        Args:
            tenant_id: ID del tenant
            
        Returns:
            Lista de conexiones del tenant
        """
        return [
            conn for conn in self.connections.values()
            if conn.tenant_id == tenant_id
        ]
    
    def get_all_connections(self) -> List[AppConnection]:
        """
        Obtiene todas las conexiones activas.
        
        Returns:
            Lista de todas las conexiones
        """
        return list(self.connections.values())
    
    async def broadcast_to_app(
        self,
        app_id: str,
        message: WebSocketMessage
    ) -> int:
        """
        Envía un mensaje a todas las conexiones de una App.
        
        Args:
            app_id: ID de la aplicación
            message: Mensaje a enviar
            
        Returns:
            Número de conexiones a las que se envió
        """
        connections = self.get_connections_by_app(app_id)
        
        for connection in connections:
            try:
                await connection.send_message(message)
            except Exception as e:
                logger.error(f"Error enviando a conexión {connection.connection_id}: {e}")
        
        return len(connections)
    
    async def broadcast_to_tenant(
        self,
        tenant_id: str,
        message: WebSocketMessage
    ) -> int:
        """
        Envía un mensaje a todas las conexiones de un tenant.
        
        Args:
            tenant_id: ID del tenant
            message: Mensaje a enviar
            
        Returns:
            Número de conexiones a las que se envió
        """
        connections = self.get_connections_by_tenant(tenant_id)
        
        for connection in connections:
            try:
                await connection.send_message(message)
            except Exception as e:
                logger.error(f"Error enviando a conexión {connection.connection_id}: {e}")
        
        return len(connections)
    
    async def broadcast_to_all(self, message: WebSocketMessage) -> int:
        """
        Envía un mensaje a todas las conexiones.
        
        Args:
            message: Mensaje a enviar
            
        Returns:
            Número de conexiones a las que se envió
        """
        for connection in self.connections.values():
            try:
                await connection.send_message(message)
            except Exception as e:
                logger.error(f"Error enviando a conexión {connection.connection_id}: {e}")
        
        return len(self.connections)
    
    def get_gateway_status(self) -> Dict[str, Any]:
        """
        Retorna el estado actual del gateway.
        
        Returns:
            Diccionario con estadísticas del gateway
        """
        connections_by_tenant: Dict[str, int] = {}
        connections_by_app: Dict[str, int] = {}
        
        for connection in self.connections.values():
            connections_by_tenant[connection.tenant_id] = \
                connections_by_tenant.get(connection.tenant_id, 0) + 1
            connections_by_app[connection.app_id] = \
                connections_by_app.get(connection.app_id, 0) + 1
        
        return {
            "total_connections": len(self.connections),
            "connections_by_tenant": connections_by_tenant,
            "connections_by_app": connections_by_app,
            "uptime": "N/A"  # Se puede implementar con un timestamp de inicio
        }
