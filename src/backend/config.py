import datetime
import json

from pydantic import BaseModel, FilePath, HttpUrl, DirectoryPath

from .models import Platform


class ApiServerPlatformConfig(BaseModel):
    client_id: int
    client_secret: str

class ApiServer(BaseModel):
    enabled: bool
    domain: str
    port: int
    database: FilePath
    fluxer: ApiServerPlatformConfig
    discord: ApiServerPlatformConfig | None = None

    def cfg(self, item: Platform) -> ApiServerPlatformConfig | None:
        if item is Platform.Fluxer:
            return self.fluxer
        elif item is Platform.Discord:
            return self.discord
        return None


class WebsiteConfig(BaseModel):
    dashboard: HttpUrl
    home: HttpUrl
    terms: HttpUrl
    privacy: HttpUrl
    contact: HttpUrl


class PlatformConfig(BaseModel):
    token: str
    guild_invite: str
    guild_id: int
    bot_invite: str
    client_id: int
    api_url: HttpUrl
    prefixes: list[str]


class Config_(BaseModel):
    fluxer: PlatformConfig
    discord: PlatformConfig | None = None

    name: str
    database_file: str
    data_path: DirectoryPath
    webhook: str
    log_directory: DirectoryPath
    log_time_format: str

    use_extras: bool = False
    donation: HttpUrl | None = None
    api_server: ApiServer | None = None
    website: WebsiteConfig | None = None

    def cfg(self, item: Platform) -> PlatformConfig | None:
        if item is Platform.Fluxer:
            return self.fluxer
        elif item is Platform.Discord:
            return self.discord
        return None


class Config:
    instance: Config_
    init_time: datetime.datetime

    def __init__(self, filename: str = "config.json"):
        with open(filename) as f:
            conf = json.loads(f.read())
            Config.instance = Config_(**conf)
        Config.init_time = datetime.datetime.now()

    @classmethod
    def cfg(cls, item: Platform) -> PlatformConfig | None:
        if item is Platform.Fluxer:
            return cls.instance.fluxer
        elif item is Platform.Discord:
            return cls.instance.discord
        return None

    @classmethod
    def prefix(cls, platform: Platform) -> str:
        return cls.cfg(platform).prefixes[0]

    @classmethod
    def name(cls) -> str:
        return cls.instance.name