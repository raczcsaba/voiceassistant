"""Offline tests: the Claude loop with a scripted fake model, the status rate limit, limits, budget, API.

Run: python -m unittest discover -s tests -v   (from the claude-worker directory)
"""
import asyncio
import copy
import itertools
import json
import os
import tempfile
import unittest
from types import SimpleNamespace

from aiohttp.test_utils import TestClient, TestServer
from voice_claude import config as config_mod
from voice_claude.budget import Ledger, Pricing
from voice_claude.loop import FAIL, Runner, Task
from voice_claude.server import SAY, Service
from voice_claude.speaker import DryRunSpeaker, StatusGate
from voice_claude.textutil import for_speech

PRICING = {"web_search_per_1000": 10.0, "models": {
    "claude-haiku-5-5": {"input": 0.10, "cache_write_5m": 0.125, "cache_write_1h": 0.20, "cache_read": 0.01, "output": 0.50},
    "claude-sonnet-5-5": {"input": 2.0, "cache_write_5m": 2.5, "cache_write_1h": 4.0, "cache_read": 0.10, "output": 10.0}}}


def make_cfg(tmp, **over):
    cfg = copy.deepcopy(config_mod.DEFAULTS)
    cfg["data_dir"] = tmp
    cfg["pricing"] = PRICING
    cfg["anthropic"]["model"] = "claude-haiku-5-5"
    cfg["home_assistant"]["default_satellite"] = "assist_satellite.tablet"
    # fast timings so the tests run in a few seconds
    cfg["status"].update({"min_gap_s": 0.3, "quiet_after_ack_s": 0.2, "max_per_task": 2, "idle_notice_s": 30})
    for section, values in over.items():
        cfg[section].update(values)
    return cfg


def text(t):
    return SimpleNamespace(type="text", text=t)


_TOOL_IDS = itertools.count(1)


def tool(name, args):
    return SimpleNamespace(type="tool_use", id=f"toolu_{next(_TOOL_IDS)}", name=name, input=args)


def response(blocks, stop, inp=1000, out=100, searches=0):
    usage = SimpleNamespace(input_tokens=inp, output_tokens=out, cache_read_input_tokens=0,
                            cache_creation_input_tokens=0, cache_creation=None,
                            server_tool_use=SimpleNamespace(web_search_requests=searches))
    return SimpleNamespace(content=blocks, stop_reason=stop, usage=usage)


class FakeClient:
    """messages.create() returns scripted responses; a step may be (delay_seconds, response)."""

    def __init__(self, script, repeat_last=False):
        self.script = list(script)
        self.repeat_last = repeat_last
        self.calls = []
        self.messages = self

    async def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})  # snapshot: the list keeps growing
        step = self.script[0] if (self.repeat_last and len(self.script) == 1) else self.script.pop(0)
        delay, resp = step if isinstance(step, tuple) else (0, step)
        if delay:
            await asyncio.sleep(delay)
        return resp


class FakePlayers:
    default = "media_player.pi"

    async def all(self):
        return [{"entity_id": "media_player.pi", "name": "Pi", "state": "playing", "title": "Song", "artist": "Band"}]


class FakeTools:
    def __init__(self):
        self.players = FakePlayers()
        self.calls = []
        self.dry_run = True
        self.on_background_error = None

    async def run(self, name, args):
        self.calls.append((name, args))
        if name == "search_music":
            return json.dumps({"tracks": [{"uri": "tidal://track/1", "name": "Get Lucky", "artist": "Daft Punk"}]}), False
        if name == "play_music":
            return json.dumps({"ok": True, "player": "Pi"}), False
        return json.dumps({"error": "unknown"}), True

    async def playlists(self):
        return [{"name": "rock", "uri": "library://playlist/36", "id": "36", "editable": True}]


class FakeCatalogue:
    data = {"built_at": 0, "text": "CATALOGUE", "films": []}

    async def get(self):
        return self.data


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def runner(self, script, repeat_last=False, **over):
        cfg = make_cfg(self.tmp, **over)
        self.cfg = cfg
        self.client = FakeClient(script, repeat_last)
        self.tools = FakeTools()
        self.speaker = DryRunSpeaker()
        self.ledger = Ledger(os.path.join(self.tmp, "ledger.jsonl"), Pricing(PRICING), cfg["limits"]["monthly_usd"])
        return Runner(cfg, self.client, self.tools, self.speaker, self.ledger, FakeCatalogue())

    def spoken(self):
        return [t for _ts, _sat, t in self.speaker.spoken]


