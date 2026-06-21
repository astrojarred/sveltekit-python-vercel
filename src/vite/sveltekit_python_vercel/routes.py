from pathlib import Path, PurePosixPath


def rel_path_from_routes(module_path: Path, routes_root: Path) -> PurePosixPath:
    """Route file path relative to src/routes, with groups stripped and [param] → {param}."""
    rel = module_path.absolute().relative_to(routes_root)
    rel = Path(str(rel).replace("[", "{").replace("]", "}"))
    parts = [
        p
        for p in PurePosixPath(rel).parts
        if not (p.startswith("(") and p.endswith(")"))
    ]
    return PurePosixPath(*parts)


def route_parent(rel: PurePosixPath) -> PurePosixPath:
    return PurePosixPath(rel).parent


def api_route(rel_parent: PurePosixPath, *, prefix: str = "/api") -> str:
    if str(rel_parent) == ".":
        return prefix
    return f"{prefix}/{rel_parent}"


def load_route(rel_parent: PurePosixPath) -> str:
    return api_route(rel_parent, prefix="/api/_load")


def resolve_route_path(template: str, params: dict) -> str:
    path = template
    for key, value in params.items():
        path = path.replace(f"{{{key}}}", str(value))
    return path
