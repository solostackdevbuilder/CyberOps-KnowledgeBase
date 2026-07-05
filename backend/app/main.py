"""
Main FastAPI application for CyberOps Knowledge Base.
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import settings
from app.routes_settings import router as settings_router
from app.core.startup_guards import check_network_binding_policy
from app.core.storage.settings_store import SettingsStore
from app.core.storage.storage_factory import get_storage, clear_storage_cache
from app.core.services.llm_factory import get_llm_service, clear_llm_cache
from app.core.teams.registry import TeamRegistry
from app.core.plugins.registry import PluginRegistry

# Fail fast before any port binds or route registers if the deployment
# declares a public network bind without explicitly acknowledging that
# an authenticating reverse proxy is in front. See startup_guards.py.
check_network_binding_policy()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown tasks.

    - Startup: Load settings, initialize storage, LLM, and teams
    - Shutdown: Cleanup connections and teams
    """
    # Startup: Load settings and initialize storage/LLM
    settings_store = SettingsStore()
    try:
        app_settings = await settings_store.load_settings()
        print(f"[OK] Settings loaded: storage={app_settings.storage_backend.value}, llm={app_settings.llm_provider.value}")

        # Initialize storage
        storage = get_storage(app_settings)
        await storage._ensure_directories() if hasattr(storage, "_ensure_directories") else None
        print("[OK] Storage initialized")

        # Initialize LLM (optional, may fail if not configured)
        try:
            llm_service = get_llm_service(app_settings, storage=storage)
            print("[OK] LLM service initialized")
        except Exception as e:
            print(f"[WARN] LLM service not available: {e}")

        # Run team startup hooks
        await team_registry.startup_all()
        print(f"[OK] {len(team_registry)} team(s) initialized")

        # Initialize plugins (pre-loaded at app creation, now async init)
        await plugin_registry.initialize_all()
        print(f"[OK] {len(plugin_registry)} plugin(s) initialized")

        # Store in app state for access in routes
        app.state.settings = app_settings
        app.state.storage = storage
        app.state.llm_service = llm_service if 'llm_service' in locals() else None
        app.state.team_registry = team_registry
        app.state.plugin_registry = plugin_registry

        # Verify routes are registered (after app is fully initialized)
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        red_team_routes = [r for r in routes if '/operations' in r or '/sessions' in r or '/query' in r or '/insights' in r]
        print(f"[OK] Registered {len(red_team_routes)} red team routes")
        if len(red_team_routes) == 0:
            print("[WARN] No red team routes found! Check router configuration.")
        else:
            print(f"   Sample routes: {red_team_routes[:5]}")

    except Exception as e:
        print(f"[ERROR] Failed to initialize application: {e}")
        # Don't raise - allow app to start with defaults
        pass

    yield

    # Shutdown: Cleanup plugins, teams, and connections
    try:
        await plugin_registry.shutdown_all()
        await team_registry.shutdown_all()
        clear_storage_cache()
        clear_llm_cache()
        print("[OK] Cleaned up connections")
    except Exception as e:
        print(f"[WARN] Error during cleanup: {e}")
    print("Shutting down...")


