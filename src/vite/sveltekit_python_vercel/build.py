import argparse
import glob
import json
import shutil

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
