"""
UI Proxy - Proxy para Recursos Estáticos de MCP Apps
======================================================

Este módulo implementa el proxy para recursos estáticos de MCP Apps,
permitiendo:
- Servir archivos estáticos (HTML, JS, CSS)
- Proxy inverso para endpoints de API
- Inyección de configuración y metadatos
- Caché de recursos estáticos

Patrones de Diseño Utilizados:
- Proxy: Para intermediar solicitudes
- Cache: Para almacenamiento temporal de recursos
- Strategy: Para diferentes estrategias de carga

Autor: Ainsophic Team
"""

import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from fastapi import Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
import aiofiles
import mimetypes


logger = logging.getLogger(__name__)


class UIProxyError(Exception):
    """Excepción base para errores del UI Proxy."""
    pass


class ResourceNotFoundError(UIProxyError):
    """Excepción levantada cuando no se encuentra un recurso."""
    pass


class UIProxy:
    """
    Proxy para recursos estáticos de MCP Apps.
    
    Esta clase sirve como proxy inverso para los recursos estáticos
    de las MCP Apps, permitiendo que las aplicaciones carguen sus
    archivos HTML, JavaScript y CSS a través del Hub.
    
    Funcionalidades:
    - Servir archivos estáticos desde el sistema de archivos local
    - Inyectar configuración y metadatos en archivos HTML
    - Caché de recursos estáticos para mejor rendimiento
    - Detección automática de MIME types
    - Soporte para directorios de plugins
    
    Estructura de Directorios:
    Los recursos de las MCP Apps se organizan en:
    plugins/
        {app_name}/
            ui/
                index.html
                app.js
                styles.css
                ...
    
    Ejemplo de uso:
        >>> proxy = UIProxy(plugins_dir="plugins")
        >>> response = await proxy.serve_resource("myapp", "ui/index.html")
        >>> response = await proxy.serve_app_index("myapp", tenant_id="default")
    """
    
    def __init__(self, plugins_dir: str = "plugins", cache_enabled: bool = True):
        """
        Inicializa el UI Proxy.
        
        Args:
            plugins_dir: Directorio base de plugins/apps
            cache_enabled: Habilitar caché de recursos estáticos
        """
        self.plugins_dir = Path(plugins_dir)
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, bytes] = {}
        self._cache_etags: Dict[str, str] = {}
        
        # Crear directorio de plugins si no existe
        self.plugins_dir.mkdir(exist_ok=True)
        
        logger.info(f"UIProxy inicializado (plugins_dir: {plugins_dir})")
    
    def _get_app_dir(self, app_id: str) -> Path:
        """
        Retorna el directorio de una aplicación específica.
        
        Args:
            app_id: ID de la aplicación
            
        Returns:
            Path del directorio de la aplicación
            
        Raises:
            ResourceNotFoundError: Si no se encuentra la aplicación
        """
        app_dir = self.plugins_dir / app_id
        
        if not app_dir.exists():
            raise ResourceNotFoundError(f"Aplicación no encontrada: {app_id}")
        
        return app_dir
    
    def _get_ui_dir(self, app_id: str) -> Path:
        """
        Retorna el directorio UI de una aplicación.
        
        Args:
            app_id: ID de la aplicación
            
        Returns:
            Path del directorio UI
            
        Raises:
            ResourceNotFoundError: Si no se encuentra el directorio UI
        """
        app_dir = self._get_app_dir(app_id)
        ui_dir = app_dir / "ui"
        
        if not ui_dir.exists():
            raise ResourceNotFoundError(f"Directorio UI no encontrado para app: {app_id}")
        
        return ui_dir
    
    def _get_resource_path(self, app_id: str, resource_path: str) -> Path:
        """
        Retorna la ruta completa de un recurso.
        
        Args:
            app_id: ID de la aplicación
            resource_path: Ruta relativa del recurso
            
        Returns:
            Path completo del recurso
            
        Raises:
            ResourceNotFoundError: Si no se encuentra el recurso
        """
        ui_dir = self._get_ui_dir(app_id)
        
        # Eliminar slash inicial si existe
        if resource_path.startswith("/"):
            resource_path = resource_path[1:]
        
        resource_file = ui_dir / resource_path
        
        if not resource_file.exists():
            raise ResourceNotFoundError(
                f"Recurso no encontrado: {app_id}/{resource_path}"
            )
        
        if not resource_file.is_file():
            raise ResourceNotFoundError(
                f"Ruta no es un archivo: {app_id}/{resource_path}"
            )
        
        return resource_file
    
    def _get_mime_type(self, file_path: Path) -> str:
        """
        Determina el MIME type de un archivo.
        
        Args:
            file_path: Path del archivo
            
        Returns:
            MIME type del archivo
        """
        mime_type, _ = mimetypes.guess_type(str(file_path))
        
        if mime_type:
            return mime_type
        
        # Fallback para extensiones comunes
        ext = file_path.suffix.lower()
        mime_map = {
            '.html': 'text/html',
            '.css': 'text/css',
            '.js': 'application/javascript',
            '.json': 'application/json',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.ico': 'image/x-icon',
            '.woff': 'font/woff',
            '.woff2': 'font/woff2',
            '.ttf': 'font/ttf',
            '.eot': 'application/vnd.ms-fontobject',
        }
        
        return mime_map.get(ext, 'application/octet-stream')
    
    def _generate_etag(self, content: bytes, file_path: Path) -> str:
        """
        Genera un ETag para un recurso.
        
        Args:
            content: Contenido del recurso
            file_path: Path del archivo (para incluir en el hash)
            
        Returns:
            String ETag
        """
        import hashlib
        
        # Crear hash del contenido y del path
        hasher = hashlib.md5()
        hasher.update(content)
        hasher.update(str(file_path).encode())
        
        return f'"{hasher.hexdigest()}"'
    
    def _check_cache_headers(
        self,
        request: Request,
        etag: str,
        last_modified: Optional[float] = None
    ) -> bool:
        """
        Verifica si el cliente tiene el recurso en caché.
        
        Args:
            request: Request HTTP
            etag: ETag del recurso
            last_modified: Timestamp de última modificación
            
        Returns:
            True si el cliente tiene el recurso en caché
        """
        # Verificar If-None-Match (ETag)
        if_none_match = request.headers.get("if-none-match")
        if if_none_match and if_none_match == etag:
            return True
        
        # Verificar If-Modified-Since
        if_modified_since = request.headers.get("if-modified-since")
        if last_modified and if_modified_since:
            try:
                import time
                client_time = time.strptime(if_modified_since, "%a, %d %b %Y %H:%M:%S %Z")
                client_timestamp = time.mktime(client_time)
                
                if client_timestamp >= last_modified:
                    return True
            except Exception:
                pass
        
        return False
    
    def _inject_config(
        self,
        content: str,
        app_id: str,
        tenant_id: str,
        additional_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Inyecta configuración en un archivo HTML.
        
        Busca y reemplaza una variable especial en el HTML
        con la configuración de la aplicación.
        
        Args:
            content: Contenido HTML original
            app_id: ID de la aplicación
            tenant_id: ID del tenant
            additional_config: Configuración adicional
            
        Returns:
            Contenido HTML con configuración inyectada
        """
        import json
        
        config = {
            "appId": app_id,
            "tenantId": tenant_id,
            "wsUrl": f"ws://localhost:8081/ws/app/{app_id}/{tenant_id}",
            "apiUrl": f"http://localhost:8080/api"
        }
        
        if additional_config:
            config.update(additional_config)
        
        config_json = json.dumps(config, indent=2)
        
        # Reemplazar variable de configuración
        # Busca: window.__MCP_CONFIG__ = {};
        # Reemplaza con: window.__MCP_CONFIG__ = {config_json};
        placeholder = "window.__MCP_CONFIG__ = {};"
        replacement = f"window.__MCP_CONFIG__ = {config_json};"
        
        content = content.replace(placeholder, replacement)
        
        # Si no encuentra el placeholder, inyecta antes del </body>
        if placeholder not in content and "</body>" in content:
            injection = f'<script>window.__MCP_CONFIG__ = {config_json};</script>'
            content = content.replace("</body>", f"{injection}</body>")
        
        return content
    
    async def _read_file(self, file_path: Path) -> bytes:
        """
        Lee el contenido de un archivo de forma asíncrona.
        
        Args:
            file_path: Path del archivo
            
        Returns:
            Contenido del archivo
        """
        async with aiofiles.open(file_path, "rb") as f:
            return await f.read()
    
    async def serve_resource(
        self,
        app_id: str,
        resource_path: str,
        request: Optional[Request] = None
    ) -> Response:
        """
        Sirve un recurso estático de una aplicación.
        
        Args:
            app_id: ID de la aplicación
            resource_path: Ruta relativa del recurso
            request: Request HTTP (opcional, para cache headers)
            
        Returns:
            Response con el recurso
            
        Raises:
            ResourceNotFoundError: Si no se encuentra el recurso
        """
        file_path = self._get_resource_path(app_id, resource_path)
        file_key = f"{app_id}:{resource_path}"
        
        # Leer contenido
        content = await self._read_file(file_path)
        
        # Determinar MIME type
        mime_type = self._get_mime_type(file_path)
        
        # Generar ETag
        etag = self._generate_etag(content, file_path)
        
        # Verificar caché del cliente
        if request and self._check_cache_headers(
            request,
            etag,
            file_path.stat().st_mtime
        ):
            return Response(status_code=304, headers={"ETag": etag})
        
        # Crear headers
        headers = {
            "ETag": etag,
            "Cache-Control": "public, max-age=3600",
            "Content-Type": mime_type
        }
        
        # Retornar respuesta
        return Response(content=content, headers=headers)
    
    async def serve_app_index(
        self,
        app_id: str,
        tenant_id: str,
        request: Optional[Request] = None,
        additional_config: Optional[Dict[str, Any]] = None
    ) -> HTMLResponse:
        """
        Sirve el index.html de una aplicación con configuración inyectada.
        
        Args:
            app_id: ID de la aplicación
            tenant_id: ID del tenant
            request: Request HTTP (opcional)
            additional_config: Configuración adicional a inyectar
            
        Returns:
            HTMLResponse con el index.html configurado
            
        Raises:
            ResourceNotFoundError: Si no se encuentra el index.html
        """
        file_path = self._get_resource_path(app_id, "index.html")
        file_key = f"{app_id}:index.html"
        
        # Leer contenido
        content_bytes = await self._read_file(file_path)
        content = content_bytes.decode("utf-8")
        
        # Inyectar configuración
        content = self._inject_config(
            content,
            app_id,
            tenant_id,
            additional_config
        )
        
        # Generar ETag
        content_injected = content.encode("utf-8")
        etag = self._generate_etag(content_injected, file_path)
        
        # Verificar caché del cliente
        if request and self._check_cache_headers(
            request,
            etag,
            file_path.stat().st_mtime
        ):
            return HTMLResponse(status_code=304, headers={"ETag": etag})
        
        # Retornar respuesta
        headers = {
            "ETag": etag,
            "Cache-Control": "no-cache",  # No cachear index.html configurado
        }
        
        return HTMLResponse(content=content, headers=headers)
    
    async def list_apps(self) -> JSONResponse:
        """
        Lista todas las aplicaciones disponibles.
        
        Returns:
            JSONResponse con lista de aplicaciones
        """
        apps = []
        
        for app_dir in self.plugins_dir.iterdir():
            if app_dir.is_dir():
                ui_dir = app_dir / "ui"
                index_file = ui_dir / "index.html"
                
                if index_file.exists():
                    apps.append({
                        "app_id": app_dir.name,
                        "ui_path": str(ui_dir),
                        "has_ui": True
                    })
                else:
                    apps.append({
                        "app_id": app_dir.name,
                        "ui_path": None,
                        "has_ui": False
                    })
        
        return JSONResponse(content={
            "apps": apps,
            "total": len(apps)
        })
    
    async def get_app_info(self, app_id: str) -> JSONResponse:
        """
        Retorna información detallada de una aplicación.
        
        Args:
            app_id: ID de la aplicación
            
        Returns:
            JSONResponse con información de la aplicación
            
        Raises:
            ResourceNotFoundError: Si no se encuentra la aplicación
        """
        app_dir = self._get_app_dir(app_id)
        ui_dir = app_dir / "ui"
        
        # Listar archivos UI
        ui_files = []
        if ui_dir.exists():
            for file_path in ui_dir.rglob("*"):
                if file_path.is_file():
                    rel_path = file_path.relative_to(ui_dir)
                    ui_files.append(str(rel_path))
        
        # Buscar metadata (opcional)
        metadata_path = app_dir / "metadata.json"
        metadata = {}
        if metadata_path.exists():
            async with aiofiles.open(metadata_path, "r") as f:
                content = await f.read()
                import json
                metadata = json.loads(content)
        
        return JSONResponse(content={
            "app_id": app_id,
            "has_ui": ui_dir.exists(),
            "ui_files": ui_files,
            "metadata": metadata
        })
    
    def clear_cache(self, app_id: Optional[str] = None) -> None:
        """
        Limpia la caché de recursos estáticos.
        
        Args:
            app_id: ID de la aplicación específica (limpia todas si es None)
        """
        if app_id:
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(f"{app_id}:")]
            for key in keys_to_remove:
                del self._cache[key]
                if key in self._cache_etags:
                    del self._cache_etags[key]
            logger.info(f"Caché limpiada para app: {app_id}")
        else:
            self._cache.clear()
            self._cache_etags.clear()
            logger.info("Toda la caché limpiada")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Retorna estadísticas de la caché.
        
        Returns:
            Diccionario con estadísticas
        """
        total_size = sum(len(content) for content in self._cache.values())
        
        return {
            "enabled": self.cache_enabled,
            "entries": len(self._cache),
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024)
        }
