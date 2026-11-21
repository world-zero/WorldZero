"""An admin route with no declared permission fails here (#3847)."""
import dependencies
from routers import admin, copy

PLAIN_ADMIN_ROUTES = {("GET", "/overview"), ("GET", "/mod-log")}
OWNER_ROUTES = {
    ("GET", "/admins"),
    ("POST", "/admins"),
    ("DELETE", "/admins/{username}"),
}
SECRET_ROUTES = {("POST", "/cli-token")}


def required_permissions(route) -> frozenset | None:
    for dep in route.dependant.dependencies:
        required = getattr(dep.call, "required_permissions", None)
        if required:
            return required
    return None


def _gate(route) -> str | frozenset | None:
    calls = [dep.call for dep in route.dependant.dependencies]
    if dependencies.require_admin in calls:
        return "admin"
    if dependencies.require_owner in calls:
        return "owner"
    return required_permissions(route)


def admin_routes():
    for route in admin.router.routes:
        yield route
    for route in copy.router.routes:
        if route.methods & {"PUT", "DELETE"}:
            yield route


def test_every_admin_route_declares_exactly_what_it_needs() -> None:
    unmapped = []
    for route in admin_routes():
        keys = {(method, route.path) for method in route.methods}
        gate = _gate(route)
        if gate == "admin":
            ok = keys <= PLAIN_ADMIN_ROUTES
        elif gate == "owner":
            ok = keys <= OWNER_ROUTES
        elif gate is None:
            ok = keys <= SECRET_ROUTES
        else:
            ok = True
        if not ok:
            unmapped.append(sorted(keys))
    assert not unmapped, f"admin routes with no permission mapped: {unmapped}"
