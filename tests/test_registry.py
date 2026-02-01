"""
Tests del Registry - Gestión de Configuración
===============================================

Tests unitarios para el componente Registry del MCP Hub.

Autor: Ainsophic Team
"""

import pytest
import json
import tempfile
from pathlib import Path

from mcp_hub.core.registry import (
    Registry,
    ServerConfig,
    TenantConfig,
    GatewayConfig,
    OrchestratorConfig
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
                        "capabilities": ["tools", "resources"],
                        "transport": "stdio",
                        "metadata": {
                            "description": "Servidor PostgreSQL"
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


def test_server_config_creation():
    """
    Test: Creación de ServerConfig.
    """
    config = ServerConfig(
        name="postgres",
        type="database",
        command="python",
        args=["-m", "mcp.server.postgres"],
        enabled=True,
        capabilities=["tools"]
    )
    
    assert config.name == "postgres"
    assert config.type == "database"
    assert config.enabled is True
    assert config.get_full_command() == ["python", "-m", "mcp.server.postgres"]


def test_tenant_config_creation():
    """
    Test: Creación de TenantConfig.
    """
    server_config = ServerConfig(
        name="postgres",
        type="database",
        command="python",
        args=[],
        enabled=True
    )
    
    tenant = TenantConfig(
        tenant_id="default",
        description="Tenant por defecto",
        servers={"postgres": server_config}
    )
    
    assert tenant.tenant_id == "default"
    assert len(tenant.servers) == 1
    assert len(tenant.get_enabled_servers()) == 1


def test_tenant_config_get_enabled_servers():
    """
    Test: Obtener solo servidores habilitados.
    """
    enabled_server = ServerConfig(
        name="postgres",
        type="database",
        command="python",
        args=[],
        enabled=True
    )
    
    disabled_server = ServerConfig(
        name="mysql",
        type="database",
        command="python",
        args=[],
        enabled=False
    )
    
    tenant = TenantConfig(
        tenant_id="default",
        servers={
            "postgres": enabled_server,
            "mysql": disabled_server
        }
    )
    
    enabled = tenant.get_enabled_servers()
    assert len(enabled) == 1
    assert enabled[0].name == "postgres"


def test_registry_load_config(config_file, sample_config):
    """
    Test: Cargar configuración desde archivo JSON.
    """
    registry = Registry.load(config_file)
    
    assert registry.version == sample_config["version"]
    assert "default" in registry.tenants
    assert len(registry.tenants) == 1


def test_registry_load_tenant_config(config_file):
    """
    Test: Cargar configuración de tenant correctamente.
    """
    registry = Registry.load(config_file)
    tenant = registry.get_tenant("default")
    
    assert tenant is not None
    assert tenant.tenant_id == "default"
    assert "postgres" in tenant.servers
    assert tenant.servers["postgres"].type == "database"


def test_registry_load_gateway_config(config_file):
    """
    Test: Cargar configuración del gateway correctamente.
    """
    registry = Registry.load(config_file)
    
    assert registry.gateway.port == 8080
    assert registry.gateway.mcp_port == 8000
    assert registry.gateway.websocket_port == 8081
    assert registry.gateway.host == "0.0.0.0"


def test_registry_load_orchestrator_config(config_file):
    """
    Test: Cargar configuración del orchestrator correctamente.
    """
    registry = Registry.load(config_file)
    
    assert registry.orchestrator.auto_start is False
    assert registry.orchestrator.max_retries == 3
    assert registry.orchestrator.startup_timeout == 30


def test_registry_get_nonexistent_tenant(config_file):
    """
    Test: Obtener tenant que no existe retorna None.
    """
    registry = Registry.load(config_file)
    tenant = registry.get_tenant("nonexistent")
    
    assert tenant is None


def test_registry_get_all_tenants(config_file):
    """
    Test: Obtener lista de todos los tenants.
    """
    registry = Registry.load(config_file)
    tenants = registry.get_all_tenants()
    
    assert len(tenants) == 1
    assert "default" in tenants


def test_registry_get_server_config(config_file):
    """
    Test: Obtener configuración de servidor específico.
    """
    registry = Registry.load(config_file)
    server = registry.get_server_config("default", "postgres")
    
    assert server is not None
    assert server.name == "postgres"
    assert server.type == "database"


def test_registry_get_all_servers(config_file):
    """
    Test: Obtener todos los servidores con sus IDs.
    """
    registry = Registry.load(config_file)
    servers = registry.get_all_servers()
    
    assert len(servers) == 1
    assert "default:postgres" in servers
    assert servers["default:postgres"].name == "postgres"


def test_registry_nonexistent_config_file():
    """
    Test: Intentar cargar archivo inexistente lanza excepción.
    """
    with pytest.raises(FileNotFoundError):
        Registry.load("nonexistent_config.json")


def test_registry_invalid_json(tmp_path):
    """
    Test: Intentar cargar JSON inválido lanza excepción.
    """
    config_file = tmp_path / "invalid.json"
    config_file.write_text("invalid json content")
    
    with pytest.raises(json.JSONDecodeError):
        Registry.load(str(config_file))


def test_registry_singleton(config_file):
    """
    Test: Registry implementa patrón Singleton.
    """
    registry1 = Registry.load(config_file)
    registry2 = Registry.get_instance()
    
    assert registry1 is registry2


def test_registry_get_instance_without_load():
    """
    Test: Obtener instancia sin cargar lanza excepción.
    """
    Registry._instance = None  # Reset singleton
    
    with pytest.raises(RuntimeError):
        Registry.get_instance()


def test_registry_reload(config_file):
    """
    Test: Recargar configuración desde archivo.
    """
    registry = Registry.load(config_file)
    
    # Modificar archivo
    with open(config_file, 'r+') as f:
        config = json.load(f)
        config["version"] = "2.0.0"
        f.seek(0)
        json.dump(config, f)
        f.truncate()
    
    # Recargar
    registry.reload()
    
    assert registry.version == "2.0.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
