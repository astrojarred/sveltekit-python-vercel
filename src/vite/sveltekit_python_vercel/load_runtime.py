import inspect
import types
from typing import Any, Optional


class SKPVError(Exception):
    def __init__(self, status: int, body: Any):
        self.status = status
        self.body = body
        super().__init__(body)


class SKPVRedirect(Exception):
    def __init__(self, status: int, location: str):
        self.status = status
        self.location = location
        super().__init__(location)


def error(status: int, body: Any) -> None:
    raise SKPVError(status, body)


def redirect(status: int, location: str) -> None:
    raise SKPVRedirect(status, location)


def inject_load_helpers(mod) -> None:
    if not hasattr(mod, "error"):
        mod.error = error
    if not hasattr(mod, "redirect"):
        mod.redirect = redirect


def _to_namespace(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        ns = types.SimpleNamespace()
        for key, val in value.items():
            setattr(ns, key, _to_namespace(val))
        return ns
    if isinstance(value, list):
        return [_to_namespace(item) for item in value]
    return value


class _Cookies:
    def __init__(self, data: Optional[dict]):
        self._data = data or {}

    def get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        return self._data.get(name, default)


def wrap_event(payload: dict) -> types.SimpleNamespace:
    event = types.SimpleNamespace()
    event.params = payload.get("params") or {}
    event.route = _to_namespace(payload.get("route") or {})
    event.url = payload.get("url", "")
    event.parent = _to_namespace(payload.get("parent"))
    event.data = payload.get("data")
    event.cookies = _Cookies(payload.get("cookies"))
    return event


def parse_load_result(result: Any) -> dict:
    if (
        isinstance(result, tuple)
        and len(result) == 3
        and result[0] in ("error", "redirect")
    ):
        kind, status, payload = result
        if kind == "error":
            return {"type": "error", "status": status, "body": payload}
        return {"type": "redirect", "status": status, "location": payload}
    return {"type": "data", "data": result}


async def run_load(mod, payload: dict) -> dict:
    inject_load_helpers(mod)
    event = wrap_event(payload)
    try:
        result = mod.load(event)
        if inspect.iscoroutine(result):
            result = await result
        return parse_load_result(result)
    except SKPVRedirect as exc:
        return {"type": "redirect", "status": exc.status, "location": exc.location}
    except SKPVError as exc:
        return {"type": "error", "status": exc.status, "body": exc.body}
