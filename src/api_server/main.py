import uuid

import aiohttp
from fastapi import HTTPException
from fastapi.params import Depends
from fastapi.responses import RedirectResponse, Response
from fastapi.requests import Request

from .api_app import Application, require_session
from .api_database import Session, Database, this_time, SESSION_TTL
from .batch_edit import handle_batch_edit
from .models import Proxy, BatchEdit, LoginInformation, RefreshLogin, UserData, ProxyTag, Relationship, \
    UploadURLResponse, UploadURLRequest
from ..backend.database.user import SSOID, UserID
from ..backend.models import Platform
from ..context import context, config, database


def ready(app: Application):
    @app.on_ready
    async def _():
        router = app.create_router("")

        @router.get(
            "/info/@me",
            response_model=UserData,
            dependencies=[]
        )
        @app.limiter.limit(config().api_server.ratelimits.get_info)
        async def _(request: Request, session: Session = Depends(require_session)) -> UserData:
            if session.user_id == -1:
                return UserData(
                    proxies=[],
                    tags=[],
                    relationships=[],
                    user_id=-1
                )

            proxies = await database().proxies.full_from_user(session.user_id)
            tags = await database().tags.from_user(session.user_id)
            relationships = await database().relationships.bulk_get_relationships([proxy.id for proxy in proxies])
            full_relationships = {
                k: await database().tags.fetch_bulk(v)
                for k, v in relationships.items()
            }
            return UserData(
                proxies=[
                    Proxy.from_source(proxy, full_relationships) for proxy in proxies
                ],
                tags=[
                    ProxyTag.from_source(tag) for tag in tags
                ],
                relationships=[
                    Relationship(
                        proxy=proxy,
                        tags=tags
                    ) for proxy, tags in relationships.items()
                ],
                user_id=session.user_id
            )


        @router.post("/edit", status_code=200)
        @app.limiter.limit(config().api_server.ratelimits.edit)
        async def _(request: Request, edits: BatchEdit, session: Session = Depends(require_session)) -> Response:
            try:
                if session.user_id == -1:
                    uid = await database().users.get_or_create_user_id(session.sso_id, session.platform)
                    session = await Database.instance.update_user_id(session.session_id, uid)
                    assert session is not None

                return await handle_batch_edit(edits, session.user_id, database())
            except ValueError as e:
                raise HTTPException(400, str(e))

        if config().cdn:
            @router.post("/upload")
            @app.limiter.limit(config().api_server.ratelimits.s3_upload)
            async def _(request: Request, data: UploadURLRequest) -> UploadURLResponse:
                key = uuid.uuid4().hex + "." + data.file_extension
                url = await context().s3_client.generate_presigned_url(
                    "put_object",
                    Params={
                        "Bucket": config().cdn.s3.bucket_name,
                        "Key": key
                    },
                    ExpiresIn=120
                )
                return UploadURLResponse(
                    upload_url=url,
                    cdn_url=str(config().cdn.url) + key,
                )


        if config().api_server and config().api_server.discord and config().discord:
            discord = config().api_server.discord
            discord_config = config().discord

            @router.get("/auth/discord", status_code=307)
            async def _(redirect_uri: str) -> RedirectResponse:
                return RedirectResponse(f"https://discord.com/oauth2/authorize?client_id={discord.client_id}&response_type=code&redirect_uri={redirect_uri}&scope=identify")

            @router.post("/auth/discord/login", response_model=LoginInformation)
            async def _(request: Request) -> LoginInformation:
                req = await request.json()
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "grant_type": "authorization_code",
                        "code": req.get("code"),
                        "redirect_uri": req.get("redirect_uri"),
                        "client_id": discord.client_id,
                        "client_secret": discord.client_secret
                    }
                    async with session.post(
                            f"{discord_config.api_url}/oauth2/token",
                            data=payload,
                            headers={'Content-Type': 'application/x-www-form-urlencoded'}
                    ) as resp:
                        data = await resp.json()
                        access_token = data["access_token"]
                        async with session.get(f"{discord_config.api_url}/users/@me", headers={"Authorization": "Bearer " + access_token}) as resp_user:
                            obj = await resp_user.json()
                            user_id = SSOID(int(obj["id"]))
                            native_id = await database().users.get_user_id(user_id, Platform.Discord) or UserID(-1)
                            session_id, expires = await Database.instance.new_session(native_id, obj, Platform.Discord, user_id)
                            return LoginInformation(session_id=session_id, user=obj, platform="discord", expires=expires)

        if config().api_server and config().api_server.fluxer:
            fluxer = config().api_server.fluxer
            fluxer_config = config().fluxer

            @router.get("/auth/fluxer", status_code=307)
            async def _(redirect_uri: str) -> RedirectResponse:
                return RedirectResponse(f"https://web.fluxer.app/oauth2/authorize?client_id={fluxer.client_id}&scope=identify&redirect_uri={redirect_uri}")

            @router.post("/auth/fluxer/login", response_model=LoginInformation)
            async def _(request: Request) -> LoginInformation:
                req = await request.json()
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "grant_type": "authorization_code",
                        "code": req.get("code"),
                        "redirect_uri": req.get("redirect_uri"),
                        "client_id": fluxer.client_id,
                        "client_secret": fluxer.client_secret
                    }
                    form_data = aiohttp.FormData(payload)
                    async with session.post(f"{fluxer_config.api_url}/oauth2/token", data=form_data) as resp:
                        data = await resp.json()
                        access_token = data["access_token"]
                        async with session.get(f"{fluxer_config.api_url}/users/@me", headers={"Authorization": "Bearer " + access_token}) as resp_user:
                            obj = await resp_user.json()
                            user_id = SSOID(int(obj["id"]))
                            native_id = await database().users.get_user_id(user_id, Platform.Fluxer) or UserID(-1)
                            session_id, expires = await Database.instance.new_session(native_id, obj, Platform.Fluxer, user_id)
                            return LoginInformation(session_id=session_id, user=obj, platform="fluxer", expires=expires)

        @router.post("/auth/logout", status_code=204)
        async def _(session: Session = Depends(require_session)) -> Response:
            if session.user_id == -1:
                await Database.instance.remove_sessions_sso_id(session.sso_id)
            else:
                await Database.instance.remove_all_sessions(session.user_id)
            return Response(status_code=204)

        @router.post("/auth/extend", response_model=RefreshLogin)
        async def _(session: Session = Depends(require_session)) -> RefreshLogin:
            now = this_time()
            new_session = await Database.instance.extend_session(session.session_id, now + SESSION_TTL)
            if new_session:
                return RefreshLogin(expires=new_session.expires)
            return Response(status_code=400)
