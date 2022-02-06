"""General utils and base classes used in the library."""

import datetime
import inspect
import json
import logging
import sys
import traceback
from enum import Enum
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from typing import Callable, TypeVar

    from typing_extensions import Concatenate, ParamSpec

    _T = TypeVar("_T")
    _R = TypeVar("_R")
    _P = ParamSpec("_P")
_LOGGER = logging.getLogger(__name__)


JSON_IGNORED_KEYS = ["account", "_account", "vehicle", "_vehicle", "status", "remote_services"]
JSON_DEPRECATED_KEYS = [
    "has_hv_battery",
    "has_range_extender",
    "has_internal_combustion_engine",
    "has_weekly_planner_service",
]


def get_class_property_names(obj: object):
    """Returns the names of all properties of a class."""
    return [p[0] for p in inspect.getmembers(type(obj), inspect.isdatadescriptor) if not p[0].startswith("_")]


def parse_datetime(date_str: str) -> Optional[datetime.datetime]:
    """Convert a time string into datetime."""
    if not date_str:
        return None
    date_formats = ["%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"]
    for date_format in date_formats:
        try:
            parsed = datetime.datetime.strptime(date_str, date_format)
            # Assume implicit UTC for Python 3.6
            if sys.version_info < (3, 7):
                parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            return parsed
        except ValueError:
            pass
    _LOGGER.error("unable to parse '%s' using %s", date_str, date_formats)
    return None


class ConnectedDriveJSONEncoder(json.JSONEncoder):
    """JSON Encoder that handles data classes, properties and additional data types."""

    def default(self, o):
        if isinstance(o, (datetime.datetime, datetime.date, datetime.time)):
            return o.isoformat()
        if not isinstance(o, Enum) and hasattr(o, "__dict__") and isinstance(o.__dict__, Dict):
            retval: Dict = o.__dict__
            retval.update({p: getattr(o, p) for p in get_class_property_names(o) if p not in JSON_DEPRECATED_KEYS})
            return {k: v for k, v in retval.items() if k not in JSON_IGNORED_KEYS}
        return str(o)


def deprecated(replacement: str = None):
    """Mark a function or property as deprecated."""

    def decorator(func: "Callable[Concatenate[_T, _P], _R]") -> "Callable[Concatenate[_T, _P], _R | None]":
        def _func_wrapper(self: "_T", *args: "_P.args", **kwargs: "_P.kwargs") -> "_R | None":
            # warnings.simplefilter('always', DeprecationWarning)  # turn off filter
            replacement_text = f" Please change to '{replacement}'." if replacement else ""
            # warnings.warn(f"{func.__qualname__} is deprecated.{replacement_text}",
            # category=DeprecationWarning,
            # stacklevel=2)
            # warnings.simplefilter('default', DeprecationWarning)  # reset filter
            stack = traceback.extract_stack()[-2]
            _LOGGER.warning(
                "DeprecationWarning:%s:%s: '%s' is deprecated.%s",
                stack.filename,
                stack.lineno,
                func.__qualname__,
                replacement_text,
            )
            return func(self, *args, **kwargs)

        return _func_wrapper

    return decorator
