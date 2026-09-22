"""Registry of built-in category handlers, resolved from a schema's
`handler:` field (see SPECS.md, "Category handlers"). Shared by
`core.lint` and the CLI wizard — neither should duplicate this
resolution logic."""

import importlib

from .base import CategoryHandler, HandlerContext
from .generic import GenericHandler
from .publications import PublicationsHandler

BUILTIN_HANDLERS = {
    "generic": GenericHandler,
    "publications": PublicationsHandler,
}


def load_handler(schema, context: HandlerContext) -> CategoryHandler:
    handler_name = schema.handler
    if ":" in handler_name:
        module_name, class_name = handler_name.split(":")
        module = importlib.import_module(module_name)
        handler_cls = getattr(module, class_name)
    else:
        handler_cls = BUILTIN_HANDLERS[handler_name]
    return handler_cls(schema, context)
