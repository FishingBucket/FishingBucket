__all__ = "context", "database", "config", "new_context"

from datetime import datetime
from typing import TYPE_CHECKING

import aioboto3
from aiobotocore.client import AioBaseClient
from aiobotocore.config import AioConfig
from aiobotocore.session import ClientCreatorContext

if TYPE_CHECKING:
    from .backend.config import Config
    from .backend.database.database import Database

def database() -> Database:
    return context().database

def config() -> Config:
    return context().config

def context() -> Context:
    return Context.instance

def new_context(config: Config) -> Context:
    return Context(config)

class Context:
    instance: Context

    def __init__(self, config: Config):
        Context.instance = self
        self.config = config
        self.startup_time = datetime.now()

        from .backend.database.database import Database
        self.database = Database(config.database_file)

        from .backend.data_reader import DataReader
        self.data_reader = DataReader(config.data_path)

        from .api_server.api_app import Application as ApiApplication
        self.api_app: ApiApplication | None = None

        self.s3_client_context: ClientCreatorContext | None = None
        self.s3_client: AioBaseClient | None = None

        if self.config.cdn:
            self.s3_client_context = aioboto3.Session().client(
                's3',
                endpoint_url=str(self.config.cdn.s3.endpoint),
                aws_access_key_id=self.config.cdn.s3.key_id,
                aws_secret_access_key=self.config.cdn.s3.access_key,
                config=AioConfig(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                )
            )

        if self.config.api_server:
            self.api_app = ApiApplication()
            from .api_server.main import ready
            ready(self.api_app)


    async def start(self):
        await self.database.init()
        if self.s3_client_context:
            self.s3_client = await self.s3_client_context.__aenter__()


    async def close(self):
        await self.database.close()

        if self.s3_client and self.s3_client_context:
            await self.s3_client_context.__aexit__(None, None, None)
            self.s3_client = None
            self.s3_client_context = None