class LoopTests(Base):
    async def test_tool_sequence_and_final_answer(self):
        r = self.runner([
            response([tool("search_music", {"query": "Daft Punk Get Lucky"})], "tool_use"),
            response([tool("play_music", {"uris": ["tidal://track/1"]})], "tool_use"),
            response([text("Elindítottam a **Get Lucky**-t a Pi-n. https://x.y")], "end_turn"),
        ])
        task = await r.run(Task("játszd le a Daft Punk Get Lucky-t"))
        self.assertEqual(task.outcome, "ok")
        self.assertEqual([c[0] for c in self.tools.calls], ["search_music", "play_music"])
        self.assertEqual(self.spoken(), ["Elindítottam a Get Lucky-t a Pi-n."])
        self.assertEqual(task.turns, 3)
        self.assertEqual(self.ledger.requests(), 3)
        self.assertAlmostEqual(task.cost, 3 * (1000 * 0.10 + 100 * 0.50) / 1e6, places=9)
        # system: prompt + cached catalogue block; the request goes in the first user turn
        first = self.client.calls[0]
        self.assertEqual(first["system"][1]["cache_control"], {"type": "ephemeral"})
        self.assertIn("Daft Punk Get Lucky", first["messages"][0]["content"])
        self.assertEqual(first["model"], "claude-haiku-5-5")
        # tool results go back in one user message, with the matching id
        second = self.client.calls[1]["messages"]
        self.assertEqual(second[-1]["content"][0]["type"], "tool_result")
        self.assertEqual(second[-1]["content"][0]["tool_use_id"], second[-2]["content"][0].id)

    async def test_status_rate_limit(self):
        # quiet 0.2 s after the ack, 0.3 s between lines, at most 2 per task
        script = [
            response([tool("report_status", {"text": "Első."})], "tool_use"),              # t=0: held, said at 0.2
            (0.25, response([tool("report_status", {"text": "Kiesik."})], "tool_use")),    # too soon: held
            response([tool("report_status", {"text": "Második."})], "tool_use"),          # replaces it, said at 0.5
            (0.35, response([tool("report_status", {"text": "Harmadik."})], "tool_use")),  # t=0.6: limit reached
            response([text("Kész vagyok.")], "end_turn"),
        ]
        r = self.runner(script)
        task = await r.run(Task("valami hosszú"))
        await asyncio.sleep(0.05)
        results = [json.loads(c["messages"][-1]["content"][0]["content"]) for c in self.client.calls[1:]]
        self.assertEqual([x.get("reason") for x in results], ["too_early", "too_soon", "too_soon", "limit"])
        self.assertEqual(self.spoken(), ["Első.", "Második.", "Kész vagyok."])
        times = [ts for ts, _s, _t in self.speaker.spoken]
        self.assertGreaterEqual(times[1] - times[0], 0.3)
        self.assertEqual(task.status_spoken, ["Első.", "Második."])

    async def test_held_status_dropped_when_task_ends(self):
        r = self.runner([response([tool("report_status", {"text": "Keresem."})], "tool_use"),
                         response([text("Kész.")], "end_turn")])
        await r.run(Task("gyors"))
        await asyncio.sleep(0.3)
        self.assertEqual(self.spoken(), ["Kész."])

    async def test_idle_notice_once(self):
        r = self.runner([(0.9, response([text("Kész.")], "end_turn"))], status={"idle_notice_s": 0.3})
        await r.run(Task("lassú kérés"))
        self.assertEqual(self.spoken(), ["Még dolgozom rajta.", "Kész."])

    async def test_timeout(self):
        r = self.runner([(2.0, response([text("túl késő")], "end_turn"))], limits={"max_seconds": 0.3})
        task = await r.run(Task("lassú"))
        self.assertEqual(task.outcome, "timeout")
        self.assertEqual(self.spoken(), [FAIL["timeout"]])

    async def test_turn_limit(self):
        r = self.runner([response([tool("search_music", {"query": "x"})], "tool_use")], repeat_last=True,
                        limits={"max_turns": 4})
        task = await r.run(Task("végtelen"))
        self.assertEqual(task.outcome, "turns")
        self.assertEqual(len(self.client.calls), 4)
        self.assertEqual(self.spoken(), [FAIL["turns"]])

    async def test_task_cost_limit(self):
        # 400k input tokens on haiku = $0.04 per call; limit $0.05 -> stops after the second call
        r = self.runner([response([tool("search_music", {"query": "x"})], "tool_use", inp=400_000)], repeat_last=True,
                        limits={"max_task_usd": 0.05})
        task = await r.run(Task("drága"))
        self.assertEqual(task.outcome, "cost")
        self.assertEqual(len(self.client.calls), 2)

    async def test_web_search_tool_dropped_after_three(self):
        r = self.runner([
            response([tool("search_music", {"query": "x"})], "tool_use", searches=3),
            response([text("ok")], "end_turn")])
        await r.run(Task("keress a weben"))
        def names(call):
            return [t.get("name") for t in call["tools"]]

        self.assertIn("web_search", names(self.client.calls[0]))
        self.assertNotIn("web_search", names(self.client.calls[1]))

    async def test_api_error_apology(self):
        class Broken(FakeClient):
            async def create(self, **kwargs):
                raise RuntimeError("boom")
        r = self.runner([])
        r.client = Broken([])
        task = await r.run(Task("bármi"))
        self.assertEqual(task.outcome, "api")
        self.assertEqual(self.spoken(), [FAIL["api"]])

    async def test_cancel_speaks_nothing(self):
        r = self.runner([(5.0, response([text("soha")], "end_turn"))])
        job = asyncio.create_task(r.run(Task("lassú")))
        await asyncio.sleep(0.1)
        job.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await job
        self.assertEqual(self.spoken(), [])


