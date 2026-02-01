"""
Tests de Integración del MCP Hub
===================================

Tests de integración para verificar el funcionamiento
correcto de todos los componentes juntos.

Autor: Ainsophic Team
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def sample_config():
    """
    Fixture que retorna una configuración de ejemplo.
    """
    return {
        "version": "1.0.0",
        "tenants": {
            "default": {
                "description": "Tenant por defecto",
                "servers": {
                    "sqlite-demo": {
                        "name": "sqlite-demo",
                        "type": "database",
                        "command": "python",
                        "args": ["-m", "mcp.server.sqlite", "--db-path", ":memory:"],
                        "enabled": True,
                        "capabilities": ["tools"],
                        "transport": "stdio",
                        "metadata": {
                            "description": "Servidor SQLite de ejemplo"
                        }
                    }
                }
            }
        },
        "gateway": {
            "port": 8080,
            "mcp_port": 8000,
            "websocket_port": 8081,
            "host": "0.0.0.0"
        },
        "logging": {
            "level": "INFO",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        },
        "orchestrator": {
            "auto_start": False,
            "max_retries": 3,
            "startup_timeout": 30
        }
    }


@pytest.fixture
def config_file(sample_config):
    """
    Fixture que crea un archivo de configuración temporal.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_config, f)
        config_path = f.name
    
    yield config_path
    
    # Cleanup
    Path(config_path).unlink(missing_ok=True)


def test_registry_to_multitenant_manager_integration(config_file):
    """
    Test: Integración entre Registry y MultitenantManager.
    
    Verifica que el MultitenantManager pueda obtener configuraciones
    del Registry correctamente.
    """
    from mcp_hub.core.registry import Registry
    from mcp_hub.core.multitenant import MultitenantManager
    from mcp_hub.core.router import DynamicToolRouter
    
    # Inicializar Registry
    registry = Registry.load(config_file)
    assert registry is not None
    
    # Crear mocks para Orchestrator y Router
    mock_orchestrator = MagicMock()
    mock_orchestrator._parse_server_id = lambda sid: sid.split(":", 1)
    mock_orchestrator.get_server_client = MagicMock(return_value=None)
    
    mock_router = MagicMock()
    mock_router.clear_tools = MagicMock()
    mock_router.get_tools_by_server = MagicMock(return_value=[])
    
    # Inicializar MultitenantManager
    multitenant_manager = MultitenantManager(
        registry=registry,
        orchestrator=mock_orchestrator,
        router=mock_router
    )
    
    # Verificar que el MultitenantManager puede acceder al Registry
    tenant = multitenant_manager.get_or_create_tenant("default")
    assert tenant is not None
    assert tenant.tenant_id == "default"


def test_orchestrator_to_registry_integration(config_file):
    """
    Test: Integración entre Orchestrator y Registry.
    
    Verifica que el Orchestrator pueda obtener configuraciones
    del Registry para iniciar servidores.
    """
    from mcp_hub.core.registry import Registry
    from mcp_hub.core.orchestrator import Orchestrator
    
    # Inicializar Registry
    registry = Registry.load(config_file)
    assert registry is not None
    
    # Inicializar Orchestrator
    orchestrator = Orchestrator(registry)
    
    # Verificar que el Orchestrator puede acceder al Registry
    server_config = registry.get_server_config("default", "sqlite-demo")
    assert server_config is not None
    assert server_config.name == "sqlite-demo"
    
    # Verificar generación de IDs
    server_id = orchestrator._generate_server_id("default", "sqlite-demo")
    assert server_id == "default:sqlite-demo"
    
    # Verificar parsing de IDs
    tenant_id, server_name = orchestrator._parse_server_id("default:sqlite-demo")
    assert tenant_id == "default"
    assert server_name == "sqlite-demo"


