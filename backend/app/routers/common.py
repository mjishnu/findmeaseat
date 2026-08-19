import json
from collections.abc import Callable

import msgpack
import zstandard as zstd
from fastapi import HTTPException, Request, Response
from fastapi.routing import APIRoute

_zstd_decompressor = zstd.ZstdDecompressor()


class DecompressRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            body = await request.body()
            if body:
                scope = dict(request.scope)
                headers = list(scope.get("headers", []))

                content_encoding = request.headers.get("Content-Encoding", "").lower()
                if "zstd" in content_encoding:
                    try:
                        body = _zstd_decompressor.decompress(body)
                    except zstd.ZstdError:
                        raise HTTPException(
                            status_code=400, detail="Invalid zstd payload"
                        )
                    headers = [
                        (k, v) for k, v in headers if k.lower() != b"content-encoding"
                    ]

                content_type = request.headers.get("Content-Type", "").lower()
                if "application/x-msgpack" in content_type:
                    try:
                        unpacked = msgpack.unpackb(body, raw=False)
                        body = json.dumps(unpacked).encode("utf-8")
                    except Exception:
                        raise HTTPException(
                            status_code=400, detail="Invalid msgpack payload"
                        )
                    headers = [
                        (k, v) for k, v in headers if k.lower() != b"content-type"
                    ]
                    headers.append((b"content-type", b"application/json"))

                scope["headers"] = headers

                async def receive():
                    return {"type": "http.request", "body": body}

                request = Request(scope, receive)
            return await original_route_handler(request)

        return custom_route_handler
