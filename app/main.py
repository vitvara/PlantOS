import os

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.lifespan import lifespan


settings = get_settings()


class NoCacheHTMLMiddleware(BaseHTTPMiddleware):
    """
    Prevent browsers and nginx from caching dynamic responses.

    Covers both rendered HTML pages AND redirect (3xx) responses.
    Without the redirect fix, browsers cache the 303 itself and re-serve
    the same stale destination on subsequent POSTs, bypassing fresh data.

    Static media (images) keep default caching since their Content-Type
    is image/* and their status is always 200.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        ct = response.headers.get("content-type", "")
        sc = response.status_code
        if "text/html" in ct or 300 <= sc < 400:
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
        version="0.0.1a",
    )

    app.add_middleware(NoCacheHTMLMiddleware)

    app.include_router(api_router)

    # Serve uploaded plant images
    os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
    app.mount("/media", StaticFiles(directory=settings.MEDIA_ROOT), name="media")

    return app


app = create_application()
