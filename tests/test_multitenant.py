"""
Tests del Multitenant Manager - Gestión Multitenant
======================================================

Tests unitarios para el componente MultitenantManager del MCP Hub.

Autor: Ainsophic Team
"""

import pytest
import tempfile
import json
from pathlib import Path

from mcp_hub.core.registry import Registry, TenantConfig, ServerConfig
from mcp_hub.core.multitenant import (
    MultitenantManager,
    TenantContext,
    TenantNotFoundError,
    QuotaExceededError
)


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
                    "postgres": {
                        "name": "postgres",
                        "type": "database",
                        "command": "python",
                        "args": ["-m", "mcp.server.postgres"],
                        "enabled": True,
                        "capabilities": ["tools"],
                        "transport": "stdio",
                        "metadata": {}
                    }
                }
            },
            "production": {
                "description": "Tenant de producción",
                "servers": {
                    "postgres-prod": {
                        "name": "postgres-prod",
                        "type": "database",
                        "command": "python",
                        "args": ["-m", "mcp.server.postgres"],
                        "enabled": True,
                        "capabilities": ["tools"],
                        "transport": "stdio",
                        "metadata": {}
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


@pytest.fixture
def registry(config_file):
    """
    Fixture que retorna un Registry inicializado.
    """
    return Registry.load(config_file)


@pytest.fixture
def mock_orchestrator():
    """
    Fixture que crea un mock del Orchestrator.
    """
    from unittest.mock import MagicMock
    
    orchestrator = MagicMock()
    orchestrator._parse_server_id = lambda sid: sid.split(":", 1)
    orchestrator.get_server_client = MagicMock(return_value=None)
    
    return orchestrator


@pytest.fixture
def mock_router():
    """
    Fixture que crea un mock del Router.
    """
    from unittest.mock import MagicMock
    
    router = MagicMock()
    router.clear_tools = MagicMock()
    router.get_tools_by_server = MagicMock(return_value=[])
    
    return router


@pytest.fixture
def multitenant_manager(registry, mock_orchestrator, mock_router):
    """
    Fixture que retorna un MultitenantManager inicializado.
    """
    return MultitenantManager(
        registry=registry,
        orchestrator=mock_orchestrator,
        router=mock_router
    )


def test_tenant_context_creation(multitenant_manager, registry):
    """
    Test: Creación de TenantContext.
    """
    tenant_config = registry.get_tenant("default")
    context = TenantContext(
        tenant_id="default",
        config=tenant_config
    )
    
    assert context.tenant_id == "default"
    assert context.config == tenant_config
    assert len(context.servers) == 0
    assert not context.is_active()


def test_tenant_context_update_activity(multitenant_manager, registry):
    """
    Test: Actualizar actividad de tenant.
    """
    tenant_config = registry.get_tenant("default")
    context = TenantContext(
        tenant_id="default",
        config=tenant_config
    )
    
    import time
    time.sleep(0.1)
    
    context.update_activity()
    assert context.last_activity > context.created_at


def test_multitenant_manager_initialization(multitenant_manager):
    """
    Test: Inicialización del MultitenantManager.
    """
    assert multitenant_manager.registry is not None
    assert multitenant_manager.orchestrator is not None
    assert multitenant_manager.router is not None
    assert len(multitenant_manager.tenants) == 0


def test_multitenant_manager_get_or_create_tenant_new(multitenant_manager):
    """
    Test: Obtener o crear tenant nuevo.
    """
    context = multitenant_manager.get_or_create_tenant("default")
    
    assert context is not None
    assert context.tenant_id == "default"
    assert "default" in multitenant_manager.tenants


def test_multitenant_manager_get_or_create_tenant_existing(multitenant_manager):
    """
    Test: Obtener tenant existente retorna misma instancia.
    """
    context1 = multitenant_manager.get_or_create_tenant("default")
    context2 = multitenant_manager.get_or_create_tenant("default")
    
    assert context1 is context2


def test_multitenant_manager_get_tenant_nonexistent(multitenant_manager):
    """
    Test: Obtener tenant no registrado retorna None.
    """
    context = multitenant_manager.get_tenant("nonexistent")
    assert context is None


def test_multitenant_manager_get_tenant_existing(multitenant_manager):
    """
    Test: Obtener tenant registrado retorna contexto.
    """
    multitenant_manager.get_or_create_tenant("default")
    context = multitenant_manager.get_tenant("default")
    
    assert context is not None
    assert context.tenant_id == "default"


def test_multitenant_manager_set_quota(multitenant_manager):
    """
    Test: Establecer cuota para tenant.
    """
    multitenant_manager.set_quota("default", "max_servers", 5)
    
    assert "default" in multitenant_manager.quotas
    assert multitenant_manager.quotas["default"]["max_servers"] == 5


def test_multitenant_manager_get_quota_default(multitenant_manager):
    """
    Test: Obtener cuota por defecto.
    """
    quota = multitenant_manager.get_quota("default", "max_servers")
    
    assert quota == 10  # Valor por defecto


def test_multitenant_manager_get_quota_custom(multitenant_manager):
    """
    Test: Obtener cuota personalizada.
    """
    multitenant_manager.set_quota("default", "max_servers", 5)
    quota = multitenant_manager.get_quota("default", "max_servers")
    
    assert quota == 5


def test_multitenant_manager_get_tenant_tools_empty(multitenant_manager):
    """
    Test: Obtener herramientas de tenant sin contexto retorna vacío.
    """
    tools = multitenant_manager.get_tenant_tools("default")
    assert tools == []


def test_multitenant_manager_get_tenant_tools_summary_nonexistent(multitenant_manager):
    """
    Test: Obtener resumen de tenant no existente.
    """
    summary = multitenant_manager.get_tenant_tools_summary("nonexistent")
    
    assert summary["tenant_id"] == "nonexistent"
    assert summary["exists"] is False
    assert summary["tools"] == []


def test_multitenant_manager_get_all_tenants_status_empty(multitenant_manager):
    """
    Test: Obtener estado de todos los tenants cuando no hay ninguno.
    """
    status = multitenant_manager.get_all_tenants_status()
    
    assert len(status) == 0


def test_multitenant_manager_get_tenant_status_nonexistent(multitenant_manager):
    """
    Test: Obtener estado de tenant no existente retorna None.
    """
    status = multitenant_manager.get_tenant_status("nonexistent")
    assert status is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