def test_router_to_orchestrator_integration():
    """
    Test: Integración entre Router y Orchestrator.
    
    Verifica que el Router pueda obtener clientes MCP
    del Orchestrator para ejecutar herramientas.
    """
    from mcp_hub.core.orchestrator import Orchestrator
    from mcp_hub.core.router import DynamicToolRouter
    from mcp_hub.core.registry import Registry
    import tempfile
    import json
    
    # Crear configuración mínima
    config = {
        "version": "1.0.0",
        "tenants": {},
        "gateway": {"port": 8080, "mcp_port": 8000, "websocket_port": 8081, "host": "0.0.0.0"},
        "logging": {"level": "INFO", "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"},
        "orchestrator": {"auto_start": False, "max_retries": 3, "startup_timeout": 30}
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        config_path = f.name
    
    try:
        # Inicializar componentes
        registry = Registry.load(config_path)
        orchestrator = Orchestrator(registry)
        router = DynamicToolRouter(orchestrator)
        
        # Verificar integración
        assert router.orchestrator == orchestrator
        
        # Verificar que el Router puede generar IDs correctos
        prefixed_name = router._generate_prefixed_name("default:postgres", "query")
        assert prefixed_name == "postgres.query"
        
    finally:
        Path(config_path).unlink(missing_ok=True)


def test_multitenant_isolation():
    """
    Test: Aislamiento entre tenants.
    
    Verifica que diferentes tenants tengan sus propios
    namespaces y no interfieran entre sí.
    """
    from mcp_hub.core.registry import Registry
    from mcp_hub.core.multitenant import MultitenantManager
    from mcp_hub.core.router import DynamicToolRouter
    from mcp_hub.core.orchestrator import Orchestrator
    import tempfile
    import json
    
    # Crear configuración con múltiples tenants
    config = {
        "version": "1.0.0",
        "tenants": {
            "tenant1": {
                "description": "Tenant 1",
                "servers": {
                    "postgres1": {
                        "name": "postgres1",
                        "type": "database",
                        "command": "python",
                        "args": [],
                        "enabled": True,
                        "capabilities": ["tools"],
                        "transport": "stdio",
                        "metadata": {}
                    }
                }
            },
            "tenant2": {
                "description": "Tenant 2",
                "servers": {
                    "postgres2": {
                        "name": "postgres2",
                        "type": "database",
                        "command": "python",
                        "args": [],
                        "enabled": True,
                        "capabilities": ["tools"],
                        "transport": "stdio",
                        "metadata": {}
                    }
                }
            }
        },
        "gateway": {"port": 8080, "mcp_port": 8000, "websocket_port": 8081, "host": "0.0.0.0"},
        "logging": {"level": "INFO", "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"},
        "orchestrator": {"auto_start": False, "max_retries": 3, "startup_timeout": 30}
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        config_path = f.name
    
    try:
        # Inicializar componentes
        registry = Registry.load(config_path)
        mock_orchestrator = MagicMock()
        mock_orchestrator._parse_server_id = lambda sid: sid.split(":", 1)
        mock_orchestrator.get_server_client = MagicMock(return_value=None)
        
        mock_router = MagicMock()
        mock_router.clear_tools = MagicMock()
        mock_router.get_tools_by_server = MagicMock(return_value=[])
        
        multitenant_manager = MultitenantManager(
            registry=registry,
            orchestrator=mock_orchestrator,
            router=mock_router
        )
        
        # Crear contextos para ambos tenants
        context1 = multitenant_manager.get_or_create_tenant("tenant1")
        context2 = multitenant_manager.get_or_create_tenant("tenant2")
        
        # Verificar que son diferentes
        assert context1 is not context2
        assert context1.tenant_id == "tenant1"
        assert context2.tenant_id == "tenant2"
        
        # Verificar que tienen sus propios recursos
        assert context1.servers != context2.servers
        assert context1.tools != context2.tools
        
    finally:
        Path(config_path).unlink(missing_ok=True)


def test_component_lifecycle():
    """
    Test: Ciclo de vida de los componentes.
    
    Verifica que los componentes se inicialicen correctamente
    y puedan ser limpiados apropiadamente.
    """
    from mcp_hub.core.registry import Registry
    from mcp_hub.core.orchestrator import Orchestrator
    from mcp_hub.core.router import DynamicToolRouter
    from mcp_hub.core.multitenant import MultitenantManager
    import tempfile
    import json
    
    # Crear configuración mínima
    config = {
        "version": "1.0.0",
        "tenants": {},
        "gateway": {"port": 8080, "mcp_port": 8000, "websocket_port": 8081, "host": "0.0.0.0"},
        "logging": {"level": "INFO", "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"},
        "orchestrator": {"auto_start": False, "max_retries": 3, "startup_timeout": 30}
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        config_path = f.name
    
    try:
        # Inicializar componentes en el orden correcto
        registry = Registry.load(config_path)
        assert registry is not None
        
        orchestrator = Orchestrator(registry)
        assert orchestrator is not None
        
        router = DynamicToolRouter(orchestrator)
        assert router is not None
        
        # Verificar que los componentes están conectados
        assert router.orchestrator == orchestrator
        assert orchestrator.registry == registry
        
        # Crear mock para MultitenantManager
        mock_router = MagicMock()
        mock_router.clear_tools = MagicMock()
        mock_router.get_tools_by_server = MagicMock(return_value=[])
        
        multitenant_manager = MultitenantManager(
            registry=registry,
            orchestrator=orchestrator,
            router=mock_router
        )
        assert multitenant_manager is not None
        
        # Verificar conexiones
        assert multitenant_manager.registry == registry
        assert multitenant_manager.orchestrator == orchestrator
        
        # Simular cleanup
        Registry._instance = None  # Reset singleton
        
    finally:
        Path(config_path).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
