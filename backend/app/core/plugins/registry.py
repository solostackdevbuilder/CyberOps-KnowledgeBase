"""
Plugin registry - discovers, loads, and manages plugins.
"""
import importlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter

from app.core.plugins.base import PluginBase, PluginManifest, UIPlugin
from app.core.plugins.capabilities import check_declared
from app.core.plugins.signing import enforce as enforce_signature

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Central registry for all plugins.

    Discovers plugins from a directory, loads them dynamically,
    and manages their lifecycle (init, shutdown, routes).
    """

    def __init__(self, plugins_dir: Path, data_dir: Path):
        self.plugins_dir = plugins_dir
        self.data_dir = data_dir
        self._plugins: Dict[str, PluginBase] = {}
        self._manifests: Dict[str, PluginManifest] = {}

    async def discover(self) -> List[str]:
        """Find all plugins with valid manifest.json in the plugins directory."""
        if not self.plugins_dir.exists():
            logger.info(f"Plugins directory does not exist: {self.plugins_dir}")
            return []

        found = []
        for d in self.plugins_dir.iterdir():
            if d.is_dir() and (d / "manifest.json").exists():
                found.append(d.name)
        logger.info(f"Discovered {len(found)} plugin(s): {found}")
        return found

    def _load_manifest(self, name: str) -> PluginManifest:
        """Load and validate a plugin's manifest.json.

        - Verifies every declared capability is a known name (typo
          detection).
        - Verifies the plugin's Ed25519 signature against the trust
          anchors configured in the environment. Policy (off|warn|strict)
          comes from CYBEROPS_PLUGIN_SIGNATURE_POLICY; default is off so
          existing deployments keep loading unsigned plugins. If policy
          is strict and verification fails, raises RuntimeError - the
          registry's caller catches it and skips the plugin.
        """
        manifest_path = self.plugins_dir / name / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        manifest = PluginManifest(**data)
        check_declared(manifest)

        plugin_dir = self.plugins_dir / name
        # Verify against the raw on-disk dict, not the PluginManifest -
        # Pydantic adds default-None fields that would drift the canonical
        # bytes the signer hashed.
        verification = enforce_signature(plugin_dir, data)
        if not verification.ok:
            raise RuntimeError(
                f"Plugin '{name}' failed signature verification: "
                f"{verification.reason}"
            )

        return manifest

    def _find_plugin_class(self, module) -> type:
        """Find the PluginBase subclass in a loaded module."""
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, PluginBase)
                and attr is not PluginBase
                and not attr.__name__.startswith("_")
            ):
                # Skip base classes imported into the module
                if attr.__module__ == module.__name__:
                    return attr
        raise ValueError(f"No PluginBase subclass found in {module.__name__}")

    async def load(self, name: str, plugin_settings: dict) -> PluginBase:
        """Load, validate, and initialize a single plugin.

        Args:
            name: Plugin directory name
            plugin_settings: Settings dict for this plugin
        """
        if name in self._plugins:
            return self._plugins[name]

        logger.info(f"Loading plugin: {name}")

        # Load manifest
        manifest = self._load_manifest(name)
        self._manifests[name] = manifest

        # Dynamic import: app.plugins.<name>.plugin
        module_path = f"app.plugins.{name}.plugin"
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            raise RuntimeError(
                f"Failed to import plugin '{name}' from {module_path}: {e}"
            )

        # Find and instantiate plugin class
        plugin_class = self._find_plugin_class(module)
        plugin = plugin_class()
        plugin.manifest = manifest

        # Initialize with settings
        settings_for_plugin = plugin_settings.get(name, {})
        await plugin.initialize(settings_for_plugin)

        self._plugins[name] = plugin
        logger.info(f"Plugin '{name}' loaded successfully (type: {manifest.plugin_type.value})")
        return plugin

    def preload_all(self) -> None:
        """Synchronous pre-load: discover plugins, import classes, get routes.

        This runs at app creation time (before lifespan) so that FastAPI
        can register plugin routes. The async initialize() runs later
        during the lifespan startup phase via initialize_all().
        """
        if not self.plugins_dir.exists():
            return

        for d in self.plugins_dir.iterdir():
            if not d.is_dir() or not (d / "manifest.json").exists():
                continue
            name = d.name
            try:
                manifest = self._load_manifest(name)
                self._manifests[name] = manifest

                module_path = f"app.plugins.{name}.plugin"
                module = importlib.import_module(module_path)
                plugin_class = self._find_plugin_class(module)

                plugin = plugin_class()
                plugin.manifest = manifest
                self._plugins[name] = plugin
                logger.info(f"Pre-loaded plugin: {name} (routes ready, not yet initialized)")
            except Exception as e:
                logger.error(f"Failed to pre-load plugin '{name}': {e}")

    async def initialize_all(self, plugin_settings: Optional[dict] = None) -> None:
        """Async initialization of all pre-loaded plugins.

        Called during lifespan startup after preload_all().
        """
        settings = plugin_settings or {}
        for name, plugin in self._plugins.items():
            try:
                await plugin.initialize(settings.get(name, {}))
                logger.info(f"Plugin '{name}' initialized")
            except Exception as e:
                logger.error(f"Plugin '{name}' initialization failed: {e}")

    async def load_all_enabled(self, enabled_plugins: Optional[List[str]] = None, plugin_settings: Optional[dict] = None) -> None:
        """Load all enabled plugins.

        Args:
            enabled_plugins: List of plugin names to enable. None = all discovered.
            plugin_settings: Dict of {plugin_name: {settings}} for each plugin.
        """
        discovered = await self.discover()
        if not discovered:
            return

        to_load = enabled_plugins if enabled_plugins is not None else discovered
        settings = plugin_settings or {}

        # Load UI plugins first (they may add middleware that must run before tool routes)
        ui_plugins = []
        other_plugins = []
        for name in to_load:
            if name not in discovered:
                logger.warning(f"Plugin '{name}' enabled but not found in {self.plugins_dir}")
                continue
            try:
                manifest = self._load_manifest(name)
                if manifest.plugin_type.value == "ui":
                    ui_plugins.append(name)
                else:
                    other_plugins.append(name)
            except Exception as e:
                logger.error(f"Failed to read manifest for plugin '{name}': {e}")

        for name in ui_plugins + other_plugins:
            try:
                await self.load(name, settings)
            except Exception as e:
                logger.error(f"Failed to load plugin '{name}': {e}")

    def get(self, name: str) -> Optional[PluginBase]:
        """Get a loaded plugin by name."""
        return self._plugins.get(name)

    def get_all_routes(self) -> List[APIRouter]:
        """Collect API routers from all loaded plugins."""
        routes = []
        for plugin in self._plugins.values():
            router = plugin.get_routes()
            if router:
                routes.append(router)
        return routes

    def get_all_middleware(self) -> list:
        """Collect middleware from UI plugins."""
        middleware = []
        for plugin in self._plugins.values():
            if isinstance(plugin, UIPlugin):
                mw = plugin.get_middleware()
                if mw:
                    middleware.extend(mw)
        return middleware

    def get_manifests(self) -> List[dict]:
        """Return frontend manifests for all loaded plugins."""
        manifests = []
        for plugin in self._plugins.values():
            try:
                manifests.append(plugin.get_frontend_manifest())
            except Exception as e:
                logger.error(f"Failed to get manifest from plugin '{plugin.manifest.id}': {e}")
        return manifests

    async def shutdown_all(self) -> None:
        """Shutdown all loaded plugins."""
        for name, plugin in self._plugins.items():
            try:
                await plugin.shutdown()
                logger.info(f"Plugin '{name}' shut down")
            except Exception as e:
                logger.error(f"Plugin '{name}' shutdown failed: {e}")

    def __len__(self) -> int:
        return len(self._plugins)

    def __contains__(self, name: str) -> bool:
        return name in self._plugins
