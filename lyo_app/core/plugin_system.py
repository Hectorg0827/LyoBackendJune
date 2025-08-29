"""
Plugin System for LyoApp Backend
-------------------------------
Provides a modular architecture that allows functionality to be added
or removed without modifying the core codebase.

Features:
- Dynamic plugin loading
- Plugin lifecycle management
- Plugin configuration
- Event-based communication between plugins
"""

import importlib
import inspect
import logging
import pkgutil
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Type, TypeVar, Union

from fastapi import FastAPI, APIRouter

# Configure logger
logger = logging.getLogger(__name__)


class PluginState(str, Enum):
    """Possible states of a plugin."""
    
    REGISTERED = "registered"
    INITIALIZED = "initialized"
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class PluginEvent(str, Enum):
    """Events that can be emitted by the plugin system."""
    
    # Lifecycle events
    INIT = "plugin.init"
    START = "plugin.start"
    STOP = "plugin.stop"
    ENABLE = "plugin.enable"
    DISABLE = "plugin.disable"
    
    # Data events
    DATA_CREATED = "plugin.data.created"
    DATA_UPDATED = "plugin.data.updated"
    DATA_DELETED = "plugin.data.deleted"
    
    # Error events
    ERROR = "plugin.error"


class Plugin(ABC):
    """Base class for all plugins."""
    
    def __init__(self):
        """Initialize plugin."""
        self.name = self.__class__.__name__
        self.state = PluginState.REGISTERED
        self.version = "1.0.0"
        self.description = ""
        self.dependencies: List[str] = []
        self.router: Optional[APIRouter] = None
        self.config: Dict[str, Any] = {}
        self.error: Optional[Exception] = None
    
    @abstractmethod
    async def initialize(self, app: FastAPI) -> bool:
        """Initialize the plugin."""
        pass
    
    @abstractmethod
    async def start(self) -> bool:
        """Start the plugin."""
        pass
    
    @abstractmethod
    async def stop(self) -> bool:
        """Stop the plugin."""
        pass
    
    async def enable(self) -> bool:
        """Enable the plugin."""
        if self.state == PluginState.DISABLED:
            success = await self.start()
            if success:
                self.state = PluginState.ACTIVE
                return True
        return False
    
    async def disable(self) -> bool:
        """Disable the plugin."""
        if self.state == PluginState.ACTIVE:
            success = await self.stop()
            if success:
                self.state = PluginState.DISABLED
                return True
        return False
    
    def get_router(self) -> Optional[APIRouter]:
        """Get the plugin's router."""
        return self.router
    
    def set_config(self, config: Dict[str, Any]) -> None:
        """Set the plugin configuration."""
        self.config = config
    
    def get_state(self) -> PluginState:
        """Get the plugin's state."""
        return self.state
    
    def get_info(self) -> Dict[str, Any]:
        """Get plugin information."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "state": self.state,
            "dependencies": self.dependencies,
            "error": str(self.error) if self.error else None
        }


# Type for event handlers
T = TypeVar('T')
EventHandler = Callable[[Any], None]


class PluginManager:
    """Manages plugin lifecycle and communication."""
    
    def __init__(self):
        """Initialize plugin manager."""
        self.plugins: Dict[str, Plugin] = {}
        self.event_handlers: Dict[PluginEvent, List[EventHandler]] = {}
    
    def register_plugin(self, plugin: Plugin) -> bool:
        """Register a plugin with the manager."""
        if plugin.name in self.plugins:
            logger.warning(f"Plugin '{plugin.name}' already registered")
            return False
        
        self.plugins[plugin.name] = plugin
        logger.info(f"Plugin '{plugin.name}' registered")
        return True
    
    async def initialize_plugin(self, plugin_name: str, app: FastAPI, config: Dict[str, Any] = None) -> bool:
        """Initialize a plugin."""
        if plugin_name not in self.plugins:
            logger.warning(f"Plugin '{plugin_name}' not registered")
            return False
        
        plugin = self.plugins[plugin_name]
        
        # Set configuration if provided
        if config:
            plugin.set_config(config)
        
        # Check dependencies
        for dependency in plugin.dependencies:
            if dependency not in self.plugins or self.plugins[dependency].state != PluginState.ACTIVE:
                logger.error(f"Plugin '{plugin_name}' dependency '{dependency}' not available")
                plugin.state = PluginState.ERROR
                plugin.error = ValueError(f"Dependency '{dependency}' not available")
                return False
        
        try:
            # Initialize the plugin
            success = await plugin.initialize(app)
            if success:
                plugin.state = PluginState.INITIALIZED
                logger.info(f"Plugin '{plugin_name}' initialized")
                
                # Register router if available
                router = plugin.get_router()
                if router:
                    app.include_router(router)
                    logger.info(f"Plugin '{plugin_name}' router registered")
                
                # Emit initialization event
                self.emit_event(PluginEvent.INIT, plugin_name)
                
                return True
            else:
                logger.warning(f"Plugin '{plugin_name}' initialization failed")
                return False
        except Exception as e:
            logger.exception(f"Error initializing plugin '{plugin_name}': {e}")
            plugin.state = PluginState.ERROR
            plugin.error = e
            return False
    
    async def start_plugin(self, plugin_name: str) -> bool:
        """Start a plugin."""
        if plugin_name not in self.plugins:
            logger.warning(f"Plugin '{plugin_name}' not registered")
            return False
        
        plugin = self.plugins[plugin_name]
        if plugin.state != PluginState.INITIALIZED:
            logger.warning(f"Plugin '{plugin_name}' not initialized")
            return False
        
        try:
            success = await plugin.start()
            if success:
                plugin.state = PluginState.ACTIVE
                logger.info(f"Plugin '{plugin_name}' started")
                
                # Emit start event
                self.emit_event(PluginEvent.START, plugin_name)
                
                return True
            else:
                logger.warning(f"Plugin '{plugin_name}' start failed")
                return False
        except Exception as e:
            logger.exception(f"Error starting plugin '{plugin_name}': {e}")
            plugin.state = PluginState.ERROR
            plugin.error = e
            return False
    
    async def stop_plugin(self, plugin_name: str) -> bool:
        """Stop a plugin."""
        if plugin_name not in self.plugins:
            logger.warning(f"Plugin '{plugin_name}' not registered")
            return False
        
        plugin = self.plugins[plugin_name]
        if plugin.state != PluginState.ACTIVE:
            logger.warning(f"Plugin '{plugin_name}' not active")
            return False
        
        try:
            success = await plugin.stop()
            if success:
                plugin.state = PluginState.DISABLED
                logger.info(f"Plugin '{plugin_name}' stopped")
                
                # Emit stop event
                self.emit_event(PluginEvent.STOP, plugin_name)
                
                return True
            else:
                logger.warning(f"Plugin '{plugin_name}' stop failed")
                return False
        except Exception as e:
            logger.exception(f"Error stopping plugin '{plugin_name}': {e}")
            plugin.error = e
            return False
    
    def get_plugin(self, plugin_name: str) -> Optional[Plugin]:
        """Get a plugin by name."""
        return self.plugins.get(plugin_name)
    
    def get_all_plugins(self) -> Dict[str, Plugin]:
        """Get all registered plugins."""
        return self.plugins.copy()
    
    def get_active_plugins(self) -> Dict[str, Plugin]:
        """Get all active plugins."""
        return {name: plugin for name, plugin in self.plugins.items() if plugin.state == PluginState.ACTIVE}
    
    def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get plugin information."""
        plugin = self.get_plugin(plugin_name)
        return plugin.get_info() if plugin else None
    
    def get_all_plugin_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information for all plugins."""
        return {name: plugin.get_info() for name, plugin in self.plugins.items()}
    
    def register_event_handler(self, event: PluginEvent, handler: EventHandler) -> None:
        """Register an event handler."""
        if event not in self.event_handlers:
            self.event_handlers[event] = []
        
        self.event_handlers[event].append(handler)
    
    def unregister_event_handler(self, event: PluginEvent, handler: EventHandler) -> bool:
        """Unregister an event handler."""
        if event not in self.event_handlers:
            return False
        
        try:
            self.event_handlers[event].remove(handler)
            return True
        except ValueError:
            return False
    
    def emit_event(self, event: PluginEvent, *args: Any, **kwargs: Any) -> None:
        """Emit an event to all registered handlers."""
        if event not in self.event_handlers:
            return
        
        for handler in self.event_handlers[event]:
            try:
                handler(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Error in event handler for {event}: {e}")
    
    async def discover_plugins(self, plugins_package: str) -> List[str]:
        """Discover plugins in a package."""
        discovered = []
        
        try:
            package = importlib.import_module(plugins_package)
            package_path = Path(package.__file__).parent
            
            for _, name, ispkg in pkgutil.iter_modules([str(package_path)]):
                if ispkg:
                    try:
                        module = importlib.import_module(f"{plugins_package}.{name}")
                        for item_name in dir(module):
                            item = getattr(module, item_name)
                            if (
                                inspect.isclass(item)
                                and issubclass(item, Plugin)
                                and item != Plugin
                            ):
                                plugin = item()
                                if self.register_plugin(plugin):
                                    discovered.append(plugin.name)
                    except Exception as e:
                        logger.exception(f"Error discovering plugin '{name}': {e}")
        except Exception as e:
            logger.exception(f"Error discovering plugins in package '{plugins_package}': {e}")
        
        return discovered
    
    async def initialize_all_plugins(self, app: FastAPI, configs: Dict[str, Dict[str, Any]] = None) -> Dict[str, bool]:
        """Initialize all registered plugins."""
        results = {}
        
        for plugin_name in self.plugins:
            config = configs.get(plugin_name, {}) if configs else {}
            results[plugin_name] = await self.initialize_plugin(plugin_name, app, config)
        
        return results
    
    async def start_all_plugins(self) -> Dict[str, bool]:
        """Start all initialized plugins."""
        results = {}
        
        for plugin_name, plugin in self.plugins.items():
            if plugin.state == PluginState.INITIALIZED:
                results[plugin_name] = await self.start_plugin(plugin_name)
        
        return results
    
    async def stop_all_plugins(self) -> Dict[str, bool]:
        """Stop all active plugins."""
        results = {}
        
        for plugin_name, plugin in self.plugins.items():
            if plugin.state == PluginState.ACTIVE:
                results[plugin_name] = await self.stop_plugin(plugin_name)
        
        return results


# Global plugin manager instance
plugin_manager = PluginManager()


# Example plugin implementation
class ExamplePlugin(Plugin):
    """Example plugin implementation."""
    
    def __init__(self):
        """Initialize example plugin."""
        super().__init__()
        self.name = "ExamplePlugin"
        self.version = "1.0.0"
        self.description = "An example plugin"
        self.router = APIRouter(prefix="/example", tags=["example"])
        
        # Define routes
        @self.router.get("/")
        async def get_example():
            return {"message": "This is an example plugin"}
    
    async def initialize(self, app: FastAPI) -> bool:
        """Initialize the plugin."""
        logger.info("Initializing ExamplePlugin")
        return True
    
    async def start(self) -> bool:
        """Start the plugin."""
        logger.info("Starting ExamplePlugin")
        return True
    
    async def stop(self) -> bool:
        """Stop the plugin."""
        logger.info("Stopping ExamplePlugin")
        return True


# Export for use throughout the application
__all__ = [
    'Plugin',
    'PluginState',
    'PluginEvent',
    'PluginManager',
    'plugin_manager',
    'ExamplePlugin',
]
