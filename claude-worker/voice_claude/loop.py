"""One Claude task: the manual tool-use loop with limits, status speech and cost accounting."""
import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from . import prompt
from .speaker import StatusGate
from .textutil import for_speech
from .tools import TOOL_DEFS

_LOGGER = logging.getLogger(__name__)

FAIL = {
    "timeout": "Bocsánat, ez túl sokáig tartott, abbahagytam.",
    "turns": "Bocsánat, ehhez túl sok lépés kellett volna, abbahagytam.",
    "cost": "Bocsánat, ez a kérés túllépte a feladatonkénti költségkeretet, abbahagytam.",
    "budget": "Elértük a havi Claude keretet, ezt most nem tudom befejezni.",
    "refusal": "Bocsánat, ebben nem tudok segíteni.",
    "error": "Bocsánat, hiba történt, nem tudtam befejezni a kérést.",
    "api": "Bocsánat, most nem érem el Claude-ot, próbáld újra később.",
}


class TaskAborted(Exception):
    def __init__(self, reason, detail=""):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


class Task:
    def __init__(self, text, satellite=None, device_id=None, source=None, lang="hu"):
        self.id = uuid.uuid4().hex[:10]
        self.text = text
        self.satellite = satellite
        self.device_id = device_id
        self.source = source
        self.lang = lang
        self.started = time.monotonic()
        self.started_wall = time.time()
        self.tools_called = []
        self.status_spoken = []
        self.cost = 0.0
        self.turns = 0
        self.web_searches = 0
        self.no_web = False
        self.pending_status = None
        self.done_event = None
        self.final = None
        self.outcome = None


