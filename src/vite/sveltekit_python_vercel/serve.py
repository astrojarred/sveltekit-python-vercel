import argparse
import glob
import importlib.util
import shutil
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).parent))
from load_runtime import run_load
from routes import (
    api_route,
    load_route,
    rel_path_from_routes,
    route_parent,
    route_registration_order,
)

parser = argparse.ArgumentParser(description="Run Sveltekit Python Server")
parser.add_argument("--host", default="0.0.0.0", help="Server hostname")
parser.add_argument("--port", type=int, default=8000, help="Server port")
parser.add_argument("--root", default=".", help="Directory where the API is located")
args = parser.parse_args()

app = FastAPI()

root_dir = Path(args.root).absolute()
api_dir = Path("./sveltekit_python_vercel").absolute()
routes_root = root_dir / "src/routes"
watch_modules = []


def _copy_module(module_path: Path) -> Path:
    api_route_path = api_dir.joinpath(module_path.relative_to(routes_root))
    api_route_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(module_path, api_route_path.parent / api_route_path.name)
    return api_route_path.parent / api_route_path.name


def _load_module(api_route_path: Path):
    spec = importlib.util.spec_from_file_location(api_route_path.stem, api_route_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_load_handler(mod):
    async def handler(request: Request):
        payload = await request.json()
        return JSONResponse(await run_load(mod, payload))

    return handler


for module_path in glob.glob(routes_root.joinpath("**/+server.py").as_posix(), recursive=True):
    abs_module_path = Path(module_path).absolute()
    watch_modules.append(abs_module_path.parent.as_posix())

    api_route_path = _copy_module(abs_module_path)
    mod = _load_module(api_route_path)

    rel = rel_path_from_routes(abs_module_path, routes_root)
    api_path = api_route(rel.parent)

    for method in ["GET", "POST", "PATCH", "PUT", "DELETE"]:
        if hasattr(mod, method) and hasattr(mod, method.lower()):
            raise Exception(
                f"Duplicate method {method} and {method.lower()} in {api_route_path}"
            )
        elif hasattr(mod, method):
            app.add_api_route(api_path, getattr(mod, method), methods=[method])
        elif hasattr(mod, method.lower()):
            app.add_api_route(api_path, getattr(mod, method.lower()), methods=[method])

load_entries = []
for pattern in ("**/+page.server.py", "**/+layout.server.py"):
    for module_path in glob.glob(routes_root.joinpath(pattern).as_posix(), recursive=True):
        abs_module_path = Path(module_path).absolute()
        watch_modules.append(abs_module_path.parent.as_posix())

        api_route_path = _copy_module(abs_module_path)
        mod = _load_module(api_route_path)

        if not hasattr(mod, "load"):
            raise Exception(f"Missing load function in {abs_module_path}")

        rel = rel_path_from_routes(abs_module_path, routes_root)
        load_path = load_route(route_parent(rel))
        load_entries.append((load_path, mod, abs_module_path))

for load_path, mod, abs_module_path in sorted(
    load_entries, key=lambda entry: route_registration_order(entry[0])
):
    app.add_api_route(load_path, _make_load_handler(mod), methods=["POST"])
    print(f"PYTHON LOAD: Registered POST {load_path} ← {abs_module_path}")


if __name__ == "__main__":
    uvicorn.run(
        "sveltekit_python_vercel.serve:app",
        host=args.host,
        port=args.port,
        log_level="info",
        reload=True,
        reload_includes=[*set(watch_modules)],
        reload_excludes=[api_dir.as_posix()],
    )
