import gzip
from collections.abc import Callable

from fastapi import HTTPException, Request, Response
from fastapi.routing import APIRoute


class GzipRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            if "gzip" in request.headers.getlist("Content-Encoding"):
                body = await request.body()
                try:
                    decompressed_body = gzip.decompress(body)
                except gzip.BadGzipFile:
                    raise HTTPException(status_code=400, detail="Invalid gzip payload")

                async def receive():
                    return {"type": "http.request", "body": decompressed_body}

                request = Request(request.scope, receive)
            return await original_route_handler(request)

        return custom_route_handler
