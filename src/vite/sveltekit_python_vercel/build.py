import argparse
import glob
import json
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).parent))
from routes import api_route, load_route, rel_path_from_routes, route_parent

parser = argparse.ArgumentParser(description="Run SvelteKit Python Deployment")
parser.add_argument("--root", default=".", help="Root directory of the SvelteKit project")
parser.add_argument("--packagedir", default=None, help="Directory of the sveltekit-python-vercel package")
args = parser.parse_args()

root_dir = Path(args.root).absolute()
routes_root = root_dir / "src/routes"

func_dir = root_dir / ".vercel" / "output" / "functions" / "api" / "index.func"
func_dir.mkdir(parents=True, exist_ok=True)

if args.packagedir:
    package_dir = Path(args.packagedir).absolute()
    shutil.copy(package_dir / "deploy.py", func_dir / "index.py")
    for helper in ("load_runtime.py", "routes.py", "__init__.py"):
        src = package_dir / helper
        if src.exists():
            shutil.copy(src, func_dir / helper)

manifest = []


def _bundle_route_module(module_path: str, *, kind: str) -> None:
    abs_path = Path(module_path).absolute()
    rel = rel_path_from_routes(abs_path, routes_root)
    target_dir = func_dir / route_parent(rel)
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(abs_path, target_dir / rel.name)

    if not (target_dir / "__init__.py").exists():
        (target_dir / "__init__.py").touch()

    parent = route_parent(rel)
    if kind == "load":
        route = load_route(parent)
    else:
        route = api_route(parent)

    entry = {"file": str(PurePosixPath(rel)), "route": route, "kind": kind}
    manifest.append(entry)
    print(f"PYTHON {'LOAD' if kind == 'load' else 'ENDPOINT'}: {module_path} → {route}")


for module_path in glob.glob(str(routes_root / "**/+server.py"), recursive=True):
    _bundle_route_module(module_path, kind="server")

for pattern in ("**/+page.server.py", "**/+layout.server.py"):
    for module_path in glob.glob(str(routes_root / pattern), recursive=True):
        _bundle_route_module(module_path, kind="load")

(func_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2))

dep_files = ["requirements.txt", "pyproject.toml", "uv.lock", "Pipfile", "Pipfile.lock"]
found_dep = False
for dep_file in dep_files:
    src = root_dir / dep_file
    if src.exists():
        shutil.copy(src, func_dir / dep_file)
        print(f"PYTHON ENDPOINT: Bundled {dep_file}")
        found_dep = True

if not found_dep:
    (func_dir / "requirements.txt").write_text("fastapi\nuvicorn\n")
    print("PYTHON ENDPOINT: No dependency file found, created minimal requirements.txt")

dep_dir = func_dir / "_deps"
dep_dir.mkdir(exist_ok=True)
pip_cmd = [sys.executable, "-m", "pip", "install", "--target", str(dep_dir), "--quiet"]
if (func_dir / "requirements.txt").exists():
    pip_cmd += ["-r", str(func_dir / "requirements.txt")]
    subprocess.run(pip_cmd, check=True)
    print("PYTHON ENDPOINT: Installed deps from requirements.txt")
elif (func_dir / "pyproject.toml").exists():
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore
    with open(func_dir / "pyproject.toml", "rb") as _f:
        _pyproject = tomllib.load(_f)
    _deps_list = _pyproject.get("project", {}).get("dependencies", [])
    if _deps_list:
        subprocess.run(pip_cmd + _deps_list, check=True)
        print(f"PYTHON ENDPOINT: Installed {len(_deps_list)} deps from pyproject.toml")

vc_config = {"runtime": "python3.12", "handler": "index.handler"}
(func_dir / ".vc-config.json").write_text(json.dumps(vc_config, indent=2))
print("PYTHON ENDPOINT: Created .vc-config.json")

config_path = root_dir / ".vercel" / "output" / "config.json"
if config_path.exists():
    config = json.loads(config_path.read_text())
    routes = config.get("routes", [])
    python_route = {"src": "^/api(/.*)?$", "dest": "api/index"}
    fs_idx = next(
        (i for i, r in enumerate(routes) if r.get("handle") == "filesystem"),
        0,
    )
    routes.insert(fs_idx, python_route)
    config["routes"] = routes
    config_path.write_text(json.dumps(config, indent=2))
    print("PYTHON ENDPOINT: Patched .vercel/output/config.json")
else:
    print(
        "WARNING: .vercel/output/config.json not found. "
        "Make sure to run `vite build` before this script."
    )
