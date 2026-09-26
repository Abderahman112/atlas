"""Control API + live WebSocket for the Atlas Town UI. Every route except /api/health needs the UI token."""
from __future__ import annotations

import asyncio
import secrets

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from atlas.config import ROOT
from atlas.events import bus
from atlas.service import Assistant

EFFORTS = {"low", "medium", "high", "xhigh", "max"}
DIST = ROOT / "ui" / "dist"


class AgentPatch(BaseModel):
    paused: bool | None = None
    effort: str | None = None


class JobPatch(BaseModel):
    enabled: bool


class ChatIn(BaseModel):
    text: str


class PauseAll(BaseModel):
    paused: bool


def create_app(assistant: Assistant, token: str) -> FastAPI:
    app = FastAPI(title="Atlas Town", docs_url=None, redoc_url=None)

    def valid(candidate: str | None) -> bool:
        return bool(candidate) and secrets.compare_digest(candidate, token)

    def auth(request: Request) -> None:
        header = request.headers.get("authorization", "")
        if not valid(header.removeprefix("Bearer ").strip()):
            raise HTTPException(401, "Wrong or missing access token")

    def agent_or_404(name: str):
        if name not in bus.agents:
            raise HTTPException(404, f"No agent called {name}")
        return bus.agents[name]

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/state", dependencies=[Depends(auth)])
    def state():
        return bus.snapshot()

    @app.get("/api/history", dependencies=[Depends(auth)])
    def history():
        rows = assistant.db.conn.execute(
            "SELECT role, content, ts FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 60",
            (assistant.chat_id,)).fetchall()
        return [dict(r) for r in rows[::-1]]

    @app.post("/api/agents/{name}", dependencies=[Depends(auth)])
    def patch_agent(name: str, patch: AgentPatch):
        s = agent_or_404(name)
        if patch.effort is not None:
            if patch.effort not in EFFORTS:
                raise HTTPException(422, f"effort must be one of {sorted(EFFORTS)}")
            if s.model.startswith("claude-haiku"):
                raise HTTPException(422, f"{s.title} runs on {s.model}, which doesn't use effort")
            s.effort = patch.effort
        if patch.paused is not None:
            s.paused = patch.paused
            bus.emit(name, "control", "Paused by you" if s.paused else "Resumed by you")
        bus.set_status(name, "paused" if s.paused else "idle")
        return s.to_dict()

    @app.post("/api/pause_all", dependencies=[Depends(auth)])
    def pause_all(body: PauseAll):
        for name, s in bus.agents.items():
            s.paused = body.paused
            bus.set_status(name, "paused" if s.paused else "idle")
        bus.emit("atlas", "control", "Everyone paused by you" if body.paused else "Everyone back to work")
        return {"ok": True}

    @app.post("/api/jobs/{name}", dependencies=[Depends(auth)])
    def patch_job(name: str, patch: JobPatch):
        if name not in bus.jobs:
            raise HTTPException(404, f"No job called {name}")
        bus.jobs[name].enabled = patch.enabled
        bus.job_changed(name)
        return bus.jobs[name].to_dict()

    @app.post("/api/jobs/{name}/run", dependencies=[Depends(auth)])
    async def run_job(name: str):
        if name not in bus.jobs:
            raise HTTPException(404, f"No job called {name}")
        asyncio.create_task(assistant.proactive.run_job(name, manual=True))
        return {"started": True}

    @app.post("/api/chat", dependencies=[Depends(auth)])
    async def chat(body: ChatIn):
        text = body.text.strip()
        if not text:
            raise HTTPException(422, "Say something first")
        return {"reply": await assistant.chat(text[:4000], source="web")}

    @app.websocket("/api/ws")
    async def ws(socket: WebSocket):
        await socket.accept()
        try:
            hello = await asyncio.wait_for(socket.receive_json(), timeout=10)
        except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
            await socket.close(code=4401)
            return
        if not valid(str(hello.get("token", ""))):  # token in the first message, not the URL
            await socket.close(code=4401)
            return
        queue = bus.subscribe()
        try:
            await socket.send_json(bus.snapshot())
            while True:
                await socket.send_json(await queue.get())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            bus.unsubscribe(queue)

    if (DIST / "index.html").exists():
        app.mount("/", StaticFiles(directory=DIST, html=True), name="ui")
    else:
        @app.get("/", response_class=HTMLResponse)
        def no_ui():
            return "<p>Atlas API is running. Build the town UI with <code>cd ui &amp;&amp; npm install &amp;&amp; npm run build</code>.</p>"

    return app
