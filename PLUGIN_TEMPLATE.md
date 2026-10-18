# Adding a plugin without editing app.py

1. Create a new Python file directly in `plugins/`, e.g. `my_feature.py`.
2. Define `register(manager)`.
3. Add a handler through `manager.on("event_name", handler)` or add a FastAPI route with `manager.app.add_api_route(...)`.
4. Redeploy the full repository. `plugin_loader.py` discovers every eligible `.py` file on startup.

Minimal example:

```python
async def on_private_message(message, text, **kwargs):
    # Keep plugin work small and fail safely.
    return None


def register(manager):
    manager.on("private_message", on_private_message)
```

Only deploy trusted Python plugins: each discovered file is executable code. One plugin's startup failure is logged and does not prevent other plugins from loading.
