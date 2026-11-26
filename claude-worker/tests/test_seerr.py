"""Offline tests: queue editing, short answers, the Seerr proposal state machine, the download poller and /pending.

Run: python -m unittest discover -s tests -v   (from the claude-worker directory)
"""
import asyncio
import copy
import json
import os
import tempfile
import time
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from aiohttp.test_utils import TestClient, TestServer
from voice_claude import config as config_mod
from voice_claude.budget import Ledger, Pricing
from voice_claude.loop import Runner, Task
from voice_claude.seerr import Pending, Seerr, Tracker, answer_kind, default_seasons
from voice_claude.server import Service
from voice_claude.speaker import DryRunSpeaker
from voice_claude.textutil import shorten
from voice_claude.tools import Tools

from tests.test_loop import PRICING, FakeCatalogue, FakeClient, FakePlayers, FakeTools, make_cfg, response, text, tool

TZ = ZoneInfo("Europe/Budapest")


# ---------------------------------------------------------------- fakes
class QueueMA:
    """A Music Assistant with one queue: current_index 1, the next item already buffered (index 2)."""

    def __init__(self, n=8, buffered=2):
        self.calls = []
        names = [("Metallica", "One"), ("Daft Punk", "Get Lucky"), ("Muse", "Uprising"), ("Metallica", "Fuel"),
                 ("Queen", "Bohemian Rhapsody"), ("Metallica", "Enter Sandman"), ("AC/DC", "T.N.T."), ("Muse", "Madness")]
        self.items = [{"queue_item_id": f"q{i}", "name": t, "media_item": {"name": t, "artists": [{"name": a}]}}
                      for i, (a, t) in enumerate(names[:n])]
        self.queue = {"queue_id": "pi_q", "current_index": 1, "index_in_buffer": buffered, "items": n,
                      "shuffle_enabled": False, "repeat_mode": "off"}

    async def call(self, command, **args):
        self.calls.append((command, args))
        if command == "player_queues/get_active_queue":
            return dict(self.queue)
        if command == "player_queues/items":
            return self.items[args["offset"]: args["offset"] + args["limit"]]
        return None


class QueueHA:
    async def states(self):
        return [{"entity_id": "media_player.pi", "state": "playing",
                 "attributes": {"friendly_name": "Pi", "mass_player_type": "player", "active_queue": "pi_q"}}]


def queue_tools(dry_run=True, **kw):
    cfg = copy.deepcopy(config_mod.DEFAULTS)
    cfg["music_assistant"]["default_player"] = "media_player.pi"
    ma = QueueMA(**kw)
    return Tools(ma, None, QueueHA(), None, cfg, dry_run=dry_run), ma


class FakeSeerr:
    """Seerr with a scripted status per tmdb id; request() is recorded, never sent."""

    def __init__(self, statuses=None, seasons=3):
        self.statuses = statuses or {}
        self.season_count = seasons
        self.posts = []
        self.dry_run = False
        self.detail_calls = 0

    async def search(self, query, limit=5):
        return [{"tmdb_id": 693134, "type": "movie", "title": "Dűne: Második rész", "original": "Dune: Part Two",
                 "year": 2024, "status": "not_requested"}]

    async def details(self, media_type, tmdb_id):
        self.detail_calls += 1
        status = self.statuses.get(tmdb_id)
        out = {"id": tmdb_id, "title" if media_type == "movie" else "name": f"Title {tmdb_id}",
               "releaseDate": "2024-02-27", "mediaInfo": {"status": status} if status else None}
        if media_type == "tv":
            out["seasons"] = [{"seasonNumber": n} for n in range(0, self.season_count + 1)]
            out["firstAirDate"] = "2020-01-01"
        return out

    async def request(self, media_type, tmdb_id, seasons=None):
        body = {"mediaType": media_type, "mediaId": tmdb_id}
        if seasons:
            body["seasons"] = seasons
        self.posts.append(body)
        return {"id": 99, "status": 2}


