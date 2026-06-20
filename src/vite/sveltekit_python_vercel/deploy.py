import importlib.util
import json
import sys
from pathlib import Path

_base = Path(__file__).parent
_deps = _base / "_deps"
if _deps.exists() and str(_deps) not in sys.path:
    sys.path.insert(0, str(_deps))
if str(_base) not in sys.path:
    sys.path.insert(0, str(_base))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()


def _load_module(file_path: Path):
    spec = importlib.util.spec_from_file_location("_route_module", file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_manifest_path = _base / "_manifest.json"
if _manifest_path.exists():
    for _entry in json.loads(_manifest_path.read_text()):
        _mod = _load_module(_base / _entry["file"])
        _route = _entry["route"]

        for _method in ["GET", "POST", "PATCH", "PUT", "DELETE"]:
            _has_upper = hasattr(_mod, _method)
            _has_lower = hasattr(_mod, _method.lower())

            if _has_upper and _has_lower:
                raise Exception(
                    f"Duplicate method {_method} and {_method.lower()} in {_route}"
                )
            elif _has_upper:
                app.add_api_route(_route, getattr(_mod, _method), methods=[_method])
                print(f"PYTHON ENDPOINT: Registered {_method} {_route}")
            elif _has_lower:
                app.add_api_route(_route, getattr(_mod, _method.lower()), methods=[_method])
                print(f"PYTHON ENDPOINT: Registered {_method} {_route}")


@app.exception_handler(Exception)
async def unicorn_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": f"{exc}"},
    )
