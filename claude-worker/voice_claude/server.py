"""HTTP API: /task, /cancel, /quick, /health, /budget."""
import argparse
import asyncio
import json
import logging
import os
import time

import aiohttp
from aiohttp import web

from . import catalogue as cat
from . import config as config_mod
from .budget import Ledger, Pricing
from .ha import HomeAssistant
from .jellyfin import Jellyfin
from .loop import Runner, Task
from .ma import MusicAssistant
from .speaker import DryRunSpeaker, Speaker
from .tools import ToolError, Tools

_LOGGER = logging.getLogger("voice_claude")

ACK = "Szólok Claude-nak."
SAY = {
    "no_key": "Claude nincs beállítva, hiányzik az API kulcs.",
    "budget": "Elértük a havi Claude keretet, ezt most nem tudom megcsinálni.",
    "busy": "Claude még az előző kérésen dolgozik.",
    "error": "Bocsánat, Claude most nem érhető el.",
}


class Service:
    def __init__(self, cfg, runner_factory, tools, ledger, catalogue, has_key):
        self.cfg = cfg
        self.runner_factory = runner_factory
        self.tools = tools
        self.ledger = ledger
        self.catalogue = catalogue
        self.has_key = has_key
        self.current = None  # (Task, asyncio.Task)
        self.tasks_log = os.path.join(cfg["data_dir"], "tasks.jsonl")

    @property
    def busy(self):
        return bool(self.current and not self.current[1].done())

    async def cancel_current(self):
        if not self.busy:
            return False
        task, job = self.current
        job.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(job), 1)
        except (TimeoutError, asyncio.CancelledError):
            pass
        except Exception:
            pass
        return True

    def log_task(self, task):
        entry = {"id": task.id, "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(task.started_wall)),
                 "text": task.text, "source": task.source, "satellite": task.satellite,
                 "model": getattr(task, "model", None), "outcome": task.outcome,
                 "seconds": round(time.monotonic() - task.started, 1), "turns": task.turns,
                 "cost_usd": round(task.cost, 5), "web_searches": task.web_searches,
                 "tools": [{"name": t["name"], "input": t["input"], "error": t.get("error")} for t in task.tools_called],
                 "status": task.status_spoken, "final": task.final}
        with open(self.tasks_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _LOGGER.info("task %s %s in %.1fs, %d turns, $%.4f, tools=%s, final=%r", task.id, task.outcome,
                     entry["seconds"], task.turns, task.cost, [t["name"] for t in task.tools_called], task.final)

    async def _run(self, task):
        runner = self.runner_factory()
        task.model = runner.model
        try:
            await runner.run(task)
        finally:
            if task.outcome is None:
                task.outcome = "cancelled"
            self.log_task(task)

    def refuse(self, reason):
        return web.json_response({"accepted": False, "reason": reason, "say": SAY[reason]})

    # ------------------------------------------------------------------ handlers
    async def handle_task(self, request):
        try:
            body = await request.json()
        except Exception:
            return self.refuse("error")
        text = (body.get("text") or "").strip() if isinstance(body, dict) else ""
        if not text:
            return self.refuse("error")
        if not self.has_key():
            return self.refuse("no_key")
        if self.ledger.over_limit():
            return self.refuse("budget")
        if self.busy:
            _LOGGER.info("new task while busy: cancelling the running one")
            await self.cancel_current()
            if self.busy:
                return self.refuse("busy")
        task = Task(text, body.get("satellite"), body.get("device_id"), body.get("source"), body.get("lang") or "hu")
        _LOGGER.info("task %s accepted from %s (%s): %s", task.id, task.source, task.satellite, text)
        self.current = (task, asyncio.create_task(self._run(task)))
        return web.json_response({"accepted": True, "ack": ACK, "task_id": task.id})

    async def handle_cancel(self, request):
        return web.json_response({"cancelled": await self.cancel_current()})

    async def handle_quick(self, request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        action = body.get("action")
        player = body.get("player")
        try:
            if action == "list_playlists":
                pls = [p for p in await self.tools.playlists() if p["editable"]]
                return web.json_response({"ok": True, "say": f"{len(pls)} saját lejátszási listád van.",
                                          "playlists": [{"name": p["name"], "uri": p["uri"], "id": p["id"]} for p in pls]})
            if action == "like":
                result = await self.tools.like(None, player)
                track = result["favourited"]
                name = track.get("name") or "a szám"
                return web.json_response({"ok": True, "say": f"Kedvencekhez adtam: {name}.", "track": track,
                                          "dry_run": self.tools.dry_run})
            if action == "save_to_playlist":
                wanted = body.get("playlist")
                pl, alts = await self.tools.match_playlist(wanted, editable_only=True)
                if not pl:
                    names = ", ".join(a["name"] for a in alts)
                    say = (f"Nem találtam ilyen listát. A legközelebbiek: {names}." if wanted and names
                           else "Melyik listába tegyem?" + (f" Például: {names}." if names else ""))
                    return web.json_response({"ok": False, "say": say,
                                              "closest": [{"name": a["name"], "id": a["id"]} for a in alts]})
                p, _queue, item = await self.tools.current_track(player)
                if not item:
                    return web.json_response({"ok": False, "say": f"Most semmi nem szól itt: {p['name']}."})
                result = await self.tools.add_to_playlist(pl["id"], [item["uri"]])
                return web.json_response({"ok": True, "say": f"Hozzáadtam a(z) {pl['name']} listához: {item['name']}.",
                                          "playlist": {"name": pl["name"], "id": pl["id"], "uri": pl["uri"]},
                                          "track": {"name": item["name"], "uri": item["uri"]}, "dry_run": self.tools.dry_run})
            return web.json_response({"ok": False, "say": "Ismeretlen művelet."})
        except ToolError as err:
            _LOGGER.info("quick %s: %s", action, err)
            say = "Most semmi nem szól." if "nothing is playing" in str(err) else "Ezt most nem sikerült megcsinálni."
            return web.json_response({"ok": False, "say": say, "error": str(err)})
        except Exception as err:
            _LOGGER.exception("quick %s failed", action)
            return web.json_response({"ok": False, "say": "Ezt most nem sikerült megcsinálni.", "error": repr(err)[:200]})

    async def handle_health(self, request):
        return web.json_response({"ok": True, "has_key": bool(self.has_key()), "model": self.cfg["anthropic"]["model"],
                                  "busy": self.busy, "dry_run": self.tools.dry_run,
                                  "catalogue_age_h": round((time.time() - self.catalogue.data["built_at"]) / 3600, 2)
                                  if self.catalogue.data else None})

    async def handle_budget(self, request):
        return web.json_response({"month": self.ledger.month(), "spent_usd": round(self.ledger.spent(), 4),
                                  "limit_usd": self.ledger.monthly_limit, "requests": self.ledger.requests()})

    def app(self):
        app = web.Application()
        app.add_routes([web.post("/task", self.handle_task), web.post("/cancel", self.handle_cancel),
                        web.post("/quick", self.handle_quick), web.get("/health", self.handle_health),
                        web.get("/budget", self.handle_budget)])
        return app


async def _refresher(catalogue, hours):
    while True:
        try:
            await catalogue.refresh(force=catalogue.stale())
        except Exception as err:
            _LOGGER.warning("catalogue refresh failed: %r", err)
        await asyncio.sleep(max(600, hours * 3600 / 6))  # check often, rebuild when stale


def build(cfg, dry_run=False, client=None, session=None):
    """Wire everything together. Returns (Service, cleanup coroutine function)."""
    os.makedirs(cfg["data_dir"], exist_ok=True)
    session = session or aiohttp.ClientSession()
    hcfg, mcfg, jcfg, acfg = cfg["home_assistant"], cfg["music_assistant"], cfg["jellyfin"], cfg["anthropic"]
    ha = HomeAssistant(hcfg["url"], config_mod.secret(cfg, hcfg["token_file"]), session)
    ma = MusicAssistant(mcfg["url"], config_mod.secret(cfg, mcfg["token_file"]), session)
    jf_key = config_mod.secret(cfg, jcfg["key_file"])
    jf = Jellyfin(jcfg["url"], jf_key, jcfg.get("user"), session,
                  titles_path=os.path.join(cfg["data_dir"], "titles_hu.json")) if jf_key else None
    catalogue = cat.Catalogue(os.path.join(cfg["data_dir"], "catalogue.json"),
                              lambda: cat.build(ma, jf, cfg["catalogue"]), cfg["catalogue"]["refresh_hours"])
    tools = Tools(ma, jf, ha, catalogue, cfg, dry_run=dry_run)
    speaker = DryRunSpeaker() if dry_run else Speaker(ha)
    ledger = Ledger(os.path.join(cfg["data_dir"], "ledger.jsonl"), Pricing(cfg["pricing"]),
                    cfg["limits"]["monthly_usd"], cfg.get("timezone", "Europe/Budapest"))

    def api_key():
        return config_mod.secret(cfg, acfg["key_file"])

    clients = {}

    def get_client():
        key = api_key()
        if client is not None:
            return client
        if key not in clients:
            import anthropic
            clients.clear()
            clients[key] = anthropic.AsyncAnthropic(api_key=key, max_retries=2, timeout=60)
        return clients[key]

    def runner_factory():
        return Runner(cfg, get_client(), tools, speaker, ledger, catalogue)

    service = Service(cfg, runner_factory, tools, ledger, catalogue, has_key=lambda: bool(api_key()) or client is not None)
    service.speaker = speaker

    async def cleanup():
        await ma.close()
        await session.close()

    return service, cleanup


def main():
    parser = argparse.ArgumentParser(description="voice-claude service")
    parser.add_argument("--config", default=os.environ.get("VOICE_CLAUDE_CONFIG", "config.json"))
    parser.add_argument("--dry-run", action="store_true", help="log writes and speech instead of doing them")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cfg = config_mod.load(args.config)
    dry = args.dry_run or cfg.get("dry_run", False)

    async def start():
        service, cleanup = build(cfg, dry_run=dry)
        app = service.app()
        refresher = None

        async def on_start(_app):
            nonlocal refresher
            refresher = asyncio.create_task(_refresher(service.catalogue, cfg["catalogue"]["refresh_hours"]))

        async def on_stop(_app):
            if refresher:
                refresher.cancel()
            await service.cancel_current()
            await cleanup()

        app.on_startup.append(on_start)
        app.on_cleanup.append(on_stop)
        _LOGGER.info("voice-claude on %s:%s, model %s%s", cfg["listen"]["host"], cfg["listen"]["port"],
                     cfg["anthropic"]["model"], " (DRY RUN)" if dry else "")
        return app

    if cfg["anthropic"]["model"] not in cfg["anthropic"]["allowed_models"]:
        raise SystemExit(f"model {cfg['anthropic']['model']} is not in allowed_models")
    for model in cfg["anthropic"]["allowed_models"]:
        if model not in cfg["pricing"]["models"]:
            raise SystemExit(f"no pricing configured for {model}")
    web.run_app(start(), host=cfg["listen"]["host"], port=cfg["listen"]["port"], print=None, access_log=None)


if __name__ == "__main__":
    main()
