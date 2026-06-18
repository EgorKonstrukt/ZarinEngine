from __future__ import annotations


class Registry:
    def __init__(self):
        self._tools: dict = {}
        self._resources: dict = {}
        self._resource_templates: dict = {}
        self._prompts: dict = {}

    def tool(self, name: str = "", description: str = "", inputSchema: dict = None):
        def wrapper(func):
            nonlocal name
            if not name:
                name = func.__name__
            self._tools[name] = {
                "description": description,
                "inputSchema": inputSchema or {"type": "object", "properties": {}},
                "handler": func,
            }
            return func
        return wrapper

    def resource(self, uri: str, name: str = "", description: str = "",
                 mimeType: str = "application/json"):
        def wrapper(func):
            self._resources[uri] = {
                "name": name or uri,
                "description": description,
                "mimeType": mimeType,
                "handler": func,
            }
            return func
        return wrapper

    def resource_template(self, uri_template: str, name: str = "", description: str = "",
                          mimeType: str = "application/json"):
        def wrapper(func):
            self._resource_templates[uri_template] = {
                "name": name or uri_template,
                "description": description,
                "mimeType": mimeType,
                "handler": func,
            }
            return func
        return wrapper

    def prompt(self, name: str = "", description: str = "", arguments: list = None):
        def wrapper(func):
            nonlocal name
            if not name:
                name = func.__name__
            self._prompts[name] = {
                "description": description,
                "arguments": arguments or [],
                "handler": func,
            }
            return func
        return wrapper

    @property
    def tools(self) -> dict:
        return self._tools

    @property
    def resources(self) -> dict:
        return self._resources

    @property
    def resource_templates(self) -> dict:
        return self._resource_templates

    @property
    def prompts(self) -> dict:
        return self._prompts