def seerr_tools(tmp, statuses=None, seasons=3):
    cfg = copy.deepcopy(config_mod.DEFAULTS)
    tools = Tools(None, None, None, None, cfg, dry_run=False)
    tools.seerr = FakeSeerr(statuses, seasons)
    tools.pending = Pending(180)
    tools.tracker = Tracker(os.path.join(tmp, "requests.json"), tools.seerr, None)
    tools.task_ctx = {"satellite": "assist_satellite.tablet", "ask": False}
    return tools


# ---------------------------------------------------------------- queue
class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_queue(self):
        tools, _ma = queue_tools()
        out = json.loads((await tools.run("get_queue", {"limit": 3}))[0])
        self.assertEqual(out["current"], {"title": "Get Lucky", "artist": "Daft Punk", "id": "q1"})
        self.assertEqual(out["upcoming"][0], {"pos": 1, "id": "q2", "title": "Uprising", "artist": "Muse", "locked": True})
        self.assertEqual([u["pos"] for u in out["upcoming"]], [1, 2, 3])
        self.assertEqual(out["upcoming_total"], 6)

    async def test_remove_by_artist_skips_buffered_and_played(self):
        tools, ma = queue_tools(dry_run=False)
        out, err = await tools.run("edit_queue", {"ops": [{"op": "remove", "match": "metallica"}]})
        self.assertFalse(err, out)
        deletes = [a["item_id_or_index"] for c, a in ma.calls if c == "player_queues/delete_item"]
        self.assertEqual(deletes, ["q5", "q3"])  # q0 was already played; highest index first

    async def test_remove_next_two_and_move_next(self):
        tools, _ma = queue_tools()
        out = json.loads((await tools.run("edit_queue", {"ops": [{"op": "remove", "count": 2},
                                                                 {"op": "move_next", "match": "AC/DC"}]}))[0])
        self.assertIn("problems", out)  # the very next one is buffered
        writes = [(w[1], w[2]) for w in tools.writes]
        self.assertEqual(writes[0], ("player_queues/delete_item", {"queue_id": "pi_q", "item_id_or_index": "q4"}))
        self.assertEqual(writes[1], ("player_queues/delete_item", {"queue_id": "pi_q", "item_id_or_index": "q3"}))
        # dry run: the queue is unchanged, AC/DC (index 6) moves to index 3, right after the buffered one
        self.assertEqual(writes[2], ("player_queues/move_item", {"queue_id": "pi_q", "queue_item_id": "q6", "pos_shift": -3}))

    async def test_clear_upcoming_keeps_current_shuffle_repeat(self):
        tools, ma = queue_tools(dry_run=False, buffered=None)
        out, err = await tools.run("edit_queue", {"ops": [{"op": "clear_upcoming"}, {"op": "shuffle", "value": True},
                                                          {"op": "repeat", "value": "all"}]})
        self.assertFalse(err, out)
        deletes = [a["item_id_or_index"] for c, a in ma.calls if c == "player_queues/delete_item"]
        self.assertEqual(deletes, [7, 6, 5, 4, 3, 2])
        self.assertIn(("player_queues/shuffle", {"queue_id": "pi_q", "shuffle_enabled": True}), ma.calls)
        self.assertIn(("player_queues/repeat", {"queue_id": "pi_q", "repeat_mode": "all"}), ma.calls)

    async def test_nothing_matches_is_an_error(self):
        tools, _ma = queue_tools()
        out, err = await tools.run("edit_queue", {"ops": [{"op": "remove", "match": "Taylor Swift"}]})
        self.assertTrue(err)
        self.assertEqual(tools.writes, [])


# ---------------------------------------------------------------- short answers
class ShortTests(unittest.TestCase):
    def test_short_text_untouched(self):
        self.assertEqual(shorten("Elindítottam a rock listádat a Pi-n."), "Elindítottam a rock listádat a Pi-n.")

    def test_keeps_whole_sentences(self):
        long = ("Elindítottam a rock listádat a Pi-n. A lista 297 számot tartalmaz, többek között a Led Zeppelin, "
                "a Queen és a Pink Floyd dalait. Keverve szól, hogy változatos legyen. Jó szórakozást kívánok!")
        out = shorten(long, 180)
        self.assertLessEqual(len(out), 180)
        self.assertTrue(out.startswith("Elindítottam a rock listádat a Pi-n."))
        self.assertTrue(out.endswith("."))

    def test_one_long_sentence_cut_at_word(self):
        out = shorten("Hozzáadtam " + "nagyon " * 40 + "sok számot.", 180)
        self.assertLessEqual(len(out), 181)
        self.assertTrue(out.endswith("."))

    def test_question_kept(self):
        long = "Az Érkezés 2016-os film, " + "nagyon " * 30 + "jó. Denis Villeneuve rendezte. Letöltsem?"
        self.assertTrue(shorten(long, 180, keep_question=True).endswith("Letöltsem?"))


class ShortLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_final_trimmed_and_status_capped(self):
        tmp = tempfile.mkdtemp()
        cfg = make_cfg(tmp)
        speaker = DryRunSpeaker()
        client = FakeClient([
            response([tool("report_status", {"text": "Megnézem most gyorsan a könyvtáradban lévő rock számokat."})], "tool_use"),
            (0.25, response([text("Elindítottam a rock listádat a Pi-n. " + "Benne van sok jó szám, " * 10 + "és még több.")],
                            "end_turn"))])
        runner = Runner(cfg, client, FakeTools(), speaker, Ledger(os.path.join(tmp, "l.jsonl"), Pricing(PRICING), 30),
                        FakeCatalogue())
        task = await runner.run(Task("rakj be valami rock zenét"))
        await asyncio.sleep(0.05)
        self.assertEqual(task.status_spoken, ["Megnézem most gyorsan a könyvtáradban lévő."])
        self.assertEqual(task.final, "Elindítottam a rock listádat a Pi-n.")


# ---------------------------------------------------------------- answers and the pending state
class AnswerTests(unittest.TestCase):
    def test_phrases(self):
        for t in ("igen", "Igen!", "mehet", "töltsd le", "jó", "oké", "kérem", "igen, kérem", "persze", "jöhet"):
            self.assertEqual(answer_kind(t), "yes", t)
        for t in ("nem", "Nem, köszi", "ne", "mégse", "hagyd"):
            self.assertEqual(answer_kind(t), "no", t)
        for t in ("mást", "inkább mást", "nem, inkább valami mást", "másikat kérek"):
            self.assertEqual(answer_kind(t), "another", t)
        for t in ("kapcsold le a lámpát", "milyen hosszú a film", "", "igen de előbb nézd meg mennyi hely van"):
            self.assertIsNone(answer_kind(t), t)

    def test_expiry(self):
        now = [100.0]
        p = Pending(180, clock=lambda: now[0])
        self.assertEqual(p.status()["pending"], False)
        p.set(kind="seerr", tmdb_id=1, type="movie", title="Dűne", satellite="assist_satellite.tablet")
        now[0] = 160.0
        self.assertEqual(p.status(), {"pending": True, "kind": "seerr", "title": "Dűne",
                                      "satellite": "assist_satellite.tablet", "expires_in": 120})
        now[0] = 280.0
        self.assertIsNone(p.get())
        self.assertFalse(p.status()["pending"])

    def test_default_seasons(self):
        self.assertEqual(default_seasons({"seasons": [{"seasonNumber": 0}, {"seasonNumber": 1}, {"seasonNumber": 2}]}), [1, 2])
        self.assertEqual(default_seasons({"seasons": [{"seasonNumber": n} for n in range(6)]}), [1])
        self.assertEqual(default_seasons({}), [1])


class SeerrToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_propose_sets_pending_and_ask(self):
        tools = seerr_tools(tempfile.mkdtemp(), seasons=5)
        out = json.loads((await tools.run("propose_download", {"tmdb_id": 42, "media_type": "tv"}))[0])
        self.assertTrue(out["ok"])
        self.assertEqual(out["seasons"], [1])
        self.assertTrue(tools.task_ctx["ask"])
        self.assertEqual(tools.pending.get()["satellite"], "assist_satellite.tablet")

    async def test_available_or_processing_is_not_proposed(self):
        tools = seerr_tools(tempfile.mkdtemp(), {5: 5, 6: 3})
        out = json.loads((await tools.run("propose_download", {"tmdb_id": 5, "media_type": "movie"}))[0])
        self.assertEqual((out["ok"], out["status"]), (False, "available"))
        out = json.loads((await tools.run("request_download", {"tmdb_id": 6, "media_type": "movie"}))[0])
        self.assertEqual((out["ok"], out["status"]), (False, "processing"))
        self.assertIsNone(tools.pending.get())
        self.assertEqual(tools.seerr.posts, [])

    async def test_request_is_tracked(self):
        tmp = tempfile.mkdtemp()
        tools = seerr_tools(tmp)
        out = json.loads((await tools.run("request_download", {"tmdb_id": 693134, "media_type": "movie"}))[0])
        self.assertTrue(out["ok"])
        self.assertEqual(tools.seerr.posts, [{"mediaType": "movie", "mediaId": 693134}])
        with open(os.path.join(tmp, "requests.json")) as f:
            saved = json.load(f)
        self.assertEqual((saved[0]["tmdb_id"], saved[0]["satellite"]), (693134, "assist_satellite.tablet"))

    async def test_dry_run_logs_post_body(self):
        class Session:
            def request(self, *a, **k):
                raise AssertionError("dry run must not send")
        s = Seerr("http://seerr", "key", Session(), user_id=2, dry_run=True)
        with self.assertLogs("voice_claude.seerr", "INFO") as logs:
            await s.request("tv", 1399, [1, 2])
        self.assertEqual(s.posts, [{"mediaType": "tv", "mediaId": 1399, "seasons": [1, 2], "userId": 2}])
        self.assertIn('"userId": 2', logs.output[0])


class TrackerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.mkdtemp()
        self.said = []
        self.clock = [datetime(2026, 11, 26, 14, 0, tzinfo=TZ)]
        self.seerr = FakeSeerr({1: 3})

        async def notify(item, msg):
            self.said.append((item["satellite"], msg))
        self.notify = notify

    def tracker(self):
        return Tracker(os.path.join(self.tmp, "requests.json"), self.seerr, self.notify, now=lambda: self.clock[0])

    async def test_announces_when_available_and_survives_restart(self):
        t = self.tracker()
        t.add(1, "movie", "Dűne: Második rész", "assist_satellite.tablet")
        self.assertEqual(await t.poll(), [])
        self.seerr.statuses[1] = 5
        t = self.tracker()  # restart: loaded from requests.json
        self.assertEqual(await t.poll(), ["Dűne: Második rész"])
        self.assertEqual(self.said, [("assist_satellite.tablet", "Letöltődött a(z) Dűne: Második rész, indíthatom a tévén?")])
        self.assertEqual(await t.poll(), [])  # only once

    async def test_quiet_hours_wait_until_eight(self):
        t = self.tracker()
        t.add(1, "movie", "X", "assist_satellite.tablet")
        self.seerr.statuses[1] = 5
        self.clock[0] = datetime(2026, 11, 26, 23, 10, tzinfo=TZ)
        self.assertEqual(await t.poll(), [])
        self.clock[0] = datetime(2026, 11, 27, 7, 55, tzinfo=TZ)
        self.assertEqual(await t.poll(), [])
        self.clock[0] = datetime(2026, 11, 27, 8, 0, tzinfo=TZ)
        self.assertEqual(await t.poll(), ["X"])

    async def test_series_waits_for_requested_seasons(self):
        t = self.tracker()
        t.add(2, "tv", "Sorozat", "s", seasons=[1, 2])
        self.seerr.statuses[2] = 4
        orig = self.seerr.details

        async def details(media_type, tmdb_id):
            d = await orig(media_type, tmdb_id)
            d["mediaInfo"]["seasons"] = [{"seasonNumber": 1, "status": 5}, {"seasonNumber": 2, "status": done[0]}]
            return d
        done = [3]
        self.seerr.details = details
        self.assertEqual(await t.poll(), [])
        done[0] = 5
        self.assertEqual(await t.poll(), ["Sorozat"])


