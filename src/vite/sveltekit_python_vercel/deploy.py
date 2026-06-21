import asyncio
import base64
import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

_base = Path(__file__).parent
_deps = _base / "_deps"
if _deps.exists() and str(_deps) not in sys.path:
    sys.path.insert(0, str(_deps))
if str(_base) not in sys.path:
    sys.path.insert(0, str(_base))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from load_runtime import run_load

app = FastAPI()


def _load_module(file_path: Path):
    spec = importlib.util.spec_from_file_location("_route_module", file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_load_handler(mod):
    async def handler(request: Request):
        payload = await request.json()
        return JSONResponse(await run_load(mod, payload))

    return handler


_manifest_path = _base / "_manifest.json"
if _manifest_path.exists():
    for _entry in json.loads(_manifest_path.read_text()):
        _mod = _load_module(_base / _entry["file"])
        _route = _entry["route"]
        _kind = _entry.get("kind", "server")

        if _kind == "load":
            app.add_api_route(_route, _make_load_handler(_mod), methods=["POST"])
            print(f"PYTHON LOAD: Registered POST {_route}")
            continue

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
async def _exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": str(exc)})


async def _dispatch(scope: dict, body: bytes) -> tuple[int, dict, bytes]:
    """Run FastAPI for one HTTP request and collect the response."""
    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait({"type": "http.request", "body": body, "more_body": False})

    status = 500
    resp_headers: dict = {}
    resp_body = b""

    async def receive():
        return await queue.get()

    async def send(message):
        nonlocal status, resp_body
        if message["type"] == "http.response.start":
            status = message["status"]
            for k, v in message.get("headers", []):
                if isinstance(k, bytes):
                    k = k.decode()
                if isinstance(v, bytes):
                    v = v.decode()
                k = k.lower()
                if k in resp_headers:
                    existing = resp_headers[k]
                    resp_headers[k] = (existing if isinstance(existing, list) else [existing]) + [v]
                else:
                    resp_headers[k] = v
        elif message["type"] == "http.response.body":
            resp_body += message.get("body", b"")

    await app(scope, receive, send)
    return status, resp_headers, resp_body


def handler(event, context):
    payload = json.loads(event.get("body") or "{}")

    parsed = urlsplit(payload.get("path", "/"))
    path = parsed.path or "/"
    query = (parsed.query or "").encode()

    raw_headers: dict = payload.get("headers") or {}
    headers_list = []
    host = payload.get("host", "localhost")
    scheme = "https"
    for k, v in raw_headers.items():
        k_lower = k.lower()
        if k_lower == "host":
            host = v
        if k_lower == "x-forwarded-proto":
            scheme = v
        headers_list.append((k_lower.encode(), str(v).encode()))

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": payload.get("method", "GET").upper(),
        "path": path,
        "raw_path": path.encode(),
        "query_string": query,
        "root_path": "",
        "headers": headers_list,
        "server": (host, 443 if scheme == "https" else 80),
        "client": (raw_headers.get("x-real-ip", "127.0.0.1"), 0),
        "scheme": scheme,
    }

    body = payload.get("body") or b""
    if payload.get("encoding") == "base64":
        body = base64.b64decode(body)
    elif isinstance(body, str):
        body = body.encode()

    status, resp_headers, resp_body = asyncio.run(_dispatch(scope, body))

    result: dict = {"statusCode": status, "headers": resp_headers}
    if resp_body:
        try:
            result["body"] = resp_body.decode("utf-8")
        except UnicodeDecodeError:
            result["body"] = base64.b64encode(resp_body).decode()
            result["encoding"] = "base64"

    return result
