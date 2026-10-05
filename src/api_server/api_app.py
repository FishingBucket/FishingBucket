import uvicorn
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.params import Header

from .api_database import Database, Session
from .context import ApplicationContext
from ..backend import logging
from ..backend.logging import start_log

print, error = start_log("api", "-api")

async def require_session(authorization: str | None = Header(None)) -> Session:
    if not authorization:
        raise HTTPException(401, "Missing AUTHORIZATION header.")

    session = await Database.instance.get_session(authorization)
    if not session:
        raise HTTPException(401, "Invalid or expired session.")

    return session

class Application:
    def __init__(self):
        self.app = FastAPI()
        self.context: ApplicationContext = None
        self.ready = False
        self.server: uvicorn.Server = None
        self.routers: list[APIRouter] = []

    def set_context(self, context: ApplicationContext):
        self.context = context

        api_server = self.context.config.api_server

        if api_server is None:
            self.ready = False
            print("[api_server] API server is not configured; initialization skipped.")
            return

        if not api_server.enabled:
            self.ready = False
            print("[api_server] API server is disabled; initialization skipped.")
            return

        Database(api_server.database)
        self.ready = True

    def create_router(self, prefix: str) -> APIRouter:
        r = APIRouter(prefix=prefix)
        self.routers.append(r)
        return r

    async def serve(self):
        if not self.ready:
            raise Exception("Application is not ready yet!")

        await Database.instance.init()
        config = self.context.config

        for r in self.routers:
            self.app.include_router(r)

        host, port = config.api_server.domain, config.api_server.port
        log_file = logging.get_log_file("-uvi")
        uv_conf = uvicorn.Config(self.app, host, port, reload=False, log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "uvicorn.logging.DefaultFormatter",
                    "fmt": "%(levelprefix)s %(message)s",
                    "use_colors": None,
                },
                "access": {
                    "()": "uvicorn.logging.AccessFormatter",
                    "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.FileHandler",
                    "filename": log_file,
                },
                "access": {
                    "formatter": "access",
                    "class": "logging.FileHandler",
                    "filename": log_file,
                },
            },
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
                "uvicorn.error": {"level": "INFO"},
                "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
            },
        })
        self.server = uvicorn.Server(uv_conf)
        await self.server.serve()
        print(f"API server is running at {host}:{port}!")

    async def close(self):
        if self.server:
            self.server.should_exit = True
            await self.server.shutdown()
        self.ready = False
        print("API server shutdown.")