class Runner:
    """Runs tasks. `client` needs an async messages.create(**kwargs) like anthropic.AsyncAnthropic."""

    def __init__(self, cfg, client, tools, speaker, ledger, catalogue, model=None, clock=time.monotonic):
        self.cfg = cfg
        self.client = client
        self.tools = tools
        self.speaker = speaker
        self.ledger = ledger
        self.catalogue = catalogue
        self.model = model or cfg["anthropic"]["model"]
        self.clock = clock
        self.tz = ZoneInfo(cfg.get("timezone", "Europe/Budapest"))
        self.tools.on_background_error = self._background_error
        self._last_satellite = None

    def satellite_for(self, task):
        return task.satellite or self.cfg["home_assistant"].get("default_satellite")

    async def _background_error(self, text):
        if self._last_satellite:
            await self.speaker.say(self._last_satellite, text)

    def _tool_defs(self, task):
        acfg = self.cfg["anthropic"]
        defs = [dict(t) for t in TOOL_DEFS]
        remaining = acfg.get("max_web_searches", 3) - task.web_searches
        if remaining > 0 and not task.no_web:
            kinds = acfg.get("web_search_tool") or {}
            kind = kinds.get(self.model) or kinds.get("default")
            if kind:
                ws = {"type": kind, "name": "web_search", "max_uses": acfg.get("max_web_searches", 3)}
                if acfg.get("web_search_location"):
                    ws["user_location"] = acfg["web_search_location"]
                defs.append(ws)
        return defs

    async def run(self, task):
        """Run to completion; speaks the answer (or an apology). Re-raises CancelledError."""
        satellite = self.satellite_for(task)
        self._last_satellite = satellite
        scfg = self.cfg["status"]
        gate = StatusGate(scfg["min_gap_s"], scfg["quiet_after_ack_s"], scfg["max_per_task"], clock=self.clock)
        done = asyncio.Event()
        task.done_event = done
        idle = asyncio.create_task(self._idle_notice(task, gate, satellite, done))
        try:
            limit = self.cfg["limits"]["max_seconds"]
            remaining = limit - (self.clock() - task.started)
            try:
                final = await asyncio.wait_for(self._loop(task, gate, satellite), max(0.1, remaining))
            except TimeoutError:
                raise TaskAborted("timeout") from None
            task.final = for_speech(final) or "Kész."
            task.outcome = "ok"
            done.set()
            idle.cancel()
            await self.speaker.say(satellite, task.final)
        except TaskAborted as err:
            done.set()
            idle.cancel()
            task.outcome = err.reason
            task.final = FAIL.get(err.reason, FAIL["error"])
            if err.detail:
                task.final = f"{task.final} {err.detail}".strip()
            _LOGGER.warning("task %s aborted: %s %s", task.id, err.reason, err.detail)
            await self.speaker.say(satellite, task.final)
        except asyncio.CancelledError:
            task.outcome = "cancelled"
            raise
        except Exception:
            _LOGGER.exception("task %s failed", task.id)
            task.outcome = "error"
            task.final = FAIL["error"]
            await self.speaker.say(satellite, task.final)
        finally:
            done.set()
            idle.cancel()
        return task

    async def _idle_notice(self, task, gate, satellite, done):
        """One generic 'still working' line if nothing was said for idle_notice_s."""
        wait = self.cfg["status"]["idle_notice_s"]
        while not done.is_set():
            left = wait - gate.since_last()
            if left <= 0:
                if gate.check() is None and not done.is_set():
                    gate.mark()
                    text = self.cfg["status"]["idle_text"]
                    task.status_spoken.append(text)
                    asyncio.create_task(self.speaker.say(satellite, text))
                return
            await asyncio.sleep(min(left, 1.0))

    async def _status(self, task, gate, satellite, text):
        text = for_speech(text, limit=120)
        if not text:
            return {"spoken": False, "reason": "empty"}
        reason = gate.check()
        if reason in ("too_early", "too_soon"):
            # Hold the newest line and say it as soon as the rate limit allows, unless the task ends first
            first = task.pending_status is None
            task.pending_status = text
            if first:
                asyncio.create_task(self._speak_pending(task, gate, satellite))
            return {"spoken": False, "reason": reason, "queued": True}
        if reason:
            return {"spoken": False, "reason": reason}
        self._speak_status(task, gate, satellite, text)
        return {"spoken": True}

    def _speak_status(self, task, gate, satellite, text):
        gate.mark()
        task.status_spoken.append(text)
        # Don't block the loop on the announcement; the speaker serialises it with later ones.
        asyncio.create_task(self.speaker.say(satellite, text))

    async def _speak_pending(self, task, gate, satellite):
        done = task.done_event
        while task.pending_status and not (done and done.is_set()):
            reason = gate.check()
            if reason is None:
                text, task.pending_status = task.pending_status, None
                self._speak_status(task, gate, satellite, text)
                return
            if reason == "limit":
                break
            await asyncio.sleep(0.05)
        task.pending_status = None

    async def _loop(self, task, gate, satellite):
        acfg = self.cfg["anthropic"]
        limits = self.cfg["limits"]
        catalogue = await self.catalogue.get()
        system = [
            {"type": "text", "text": prompt.system_prompt(self.cfg["music_assistant"].get("player_hint"))},
            {"type": "text", "text": catalogue["text"], "cache_control": {"type": "ephemeral"}},
        ]
        try:
            players = await self.tools.players.all()
        except Exception as err:
            _LOGGER.warning("player list failed: %r", err)
            players = []
        now = datetime.now(self.tz).strftime("%Y-%m-%d %H:%M, %A")
        messages = [{"role": "user", "content": prompt.user_turn(task.text, now, satellite, task.source, players)}]

        while True:
            if task.turns >= limits["max_turns"]:
                raise TaskAborted("turns")
            if self.ledger.over_limit():
                raise TaskAborted("budget")
            task.turns += 1
            kwargs = {"model": self.model, "max_tokens": acfg["max_tokens"], "system": system,
                      "tools": self._tool_defs(task), "messages": messages,
                      "cache_control": {"type": "ephemeral"}}
            if acfg.get("effort"):
                kwargs["output_config"] = {"effort": acfg["effort"]}
            try:
                resp = await self.client.messages.create(**kwargs)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.warning("Claude API call failed: %r", err)
                if "web_search" in str(err) and not task.no_web:
                    # A rejected web search config shouldn't break the whole assistant: retry without it
                    task.no_web = True
                    task.turns -= 1
                    continue
                raise TaskAborted("api") from err
            cost = self.ledger.record(self.model, resp.usage, task_id=task.id)
            task.cost += cost["total"]
            server = getattr(resp.usage, "server_tool_use", None)
            task.web_searches += int(getattr(server, "web_search_requests", 0) or 0) if server else 0
            messages.append({"role": "assistant", "content": resp.content})
            for block in resp.content:
                if block.type == "server_tool_use":
                    task.tools_called.append({"name": block.name, "input": block.input})

            if resp.stop_reason == "refusal":
                raise TaskAborted("refusal")
            if task.cost > limits["max_task_usd"] and resp.stop_reason in ("tool_use", "pause_turn"):
                raise TaskAborted("cost")
            if resp.stop_reason == "pause_turn":
                continue
            if resp.stop_reason == "tool_use":
                uses = [b for b in resp.content if b.type == "tool_use"]
                results = await asyncio.gather(*(self._run_tool(task, gate, satellite, b) for b in uses))
                messages.append({"role": "user", "content": list(results)})
                continue
            text = " ".join(b.text for b in resp.content if b.type == "text").strip()
            return text

    async def _run_tool(self, task, gate, satellite, block):
        started = time.monotonic()
        if block.name == "report_status":
            result = await self._status(task, gate, satellite, (block.input or {}).get("text", ""))
            content, is_error = json.dumps(result), False
        else:
            content, is_error = await self.tools.run(block.name, block.input)
        task.tools_called.append({"name": block.name, "input": block.input, "error": is_error,
                                  "ms": int((time.monotonic() - started) * 1000), "result": content[:300]})
        out = {"type": "tool_result", "tool_use_id": block.id, "content": content}
        if is_error:
            out["is_error"] = True
        return out
