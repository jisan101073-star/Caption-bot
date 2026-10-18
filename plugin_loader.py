"""Safe, file-based plugin discovery for Zinn AI.

Plugins are trusted Python code shipped with the deployment. Drop a .py file into
plugins/, implement register(manager), and redeploy; app.py need not be edited.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

log = logging.getLogger("zinn-ai.plugins")
Handler = Callable[..., Any]


class PluginManager:
    def __init__(self, app: Any, plugin_dir: str | Path = "plugins") -> None:
        self.app = app
        self.plugin_dir = Path(plugin_dir)
        self.handlers: dict[str, list[tuple[str, Handler]]] = {}
        self.plugins: dict[str, Any] = {}
        self.errors: dict[str, str] = {}

    def on(self, event: str, handler: Handler) -> None:
        self.handlers.setdefault(event, []).append((getattr(handler, "__module__", "plugin"), handler))

    def load_all(self) -> dict[str, Any]:
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.plugin_dir.glob("*.py")):
            if path.name.startswith("_") or path.name == "__init__.py":
                continue
            name = path.stem
            try:
                spec = importlib.util.spec_from_file_location(f"zinn_plugins.{name}", path)
                if spec is None or spec.loader is None:
                    raise RuntimeError("Python plugin loader could not create a module spec")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                register = getattr(module, "register", None)
                if not callable(register):
                    raise RuntimeError("Plugin must provide register(manager)")
                register(self)
                self.plugins[name] = module
                log.info("Loaded plugin: %s", name)
            except Exception as exc:
                self.errors[name] = type(exc).__name__
                log.exception("Plugin %s failed to load; other plugins will continue", name)
        log.info("Plugin discovery complete: %d loaded, %d failed", len(self.plugins), len(self.errors))
        return self.plugins

    async def emit(self, event: str, **payload: Any) -> list[Any]:
        results: list[Any] = []
        for plugin_name, handler in list(self.handlers.get(event, [])):
            try:
                result = handler(**payload)
                if hasattr(result, "__await__"):
                    result = await result
                results.append(result)
            except Exception as exc:
                log.warning("Plugin handler failed (%s, %s): %s", plugin_name, event, type(exc).__name__)
        return results

    async def dispatch_first(self, event: str, **payload: Any) -> bool:
        """Dispatch until a handler explicitly returns True (command consumed)."""
        for plugin_name, handler in list(self.handlers.get(event, [])):
            try:
                result = handler(**payload)
                if hasattr(result, "__await__"):
                    result = await result
                if result is True:
                    return True
            except Exception as exc:
                log.warning("Plugin handler failed (%s, %s): %s", plugin_name, event, type(exc).__name__)
        return False
