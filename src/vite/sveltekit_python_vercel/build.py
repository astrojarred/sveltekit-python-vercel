import argparse
import shutil
import glob

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

# Add all +server.py routes to web_app
for module_path in glob.glob(str(root_dir / "src/routes/**/+server.py"), recursive=True):

    api_route = func_dir / Path(module_path).absolute().relative_to(root_dir / "src/routes")

    # replace square brackets with curly brackets
    api_route = Path(str(api_route).replace("[", "{").replace("]", "}"))

    # remove any groups from the URL
    api_route = Path(str(PurePosixPath(*[part for part in PurePosixPath(api_route).parts if not part.startswith("(") and not part.endswith(")")])))

    if not api_route.parent.exists():
        api_route.parent.mkdir(parents=True)

    shutil.copy(module_path, api_route.parent)

    if not (api_route.parent / "__init__.py").exists():
        (api_route.parent / "__init__.py").touch()

    print(f"PYTHON ENDPOINT: Copied {module_path} to {api_route.parent}")
