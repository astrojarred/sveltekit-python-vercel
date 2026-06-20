import argparse
import glob
import json
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

parser = argparse.ArgumentParser(description="Run SvelteKit Python Deployment")
parser.add_argument("--root", default=".", help="Root directory of the SvelteKit project")
parser.add_argument("--packagedir", default=None, help="Directory of the sveltekit-python-vercel package")
args = parser.parse_args()

root_dir = Path(args.root).absolute()

func_dir = root_dir / ".vercel" / "output" / "functions" / "api" / "index.func"
func_dir.mkdir(parents=True, exist_ok=True)

if args.packagedir:
    shutil.copy(Path(args.packagedir).absolute() / "deploy.py", func_dir / "index.py")

# find all +server.py routes and copy them into the .func directory
manifest = []

for module_path in glob.glob(str(root_dir / "src/routes/**/+server.py"), recursive=True):
    rel = Path(module_path).absolute().relative_to(root_dir / "src/routes")

    # replace square brackets with curly brackets
    rel = Path(str(rel).replace("[", "{").replace("]", "}"))

    # remove any SvteleKit groups from the URL
    parts = [
        p for p in PurePosixPath(rel).parts
        if not (p.startswith("(") and p.endswith(")"))
    ]
    rel = Path(*parts)

    target_dir = func_dir / rel.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy(module_path, target_dir / rel.name)

    if not (target_dir / "__init__.py").exists():
        (target_dir / "__init__.py").touch()

    # build the API route
    parent = PurePosixPath(rel).parent
    if str(parent) == ".":
        api_route = "/api"
    else:
        api_route = "/api/" + str(parent)

    manifest.append({"file": str(PurePosixPath(rel)), "route": api_route})
    print(f"PYTHON ENDPOINT: {module_path} → {api_route}")

(func_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2))

# bundle the dependency file here
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

# pre-install Python packages into _deps/ so they are available in the lambda env
dep_dir = func_dir / "_deps"
dep_dir.mkdir(exist_ok=True)
pip_cmd = [sys.executable, "-m", "pip", "install", "--target", str(dep_dir), "--quiet"]
if (func_dir / "requirements.txt").exists():
    pip_cmd += ["-r", str(func_dir / "requirements.txt")]
    subprocess.run(pip_cmd, check=True)
    print("PYTHON ENDPOINT: Installed deps from requirements.txt")
elif (func_dir / "pyproject.toml").exists():
    # extract dependencies from pyproject.toml
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

# python3.12 is the AWS Lambda runtime string
vc_config = {"runtime": "python3.12", "handler": "index.handler"}
(func_dir / ".vc-config.json").write_text(json.dumps(vc_config, indent=2))
print("PYTHON ENDPOINT: Created .vc-config.json")

# patch the SvelteKit config.json that the endpoints are rerouted to python
config_path = root_dir / ".vercel" / "output" / "config.json"
if config_path.exists():
    config = json.loads(config_path.read_text())
    routes = config.get("routes", [])

    python_route = {"src": "^/api(/.*)?$", "dest": "api/index"}

    # routes /api/* to python before SvelteKit catches it
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
