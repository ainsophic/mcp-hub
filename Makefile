# ============================================================================
# Makefile - MCP Hub
# ============================================================================
# Autor: Equipo Ainsophic
# Enfoque: Comandos de alto nivel para operaciones comunes
#
# CONCEPTO FEYNMAN - Makefiles:
# --------------------------------
# Imagina que tienes un asistente que recuerda TODOS los comandos
# complejos de tu trabajo.
#
# Sin el asistente:
# Tú: "Hola, quiero construir y ejecutar el proyecto en modo
#        desarrollo con PostgreSQL y ver los logs."
# Asistente: "Ejecuta esto: docker-compose -f docker-compose.dev.yml
#                    --profile postgres up --build && docker-compose -f
#                    docker-compose.dev.yml logs -f"
#
# Con el asistente (Makefile):
# Tú: "make up-dev-db"
# Asistente: [Ejecuta automáticamente el comando complejo]
#
# RESULTADO: Comandos simples que ejecutan tareas complejas.
# ============================================================================

# ----------------------------------------------------------------------------
# CONFIGURACIÓN DEL MAKEFILE
# ----------------------------------------------------------------------------

# Shell a usar (bash para mejores features)
SHELL := /bin/bash

# Deshabilitar reglas intermedias (no crear archivos .o, etc.)
.NOTINTERMEDIATE:

# Deshabilitar reglas de phony (objetivos que no representan archivos)
.PHONY: help build build-dev up up-dev up-prod down down-v logs ps test clean install-dev install-prod format lint lint-all test-local coverage shell check build-images push-images deploy

# Colores para salida de terminal (solo si TTY)
ifeq ($(TERM),dumb)
    NO_COLOR := true
else
    NO_COLOR := false
endif

# Definir colores si hay TTY
ifeq ($(NO_COLOR),true)
    COLOR_RESET :=
    COLOR_BOLD :=
    COLOR_GREEN :=
    COLOR_YELLOW :=
    COLOR_BLUE :=
    COLOR_RED :=