class ServiceTests(Base):
    async def asyncSetUp(self):
        self.script = []

    async def client_for(self, script, has_key=True, **over):
        runner = self.runner(script, **over)
        self.service = Service(self.cfg, lambda: runner, self.tools, self.ledger, FakeCatalogue(), lambda: has_key)
        client = TestClient(TestServer(self.service.app()))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    async def test_accept_and_health(self):
        c = await self.client_for([(0.3, response([text("Kész.")], "end_turn"))])
        r = await (await c.post("/task", json={"text": "szia", "lang": "hu", "satellite": None, "source": "test"})).json()
        self.assertEqual(r, {"accepted": True, "ack": "Szólok Claude-nak.", "task_id": r["task_id"]})
        h = await (await c.get("/health")).json()
        self.assertTrue(h["busy"])
        self.assertTrue(h["has_key"])
        await self.service.current[1]
        self.assertFalse((await (await c.get("/health")).json())["busy"])
        self.assertEqual(self.speaker.spoken[-1][1], "assist_satellite.tablet")  # default satellite
        with open(os.path.join(self.tmp, "tasks.jsonl")) as f:
            logged = json.loads(f.readlines()[-1])
        self.assertEqual(logged["outcome"], "ok")
        self.assertEqual(logged["final"], "Kész.")
        b = await (await c.get("/budget")).json()
        self.assertEqual(b["requests"], 1)
        self.assertEqual(b["limit_usd"], 30.0)

    async def test_cancel_endpoint(self):
        c = await self.client_for([(5.0, response([text("soha")], "end_turn"))])
        await c.post("/task", json={"text": "lassú"})
        await asyncio.sleep(0.05)
        self.assertEqual(await (await c.post("/cancel")).json(), {"cancelled": True})
        self.assertEqual(await (await c.post("/cancel")).json(), {"cancelled": False})
        self.assertEqual(self.spoken(), [])

    async def test_new_task_cancels_old(self):
        c = await self.client_for([(5.0, response([text("régi")], "end_turn")), response([text("új")], "end_turn")])
        await c.post("/task", json={"text": "első"})
        await asyncio.sleep(0.05)
        first = self.service.current[0]
        r = await (await c.post("/task", json={"text": "második"})).json()
        self.assertTrue(r["accepted"])
        await self.service.current[1]
        self.assertEqual(first.outcome, "cancelled")
        self.assertEqual(self.spoken(), ["új"])

    async def test_budget_refusal(self):
        c = await self.client_for([response([text("x")], "end_turn")], limits={"monthly_usd": 0.001})
        self.ledger.record("claude-sonnet-5-5", {"input_tokens": 1000, "output_tokens": 0, "cache_read_input_tokens": 0,
                                                 "cache_creation_input_tokens": 0})
        r = await (await c.post("/task", json={"text": "szia"})).json()
        self.assertEqual(r, {"accepted": False, "reason": "budget",
                             "say": "Elértük a havi Claude keretet, ezt most nem tudom megcsinálni."})

    async def test_no_key(self):
        c = await self.client_for([], has_key=False)
        r = await (await c.post("/task", json={"text": "szia"})).json()
        self.assertEqual((r["accepted"], r["reason"], r["say"]), (False, "no_key", SAY["no_key"]))
        self.assertFalse((await (await c.get("/health")).json())["has_key"])


class UnitTests(unittest.TestCase):
    def test_gate(self):
        now = [100.0]
        gate = StatusGate(6, 4, 2, clock=lambda: now[0])
        self.assertEqual(gate.check(), "too_early")
        now[0] = 104.0
        self.assertIsNone(gate.check())
        gate.mark()
        now[0] = 109.9
        self.assertEqual(gate.check(), "too_soon")
        now[0] = 110.0
        gate.mark()
        now[0] = 200.0
        self.assertEqual(gate.check(), "limit")

    def test_pricing(self):
        p = Pricing(PRICING)
        usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=1_000_000, cache_read_input_tokens=1_000_000,
                                cache_creation_input_tokens=1_000_000, cache_creation=None,
                                server_tool_use=SimpleNamespace(web_search_requests=2))
        c = p.cost("claude-sonnet-5-5", usage)
        self.assertEqual((c["input"], c["output"], c["cache_read"], c["cache_write"], c["web_search"]),
                         (2.0, 10.0, 0.1, 2.5, 0.02))
        self.assertAlmostEqual(c["total"], 14.62)

    def test_for_speech(self):
        self.assertEqual(for_speech("# Cím\n- **egy** 🎷\n- kettő https://a.b/c"), "Cím egy kettő")


if __name__ == "__main__":
    unittest.main()
