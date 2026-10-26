import json

from pydantic import BaseModel, FilePath, HttpUrl, DirectoryPath, Field

from .models import Platform


RateLimit = Field(pattern=r"\d+ *(/|per) *(\d+)? *(second|minute|hour|day|month|year)")

class ApiServerPlatformConfig(BaseModel):
    client_id: int
    client_secret: str

class RateLimits(BaseModel):
    get_info: str = RateLimit
    edit: str = RateLimit
    s3_upload: str = RateLimit

class ApiServer(BaseModel):
    enabled: bool
    domain: str
    port: int
    database: FilePath
    ratelimits: RateLimits
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


class S3Config(BaseModel):
    endpoint: HttpUrl
    key_id: str
    bucket_name: str
    access_key: str

class CDNConfig(BaseModel):
    s3: S3Config
    url: HttpUrl


class Config(BaseModel):
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
    cdn: CDNConfig | None = None

    def cfg(self, item: Platform) -> PlatformConfig | None:
        if item is Platform.Fluxer:
            return self.fluxer
        elif item is Platform.Discord:
            return self.discord
        return None


def config_from_file(filename: str = "config.json") -> Config:
    with open(filename) as f:
        conf = json.loads(f.read())
        return Config(**conf)
