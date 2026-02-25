"""Project logging package that proxies the standard library logging module.

This avoids name conflicts by executing the stdlib logging package in this
namespace, while still allowing project-specific logging utilities.
"""

import os as _os

# Make stdlib logging submodules available for relative imports.
_stdlib_dir = _os.path.dirname(_os.__file__)
_stdlib_logging_dir = _os.path.join(_stdlib_dir, "logging")
if _stdlib_logging_dir not in __path__:
    __path__.append(_stdlib_logging_dir)

_stdlib_init = _os.path.join(_stdlib_logging_dir, "__init__.py")
with open(_stdlib_init, "r", encoding="utf-8") as _f:
    _code = _f.read()

exec(compile(_code, _stdlib_init, "exec"), globals())