# ---------------------------------------------------------------- the service: /pending and replies
class PendingServiceTests(unittest.IsolatedAsyncioTestCase):
    async def client_for(self, script):
        self.tmp = tempfile.mkdtemp()
        cfg = make_cfg(self.tmp)
        tools = seerr_tools(self.tmp)
        tools.players = FakePlayers()
        self.tools = tools
        self.speaker = DryRunSpeaker()
        ledger = Ledger(os.path.join(self.tmp, "l.jsonl"), Pricing(PRICING), 30)
        self.client = FakeClient(script)
        runner = Runner(cfg, self.client, tools, self.speaker, ledger, FakeCatalogue())
        self.service = Service(cfg, lambda: runner, tools, ledger, FakeCatalogue(), lambda: True)
        self.service.speaker = self.speaker
        c = TestClient(TestServer(self.service.app()))
        await c.start_server()
        self.addAsyncCleanup(c.close)
        return c

    async def test_propose_then_yes(self):
        c = await self.client_for([
            response([tool("propose_download", {"tmdb_id": 329865, "media_type": "movie"})], "tool_use"),
            response([text("Az Érkezés, 2016, okos sci-fi. Letöltsem?")], "end_turn")])
        self.assertEqual((await (await c.get("/pending")).json())["pending"], False)
        await c.post("/task", json={"text": "ajánlj egy sci-fi filmet", "satellite": "assist_satellite.kitchen"})
        await self.service.current[1]
        self.assertEqual(self.speaker.asked, ["Az Érkezés, 2016, okos sci-fi. Letöltsem?"])
        t = time.monotonic()
        p = await (await c.get("/pending")).json()
        self.assertLess(time.monotonic() - t, 0.05)
        self.assertEqual((p["pending"], p["kind"], p["satellite"]), (True, "seerr", "assist_satellite.kitchen"))
        self.assertEqual(p["title"], "Title 329865")
        self.assertGreater(p["expires_in"], 170)
        r = await (await c.post("/task", json={"text": "igen, mehet", "satellite": "assist_satellite.kitchen"})).json()
        self.assertEqual(r, {"accepted": True, "ack": "Rendben, kértem a(z) Title 329865 letöltését.", "task_id": None,
                             "pending_answer": "yes"})
        self.assertEqual(self.tools.seerr.posts, [{"mediaType": "movie", "mediaId": 329865}])
        self.assertFalse((await (await c.get("/pending")).json())["pending"])
        self.assertEqual(len(self.client.calls), 2)  # no Claude call for the answer

    async def test_no_and_another(self):
        c = await self.client_for([
            response([tool("propose_download", {"tmdb_id": 1, "media_type": "movie"})], "tool_use"),
            response([text("Title 1, 2024. Letöltsem?")], "end_turn"),
            response([tool("propose_download", {"tmdb_id": 2, "media_type": "movie"})], "tool_use"),
            response([text("Title 2, 2024, más hangulat.")], "end_turn")])
        await c.post("/task", json={"text": "ajánlj filmet"})
        await self.service.current[1]
        await c.post("/task", json={"text": "inkább mást"})
        await self.service.current[1]
        user_turn = self.client.calls[2]["messages"][0]["content"]
        self.assertIn("rejected it and wants something else", user_turn)
        self.assertIn("already offered: Title 1", user_turn)
        # the question mark was missing: the worker adds it
        self.assertEqual(self.speaker.asked[-1], "Title 2, 2024, más hangulat. Letöltsem?")
        r = await (await c.post("/task", json={"text": "nem"})).json()
        self.assertEqual((r["ack"], r["pending_answer"]), ("Rendben, nem töltöm le.", "no"))
        self.assertEqual(self.tools.seerr.posts, [])

    async def test_expired_pending_is_ignored(self):
        c = await self.client_for([response([text("Kész.")], "end_turn")])
        self.tools.pending.set(kind="seerr", tmdb_id=1, type="movie", title="X", satellite=None)
        self.tools.pending.item["expires"] = time.monotonic() - 1
        r = await (await c.post("/task", json={"text": "igen"})).json()
        self.assertIsNotNone(r["task_id"])  # went to Claude as a normal request
        await self.service.current[1]
        self.assertEqual(self.tools.seerr.posts, [])


if __name__ == "__main__":
    unittest.main()

