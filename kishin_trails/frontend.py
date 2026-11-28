"""
Serves the built frontend, so one process answers the pages and the API.

Only used when FRONTEND_DIR is set. Every path that is not a file of the build answers
`index.html`, which is how the frontend's own routes (`/plan`, `/athlete/activities/<id>`)
load when typed into the address bar or reloaded. A path under `/api`, `/withings` or the
documentation's paths never does: a mistyped API route answers a JSON 404, not a page.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response

#: The first path segments that belong to the API, to the Withings page and to the API's
#: documentation. With EXPOSE_DOCS off the documentation paths answer 404, not a page.
RESERVED_PREFIXES = ("api", "withings", "docs", "redoc", "openapi.json")

#: Vite names a file under `assets/` after its content, so a browser may keep it for good.
IMMUTABLE = "public, max-age=31536000, immutable"

#: The rest of the page's policy is in the `<meta>` tag the frontend's build writes into
#: `index.html` (vite.config.ts). A `<meta>` policy cannot forbid framing; this header does.
#: The browser enforces both policies.
CONTENT_SECURITY_POLICY = "frame-ancestors 'none'"


def isReservedPath(path: str) -> bool:
    """
    Whether a path belongs to the API or to the Withings page, even if no route matches it.

    Args:
        path: The request path without its leading slash.

    Returns:
        True when its first segment is in RESERVED_PREFIXES.
    """
    return path.split("/", 1)[0] in RESERVED_PREFIXES


def resolve(root: Path, path: str) -> Path:
    """
    The file to answer for a path.

    Args:
        root: The build directory, already resolved.
        path: The request path without its leading slash.

    Returns:
        The file the path names inside root when it is a regular file, `index.html`
        otherwise. A path that leaves root, by `..` or by a symlink, is not a file of the build.
    """
    candidate = (root / path).resolve()
    if candidate.is_relative_to(root) and candidate.is_file():
        return candidate
    return root / "index.html"


def mount(application: FastAPI, directory: Path) -> None:
    """
    Adds the route that serves the build. Register it after every other route.

    Args:
        application: The FastAPI app.
        directory: The build directory, holding `index.html`.

    Raises:
        RuntimeError: When the directory holds no `index.html`.
    """
    root = directory.resolve()
    if not (root / "index.html").is_file():
        raise RuntimeError(f"FRONTEND_DIR {root} holds no index.html.")

    @application.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def serve(path: str) -> Response:
        if isReservedPath(path):
            raise HTTPException(status_code=404, detail="Not Found")
        target = resolve(root, path)
        headers = {
            "Content-Security-Policy": CONTENT_SECURITY_POLICY,
            "Cache-Control": IMMUTABLE if target.parent == root / "assets" else "no-cache",
        }
        return FileResponse(target, headers=headers)