else
    COLOR_RESET := \033[0m
    COLOR_BOLD := \033[1m
    COLOR_GREEN := \033[32m
    COLOR_YELLOW := \033[33m
    COLOR_BLUE := \033[34m
    COLOR_RED := \033[31m
endif

# ----------------------------------------------------------------------------
# OBJETIVO PRINCIPAL: Ayuda
# ----------------------------------------------------------------------------

help: ## Mostrar esta ayuda
	@echo "$(COLOR_BOLD)MCP Hub - Makefile de Comandos$(COLOR_RESET)"
	@echo ""
	@echo "$(COLOR_BLUE)Uso:$(COLOR_RESET) make [objetivo]"
	@echo ""
	@echo "$(COLOR_BLUE)Objetivos disponibles:$(COLOR_RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(COLOR_GREEN)%-20s$(COLOR_RESET) %s\n", $$1, $$2}'

# ----------------------------------------------------------------------------
# OBJETIVOS DE CONSTRUCCIÓN (BUILD)
# ----------------------------------------------------------------------------

build: ## Construir imagen de producción
	@echo "$(COLOR_BOLD)Construyendo imagen de producción...$(COLOR_RESET)"
	docker build -t mcp-hub:0.1.0 .
	@echo "$(COLOR_GREEN)✓ Imagen de producción construida$(COLOR_RESET)"

build-dev: ## Construir imagen de desarrollo
	@echo "$(COLOR_BOLD)Construyendo imagen de desarrollo...$(COLOR_RESET)"
	docker build -f Dockerfile.dev -t mcp-hub:dev .
	@echo "$(COLOR_GREEN)✓ Imagen de desarrollo construida$(COLOR_RESET)"

build-no-cache: ## Construir imagen sin caché
	@echo "$(COLOR_BOLD)Construyendo imagen sin caché...$(COLOR_RESET)"
	docker build --no-cache -t mcp-hub:0.1.0 .
	@echo "$(COLOR_GREEN)✓ Imagen construida sin caché$(COLOR_RESET)"

build-dev-no-cache: ## Construir imagen de desarrollo sin caché
	@echo "$(COLOR_BOLD)Construyendo imagen de desarrollo sin caché...$(COLOR_RESET)"
	docker build --no-cache -f Dockerfile.dev -t mcp-hub:dev .
	@echo "$(COLOR_GREEN)✓ Imagen de desarrollo construida sin caché$(COLOR_RESET)"

build-images: ## Construir todas las imágenes
	@echo "$(COLOR_BOLD)Construyendo todas las imágenes...$(COLOR_RESET)"
	$(MAKE) build
	$(MAKE) build-dev
	@echo "$(COLOR_GREEN)✓ Todas las imágenes construidas$(COLOR_RESET)"

# ----------------------------------------------------------------------------
# OBJETIVOS DE EJECUCIÓN (UP/DOWN)
# ----------------------------------------------------------------------------

up: ## Iniciar servicios con Docker Compose
	@echo "$(COLOR_BOLD)Iniciando servicios con Docker Compose...$(COLOR_RESET)"
	docker-compose up -d
	@echo "$(COLOR_GREEN)✓ Servicios iniciados$(COLOR_RESET)"
	@echo ""
	@echo "$(COLOR_BLUE)Para ver logs: make logs$(COLOR_RESET)"
	@echo "$(COLOR_BLUE)Para detener: make down$(COLOR_RESET)"

up-dev: ## Iniciar servicios de desarrollo con hot-reload
	@echo "$(COLOR_BOLD)Iniciando servicios de desarrollo...$(COLOR_RESET)"
	docker-compose -f docker-compose.dev.yml up
	@echo "$(COLOR_GREEN)✓ Servicios de desarrollo iniciados$(COLOR_RESET)"

up-dev-detached: ## Iniciar servicios de desarrollo en modo detached (fondo)
	@echo "$(COLOR_BOLD)Iniciando servicios de desarrollo (detached)...$(COLOR_RESET)"
	docker-compose -f docker-compose.dev.yml up -d
	@echo "$(COLOR_GREEN)✓ Servicios de desarrollo iniciados en fondo$(COLOR_RESET)"
	@echo ""
	@echo "$(COLOR_BLUE)Para ver logs: make logs-dev$(COLOR_RESET)"

up-prod: ## Iniciar servicios de producción
	@echo "$(COLOR_BOLD)Iniciando servicios de producción...$(COLOR_RESET)"
	docker-compose -f docker-compose.prod.yml up -d
	@echo "$(COLOR_GREEN)✓ Servicios de producción iniciados$(COLOR_RESET)"

up-with-db: ## Iniciar servicios con PostgreSQL
	@echo "$(COLOR_BOLD)Iniciando servicios con PostgreSQL...$(COLOR_RESET)"
	docker-compose --profile postgres up -d
	@echo "$(COLOR_GREEN)✓ Servicios iniciados con PostgreSQL$(COLOR_RESET)"

up-dev-with-db: ## Iniciar servicios de desarrollo con PostgreSQL
	@echo "$(COLOR_BOLD)Iniciando servicios de desarrollo con PostgreSQL...$(COLOR_RESET)"
	docker-compose -f docker-compose.dev.yml --profile postgres up
	@echo "$(COLOR_GREEN)✓ Servicios de desarrollo iniciados con PostgreSQL$(COLOR_RESET)"

up-all: ## Iniciar todos los servicios (con PostgreSQL y Redis)
	@echo "$(COLOR_BOLD)Iniciando todos los servicios...$(COLOR_RESET)"
	docker-compose --profile postgres --profile redis up -d
	@echo "$(COLOR_GREEN)✓ Todos los servicios iniciados$(COLOR_RESET)"

down: ## Detener servicios
	@echo "$(COLOR_BOLD)Deteniendo servicios...$(COLOR_RESET)"
	docker-compose down
	@echo "$(COLOR_GREEN)✓ Servicios detenidos$(COLOR_RESET)"

down-v: ## Detener servicios y eliminar volúmenes (PELIGROSO: BORRA DATOS)
	@echo "$(COLOR_BOLD)$(COLOR_RED)ADVERTENCIA: Esto eliminará todos los volúmenes y datos$(COLOR_RESET)"
	@read -p "¿Estás seguro? [y/N] " -n 1 -r; \
	echo ""; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker-compose down -v; \
		echo "$(COLOR_GREEN)✓ Servicios y volúmenes eliminados$(COLOR_RESET)"; \
	else \
		echo "$(COLOR_YELLOW)Cancelado$(COLOR_RESET)"; \
	fi

down-dev: ## Detener servicios de desarrollo
	@echo "$(COLOR_BOLD)Deteniendo servicios de desarrollo...$(COLOR_RESET)"
	docker-compose -f docker-compose.dev.yml down
	@echo "$(COLOR_GREEN)✓ Servicios de desarrollo detenidos$(COLOR_RESET)"

down-prod: ## Detener servicios de producción
	@echo "$(COLOR_BOLD)Deteniendo servicios de producción...$(COLOR_RESET)"
	docker-compose -f docker-compose.prod.yml down
	@echo "$(COLOR_GREEN)✓ Servicios de producción detenidos$(COLOR_RESET)"

# ----------------------------------------------------------------------------
# OBJETIVOS DE MONITOREO (LOGS/STATUS)
# ----------------------------------------------------------------------------

logs: ## Ver logs de servicios (follow)
	docker-compose logs -f

logs-dev: ## Ver logs de servicios de desarrollo (follow)
	docker-compose -f docker-compose.dev.yml logs -f

logs-prod: ## Ver logs de servicios de producción (follow)
	docker-compose -f docker-compose.prod.yml logs -f

logs-api: ## Ver solo logs del API
	docker-compose logs -f mcp-hub

logs-db: ## Ver solo logs de PostgreSQL
	docker-compose logs -f postgres

ps: ## Mostrar estado de contenedores
	@echo "$(COLOR_BOLD)Estado de contenedores:$(COLOR_RESET)"
	docker-compose ps

ps-dev: ## Mostrar estado de contenedores de desarrollo
	@echo "$(COLOR_BOLD)Estado de contenedores (desarrollo):$(COLOR_RESET)"
	docker-compose -f docker-compose.dev.yml ps

ps-prod: ## Mostrar estado de contenedores de producción
	@echo "$(COLOR_BOLD)Estado de contenedores (producción):$(COLOR_RESET)"
	docker-compose -f docker-compose.prod.yml ps

status: healthcheck ## Alias para healthcheck

healthcheck: ## Verificar health de todos los servicios
	@echo "$(COLOR_BOLD)Health check de servicios:$(COLOR_RESET)"
	@echo ""
	@echo "$(COLOR_BLUE)MCP Hub (API):$(COLOR_RESET)"
	@curl -sf http://localhost:8080/health && echo "  $(COLOR_GREEN)✓ Healthy$(COLOR_RESET)" || echo "  $(COLOR_RED)✗ Unhealthy$(COLOR_RESET)"
	@echo ""

# ----------------------------------------------------------------------------
# OBJETIVOS DE INTERACCIÓN (EXEC/RESTART)
# ----------------------------------------------------------------------------

restart: ## Reiniciar servicios
	@echo "$(COLOR_BOLD)Reiniciando servicios...$(COLOR_RESET)"
	docker-compose restart
	@echo "$(COLOR_GREEN)✓ Servicios reiniciados$(COLOR_RESET)"

restart-dev: ## Reiniciar servicios de desarrollo
	@echo "$(COLOR_BOLD)Reiniciando servicios de desarrollo...$(COLOR_RESET)"
	docker-compose -f docker-compose.dev.yml restart
	@echo "$(COLOR_GREEN)✓ Servicios de desarrollo reiniciados$(COLOR_RESET)"

restart-prod: ## Reiniciar servicios de producción
	@echo "$(COLOR_BOLD)Reiniciando servicios de producción...$(COLOR_RESET)"
	docker-compose -f docker-compose.prod.yml restart
	@echo "$(COLOR_GREEN)✓ Servicios de producción reiniciados$(COLOR_RESET)"

shell: ## Abrir shell en el contenedor mcp-hub
	docker-compose exec mcp-hub bash

shell-dev: ## Abrir shell en el contenedor de desarrollo
	docker-compose -f docker-compose.dev.yml exec mcp-hub bash

shell-db: ## Abrir shell en el contenedor PostgreSQL
	docker-compose exec postgres psql -U $${POSTGRES_USER:-mcpuser} -d $${POSTGRES_DB:-mcpdb}

exec: ## Ejecutar comando en el contenedor (ej: make exec COMMAND="ls -la")
	docker-compose exec mcp-hub $(COMMAND)

exec-dev: ## Ejecutar comando en el contenedor de desarrollo (ej: make exec-dev COMMAND="ls -la")
	docker-compose -f docker-compose.dev.yml exec mcp-hub $(COMMAND)

# ----------------------------------------------------------------------------
# OBJETIVOS DE TESTING
# ----------------------------------------------------------------------------

test: ## Ejecutar tests en Docker
	@echo "$(COLOR_BOLD)Ejecutando tests en Docker...$(COLOR_RESET)"
	docker-compose run --rm mcp-hub pytest -v
	@echo "$(COLOR_GREEN)✓ Tests completados$(COLOR_RESET)"

test-coverage: ## Ejecutar tests con cobertura en Docker
	@echo "$(COLOR_BOLD)Ejecutando tests con cobertura en Docker...$(COLOR_RESET)"
	docker-compose run --rm mcp-hub pytest --cov=mcp_hub --cov-report=term-missing
	@echo "$(COLOR_GREEN)✓ Tests completados con reporte de cobertura$(COLOR_RESET)"

test-dev: ## Ejecutar tests en el contenedor de desarrollo
	@echo "$(COLOR_BOLD)Ejecutando tests en contenedor de desarrollo...$(COLOR_RESET)"
	docker-compose -f docker-compose.dev.yml run --rm mcp-hub pytest -v
	@echo "$(COLOR_GREEN)✓ Tests completados$(COLOR_RESET)"

test-local: ## Ejecutar tests localmente (sin Docker)
	@echo "$(COLOR_BOLD)Ejecutando tests localmente...$(COLOR_RESET)"
	pytest -v
	@echo "$(COLOR_GREEN)✓ Tests completados$(COLOR_RESET)"

# ----------------------------------------------------------------------------
# OBJETIVOS DE LIMPIEZA Y MANTENIMIENTO
# ----------------------------------------------------------------------------

clean: ## Limpiar imágenes y contenedores sin usar
	@echo "$(COLOR_BOLD)Limpiando imágenes y contenedores sin usar...$(COLOR_RESET)"
	docker system prune -f
	@echo "$(COLOR_GREEN)✓ Limpieza completada$(COLOR_RESET)"

clean-all: ## Limpiar TODO (imágenes, contenedores, volúmenes, build cache) - PELIGROSO
	@echo "$(COLOR_BOLD)$(COLOR_RED)ADVERTENCIA: Esto eliminará TODAS las imágenes y contenedores$(COLOR_RESET)"
	@read -p "¿Estás seguro? [y/N] " -n 1 -r; \
	echo ""; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker system prune -a -f --volumes; \
		echo "$(COLOR_GREEN)✓ Limpieza completa realizada$(COLOR_RESET)"; \
	else \
		echo "$(COLOR_YELLOW)Cancelado$(COLOR_RESET)"; \
	fi

clean-volumes: ## Eliminar volúmenes Docker (PELIGROSO: BORRA DATOS)
	@echo "$(COLOR_BOLD)$(COLOR_RED)ADVERTENCIA: Esto eliminará todos los volúmenes y datos$(COLOR_RESET)"
	@read -p "¿Estás seguro? [y/N] " -n 1 -r; \
	echo ""; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker volume prune -f; \
		echo "$(COLOR_GREEN)✓ Volúmenes eliminados$(COLOR_RESET)"; \
	else \
		echo "$(COLOR_YELLOW)Cancelado$(COLOR_RESET)"; \
	fi

rebuild: ## Reconstruir imagen y reiniciar servicios
	@echo "$(COLOR_BOLD)Reconstruyendo y reiniciando...$(COLOR_RESET)"
	$(MAKE) build-no-cache
	$(MAKE) down
	$(MAKE) up
	@echo "$(COLOR_GREEN)✓ Reconstrucción completada$(COLOR_RESET)"

rebuild-dev: ## Reconstruir imagen de desarrollo y reiniciar
	@echo "$(COLOR_BOLD)Reconstruyendo y reiniciando (desarrollo)...$(COLOR_RESET)"
	$(MAKE) build-dev-no-cache
	$(MAKE) down-dev
	$(MAKE) up-dev
	@echo "$(COLOR_GREEN)✓ Reconstrucción de desarrollo completada$(COLOR_RESET)"

# ----------------------------------------------------------------------------
# OBJETIVOS DE INSTALACIÓN LOCAL (SIN DOCKER)
# ----------------------------------------------------------------------------

install-dev: ## Instalar dependencias de desarrollo localmente
	@echo "$(COLOR_BOLD)Instalando dependencias de desarrollo...$(COLOR_RESET)"
	pip install -r requirements-dev.txt
	@echo "$(COLOR_GREEN)✓ Dependencias de desarrollo instaladas$(COLOR_RESET)"

install-prod: ## Instalar dependencias de producción localmente
	@echo "$(COLOR_BOLD)Instalando dependencias de producción...$(COLOR_RESET)"
	pip install -r requirements.txt
	@echo "$(COLOR_GREEN)✓ Dependencias de producción instaladas$(COLOR_RESET)"

# ----------------------------------------------------------------------------
# OBJETIVOS DE CALIDAD DE CÓDIGO (LINT/FORMAT)
# ----------------------------------------------------------------------------

format: ## Formatear código con black y ruff
	@echo "$(COLOR_BOLD)Formateando código...$(COLOR_RESET)"
	black src/mcp_hub tests/
	ruff check --fix src/mcp_hub tests/
	@echo "$(COLOR_GREEN)✓ Código formateado$(COLOR_RESET)"

format-check: ## Verificar formato (sin modificar archivos)
	@echo "$(COLOR_BOLD)Verificando formato...$(COLOR_RESET)"
	black --check src/mcp_hub tests/
	ruff check src/mcp_hub tests/

lint: ## Ejecutar linters (ruff y mypy)
	@echo "$(COLOR_BOLD)Ejecutando linters...$(COLOR_RESET)"
	@echo "$(COLOR_BLUE)Ruff...$(COLOR_RESET)"
	ruff check src/mcp_hub tests/
	@echo "$(COLOR_BLUE)MyPy...$(COLOR_RESET)"
	mypy src/mcp_hub
	@echo "$(COLOR_GREEN)✓ Linters completados$(COLOR_RESET)"

lint-ruff: ## Ejecutar solo ruff
	@echo "$(COLOR_BOLD)Ejecutando ruff...$(COLOR_RESET)"
	ruff check src/mcp_hub tests/

lint-mypy: ## Ejecutar solo mypy
	@echo "$(COLOR_BOLD)Ejecutando mypy...$(COLOR_RESET)"
	mypy src/mcp_hub

lint-all: format lint ## Ejecutar todos los checks de calidad (format + lint)

type-check: ## Alias para lint (type checking)
	@$(MAKE) lint

# ----------------------------------------------------------------------------
# OBJETIVOS DE COBERTURA Y MÉTRICAS
# ----------------------------------------------------------------------------

coverage: ## Ejecutar tests con cobertura de código
	@echo "$(COLOR_BOLD)Ejecutando tests con cobertura...$(COLOR_RESET)"
	pytest --cov=mcp_hub --cov-report=html --cov-report=term
	@echo "$(COLOR_GREEN)✓ Tests completados. Reporte de cobertura en htmlcov/index.html$(COLOR_RESET)"

coverage-html: ## Generar reporte HTML de cobertura
	@echo "$(COLOR_BOLD)Generando reporte HTML de cobertura...$(COLOR_RESET)"
	pytest --cov=mcp_hub --cov-report=html
	@echo "$(COLOR_GREEN)✓ Reporte generado en htmlcov/index.html$(COLOR_RESET)"

# ----------------------------------------------------------------------------
# OBJETIVOS DE DESPLIEGUE (DEPLOY)
# ----------------------------------------------------------------------------

push-images: ## Push de imágenes a Docker registry
	@echo "$(COLOR_BOLD)Haciendo push de imágenes...$(COLOR_RESET)"
	docker push mcp-hub:0.1.0
	docker push mcp-hub:dev
	@echo "$(COLOR_GREEN)✓ Imágenes pushadas$(COLOR_RESET)"

deploy: ## Desplegar a producción (reconstruir y subir)
	@echo "$(COLOR_BOLD)Desplegando a producción...$(COLOR_RESET)"
	$(MAKE) build
	$(MAKE) push-images
	@echo "$(COLOR_GREEN)✓ Despliegue completado$(COLOR_RESET)"

deploy-dev: ## Desplegar a desarrollo
	@echo "$(COLOR_BOLD)Desplegando a desarrollo...$(COLOR_RESET)"
	$(MAKE) build-dev
	@echo "$(COLOR_GREEN)✓ Despliegue de desarrollo completado$(COLOR_RESET)"

# ----------------------------------------------------------------------------
# OBJETIVOS DE INFORMACIÓN
# ----------------------------------------------------------------------------

info: ## Mostrar información del entorno
	@echo "$(COLOR_BOLD)Información del entorno:$(COLOR_RESET)"
	@echo ""
	@echo "$(COLOR_BLUE)Docker:$(COLOR_RESET)"
	@docker --version
	@echo ""
	@echo "$(COLOR_BLUE)Docker Compose:$(COLOR_RESET)"
	@docker-compose --version
	@echo ""
	@echo "$(COLOR_BLUE)Python:$(COLOR_RESET)"
	@python --version
	@echo ""
	@echo "$(COLOR_BLUE)Imágenes disponibles:$(COLOR_RESET)"
	@docker images | grep mcp-hub || echo "  No hay imágenes de mcp-hub"
	@echo ""
	@echo "$(COLOR_BLUE)Volúmenes:$(COLOR_RESET)"
	@docker volume ls | grep mcp-hub || echo "  No hay volúmenes de mcp-hub"
	@echo ""
	@echo "$(COLOR_BLUE)Redes:$(COLOR_RESET)"
	@docker network ls | grep mcp-hub || echo "  No hay redes de mcp-hub"

show-config: ## Mostrar configuración de Docker Compose
	@echo "$(COLOR_BOLD)Configuración de Docker Compose:$(COLOR_RESET)"
	docker-compose config

show-dev-config: ## Mostrar configuración de Docker Compose de desarrollo
	@echo "$(COLOR_BOLD)Configuración de Docker Compose (desarrollo):$(COLOR_RESET)"
	docker-compose -f docker-compose.dev.yml config

show-prod-config: ## Mostrar configuración de Docker Compose de producción
	@echo "$(COLOR_BOLD)Configuración de Docker Compose (producción):$(COLOR_RESET)"
	docker-compose -f docker-compose.prod.yml config

# ----------------------------------------------------------------------------
# OBJETIVOS DE DOCUMENTACIÓN
# ----------------------------------------------------------------------------

docs: ## Generar documentación (si hay Sphinx/MkDocs configurado)
	@echo "$(COLOR_BOLD)Generando documentación...$(COLOR_RESET)"
	@if [ -d "docs" ]; then \
		cd docs && make html; \
		echo "$(COLOR_GREEN)✓ Documentación generada en docs/_build/html/index.html$(COLOR_RESET)"; \
	else \
		echo "$(COLOR_YELLOW)No hay directorio 'docs'$(COLOR_RESET)"; \
	fi

# ----------------------------------------------------------------------------
# OBJETIVOS DE DESARROLLO RÁPIDO (WORKFLOWS COMUNES)
# ----------------------------------------------------------------------------

dev: build-dev up-dev-detached ## Flujo completo de desarrollo (construir + iniciar)

dev-with-db: build-dev up-dev-with-db ## Flujo de desarrollo con PostgreSQL

reset: down-v build up ## Flujo completo de reset (limpiar + construir + iniciar)

reset-dev: down-v build-dev up-dev ## Flujo completo de reset de desarrollo