# Create FastAPI app
app = FastAPI(
    title="CyberOps Knowledge Base API",
    description="API for managing cyber operations session data and querying with AI",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS for frontend (allow any localhost origin for flexible port assignment)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Audit log middleware - appends one JSONL line per state-changing
# request to data/audit/. Identity comes from the reverse-proxy's
# X-Forwarded-User / X-Auth-Request-User header (set by the YubiKey
# gate). On a dev box without the gate, identity is "anonymous".
try:
    from app.core.middleware.audit_log import AuditLogMiddleware
    audit_dir = Path(settings.data_dir) / "audit"
    app.add_middleware(AuditLogMiddleware, audit_dir=audit_dir)
    print(f"[OK] Audit log middleware enabled, writing to {audit_dir}")
except Exception as e:
    print(f"[WARN] Audit log middleware not enabled: {e}")

# Register custom exception handlers for granular error responses
try:
    from app.core.error_handlers import register_exception_handlers
    register_exception_handlers(app)
    print("[OK] Registered custom exception handlers")
except ImportError as e:
    print(f"[WARN] Could not register custom exception handlers: {e}")

# Include settings router
app.include_router(settings_router)

# ============================================================================
# Team Registry - register all available teams
# ============================================================================
team_registry = TeamRegistry()

try:
    from app.modules.red_team.team import RedTeam
    team_registry.register(RedTeam())
except ImportError as e:
    print(f"[ERROR] Failed to register Red Team: {e}")
    import traceback
    traceback.print_exc()

# Register team-specific routes (e.g., detection_strategies for Red Team)
for router in team_registry.get_all_routes():
    app.include_router(router)
    print(f"[OK] Loaded team route: {router.prefix}")

# Load shared red team routes (operations, sessions, query, insights, FAA)
# These routes live under the red_team module.
try:
    from app.modules.red_team.routes import (
        operations_router,
        sessions_router,
        query_router,
        insights_router,
        faa_router,
    )
    app.include_router(operations_router)
    app.include_router(sessions_router)
    app.include_router(query_router)
    app.include_router(insights_router)
    app.include_router(faa_router)
    print("[OK] Loaded shared routes (operations, sessions, query, insights, FAA)")
except ImportError as e:
    print(f"[ERROR] Failed to import shared routes: {e}")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"[ERROR] Failed to load shared routes: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# Plugin Registry - discover and pre-load plugins for route registration
# ============================================================================
plugin_registry = PluginRegistry(
    plugins_dir=Path(__file__).parent / "plugins",
    data_dir=Path(settings.data_dir),
)

# Pre-load plugins synchronously so routes can be registered at app creation.
# The async initialize() is called later during lifespan startup.
plugin_registry.preload_all()

# Register plugin routes
for router in plugin_registry.get_all_routes():
    app.include_router(router)
    print(f"[OK] Loaded plugin route: {router.prefix}")

# Platform manifest endpoint
@app.get("/api/platform/manifest")
async def get_platform_manifest():
    """Return platform manifest with registered teams and plugins."""
    manifest = team_registry.get_platform_manifest()
    manifest["plugins"] = plugin_registry.get_manifests()
    return manifest

# Load timeline and commands routes
try:
    from app.modules.red_team.routes_timeline import timeline_router, commands_router
    app.include_router(timeline_router)
    app.include_router(commands_router)
    print(f"[OK] Loaded Timeline router: {timeline_router.prefix}")
    print(f"[OK] Loaded Commands router: {commands_router.prefix}")
except ImportError as e:
    print(f"[WARN] Timeline/Commands routes not available: {e}")
except Exception as e:
    print(f"[WARN] Failed to load Timeline/Commands routes: {e}")


@app.get("/api/health")
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        Health status
    """
    return {
        "status": "healthy",
        "service": "CyberOps Knowledge Base API",
        "version": "1.0.0"
    }


def _serve_frontend_enabled() -> bool:
    return os.getenv("SERVE_FRONTEND", "").lower() in ("1", "true", "yes")


def _frontend_dist_path() -> Path:
    return Path(os.getenv("FRONTEND_DIST", "static"))


def _spa_should_fallback(full_path: str) -> bool:
    """Paths that must not return index.html (handled by API or OpenAPI)."""
    if full_path.startswith("api/"):
        return False
    if full_path.startswith("docs"):
        return False
    if full_path in ("openapi.json", "redoc"):
        return False
    return True


_frontend_dist = _frontend_dist_path()
_index_file = _frontend_dist / "index.html"

if _serve_frontend_enabled() and _frontend_dist.is_dir() and _index_file.is_file():

    @app.get("/")
    async def root():
        return FileResponse(_index_file)

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if not _spa_should_fallback(full_path):
            raise HTTPException(status_code=404)
        base = _frontend_dist.resolve()
        candidate = (_frontend_dist / full_path).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            return FileResponse(_index_file)
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_index_file)

else:

    @app.get("/")
    async def root():
        """
        Root endpoint with API information.

        Returns:
            API information
        """
        all_routes = []
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                all_routes.append({
                    "path": route.path,
                    "methods": list(route.methods)
                })

        red_team_routes = [r for r in all_routes if any(x in r["path"] for x in ["/operations", "/sessions", "/query", "/insights"])]

        return {
            "message": "CyberOps Knowledge Base API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/api/health",
            "total_routes": len(all_routes),
            "red_team_routes": red_team_routes
        }

