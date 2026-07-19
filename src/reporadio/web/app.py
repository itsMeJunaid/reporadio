"""FastAPI studio server: static dashboard + REST + one WebSession per socket."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from reporadio.web.events import ProtocolError, event, parse_client

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="RepoRadio Studio")

    @app.get("/api/modes")
    def modes() -> list[dict]:
        from reporadio.show.modes import load_modes

        return [
            {
                "key": m.key, "freq": m.freq, "title": m.title,
                "language": m.language, "greeting": m.greeting,
                "voice": f"{m.voice.engine} · {m.voice.name}",
            }
            for m in load_modes().values()
        ]

    @app.get("/api/versions/{owner}/{name}")
    def versions(owner: str, name: str) -> dict:
        from reporadio.versions import registry

        repo = f"{owner}/{name}"
        return {
            "repo": repo,
            "versions": [
                {
                    "commit": v.commit[:10], "analyzed_at": v.analyzed_at,
                    "files": v.file_count, "tokens": v.token_count,
                    "languages": v.languages,
                }
                for v in registry.list_versions(repo)
            ],
            "episodes": len(registry.list_episodes(repo)),
        }

    @app.websocket("/ws/session")
    async def ws_session(ws: WebSocket) -> None:
        from reporadio.web.session import WebSession

        await ws.accept()
        session = WebSession(asyncio.get_running_loop())

        async def sender() -> None:
            while True:
                item = await session.events.get()
                if item is None:
                    break
                await ws.send_json(item)

        send_task = asyncio.create_task(sender())
        try:
            while True:
                raw = await ws.receive_json()
                try:
                    type_, payload = parse_client(raw)
                except ProtocolError as err:
                    await ws.send_json(event("error", message=str(err)))
                    continue
                if type_ == "tune_in":
                    session.tune_in(payload.url, payload.mode, payload.lang)
                elif type_ == "mic":
                    session.set_mic(payload.live)
                elif type_ == "caller_audio":
                    session.caller_chunk(payload.data, payload.end)
                elif type_ == "select_file":
                    session.select_file(payload.path)
                elif type_ == "explain_file":
                    session.explain_file(payload.path)
                elif type_ == "tour":
                    session.start_tour()
                elif type_ == "pause":
                    session.paused.set()
                elif type_ == "resume":
                    session.paused.clear()
                elif type_ == "skip":
                    session.skip.set()
        except WebSocketDisconnect:
            pass
        finally:
            session.close()
            send_task.cancel()

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


def serve(host: str = "127.0.0.1", port: int = 8181, open_browser: bool = True) -> None:
    import threading
    import webbrowser

    import uvicorn

    if open_browser:
        threading.Timer(
            1.2, lambda: webbrowser.open(f"http://{host}:{port}")
        ).start()
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
