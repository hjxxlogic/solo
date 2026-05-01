from __future__ import annotations

import asyncio
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

import httpx
import websockets
from fastapi import HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse, Response

from .editor import editor_id_from_host, load_editor_record
from .models import Project


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class EditorProxyMiddleware:
    def __init__(self, app, project_getter: Callable[[], Project]):
        self.app = app
        self.project_getter = project_getter

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] in {"http", "websocket"}:
            host = _scope_header(scope, b"host")
            if editor_id_from_host(host):
                path = str(scope.get("path") or "/").lstrip("/")
                if scope["type"] == "http":
                    request = Request(scope, receive)
                    try:
                        response = await proxy_editor_http(self.project_getter(), request, path)
                    except HTTPException as exc:
                        response = JSONResponse(
                            {"detail": exc.detail},
                            status_code=exc.status_code,
                        )
                    await response(scope, receive, send)
                    return
                websocket = WebSocket(scope, receive, send)
                await proxy_editor_websocket(self.project_getter(), websocket, path)
                return
        await self.app(scope, receive, send)


def request_public_origin(request: Request) -> str:
    proto = _first_header_value(request.headers.get("x-forwarded-proto")) or request.url.scheme
    host = _first_header_value(request.headers.get("x-forwarded-host")) or request.headers.get("host")
    return f"{proto}://{host}"


def _scope_header(scope, name: bytes) -> str | None:
    for header_name, value in scope.get("headers") or []:
        if header_name.lower() == name:
            return value.decode("latin-1")
    return None


def _first_header_value(value: str | None) -> str | None:
    if not value:
        return None
    return value.split(",", 1)[0].strip()


async def proxy_editor_http(project: Project, request: Request, path: str) -> Response:
    record = _editor_record_for_host(project, request.headers.get("host"))
    port = int(record["port"])
    target_url = _target_url("http", port, path, request.url.query)
    headers = _forward_headers(dict(request.headers), port)
    body = await request.body()

    async with httpx.AsyncClient(follow_redirects=False, timeout=None) as client:
        upstream = await client.request(
            request.method,
            target_url,
            content=body,
            headers=headers,
        )

    response_headers = _response_headers(dict(upstream.headers), request)
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )


async def proxy_editor_websocket(project: Project, websocket: WebSocket, path: str) -> None:
    try:
        record = _editor_record_for_host(project, websocket.headers.get("host"))
    except HTTPException:
        await websocket.close(code=1008)
        return

    port = int(record["port"])
    target_url = _target_url("ws", port, path, websocket.url.query)
    await websocket.accept()
    try:
        async with websockets.connect(target_url) as upstream:
            client_task = asyncio.create_task(_client_to_upstream(websocket, upstream))
            upstream_task = asyncio.create_task(_upstream_to_client(websocket, upstream))
            done, pending = await asyncio.wait(
                {client_task, upstream_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
    except Exception:
        await websocket.close(code=1011)


def _editor_record_for_host(project: Project, host: str | None) -> dict:
    editor_id = editor_id_from_host(host)
    if not editor_id:
        raise HTTPException(status_code=404, detail="not found")
    record = load_editor_record(project, editor_id)
    if not record:
        raise HTTPException(status_code=404, detail="editor not found")
    return record


def _target_url(scheme: str, port: int, path: str, query: str) -> str:
    suffix = f"/{path}" if path else "/"
    if query:
        suffix = f"{suffix}?{query}"
    return f"{scheme}://127.0.0.1:{port}{suffix}"


def _forward_headers(headers: dict[str, str], port: int) -> dict[str, str]:
    output = {
        name: value
        for name, value in headers.items()
        if name.lower() not in HOP_BY_HOP_HEADERS and name.lower() != "host"
    }
    output["host"] = f"127.0.0.1:{port}"
    return output


def _response_headers(headers: dict[str, str], request: Request) -> dict[str, str]:
    output = {
        name: value
        for name, value in headers.items()
        if name.lower() not in HOP_BY_HOP_HEADERS and name.lower() != "content-length"
    }
    if "location" in output:
        output["location"] = _rewrite_location(output["location"], request)
    return output


def _rewrite_location(location: str, request: Request) -> str:
    host = request.headers.get("host")
    if not host:
        return location
    parsed = urlsplit(location)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return location
    proto = _first_header_value(request.headers.get("x-forwarded-proto")) or request.url.scheme
    return urlunsplit((proto, host, parsed.path, parsed.query, parsed.fragment))


async def _client_to_upstream(websocket: WebSocket, upstream) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            await upstream.close()
            return
        if "text" in message:
            await upstream.send(message["text"])
        elif "bytes" in message:
            await upstream.send(message["bytes"])


async def _upstream_to_client(websocket: WebSocket, upstream) -> None:
    async for message in upstream:
        if isinstance(message, bytes):
            await websocket.send_bytes(message)
        else:
            await websocket.send_text(message)
