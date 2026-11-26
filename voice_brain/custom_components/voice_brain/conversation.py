"""Conversation agent: text -> JSON command from the language model -> Home Assistant action.

Quick device control (lights, TV on/off, transport, volume) and like / save / cancel stay local and fast.
Everything else (music requests, questions, unclear films) is handed to the Claude worker with the original text;
the worker answers on the satellite itself. If the worker is down, music and films fall back to the local way.

router.py runs first: anything naming Claude (or "Cloud", "Klód"...) and playlist requests go straight to the
worker, and like / save / cancel only happen on explicit phrases, never on the model's guess alone. A short or
yes/no-like utterance first asks the worker whether it waits for an answer ("Letöltsem a Dűnét?"); if so, the
text goes to the worker as that answer.

Local actions are never reported on faith: the service call is awaited and the state polled until it shows the
change (control.py). Transport commands act on what is actually playing (any Music Assistant player, a Jellyfin
film or other playback on the TV), and the reply says what was verified, or that nothing was playing, or that it
didn't work."""
import asyncio
import json
import logging
import time
from datetime import timedelta

from custom_components import jellyfin_panel
from custom_components.jellyfin_panel import DEVICES as WATCH_DEVICES
from custom_components.jellyfin_panel import async_start_title
from homeassistant.components import conversation
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import ulid

from . import control, prompt, router, titles, worker

_LOGGER = logging.getLogger(__name__)
DOMAIN = "voice_brain"
LLM_URL = "http://192.168.1.142:8081/v1/chat/completions"
LLM_TIMEOUT = 3
WARM_UP_TIMEOUT = 20  # an uncached system prompt takes several seconds to process
TV = "media_player.philips_uhd_android_tv"
TV_REMOTE = "remote.philips_uhd_android_tv"
TV_ADB = "media_player.android_tv_192_168_1_188"  # its polling is off: refresh it before reading
ALL_OFF = "script.minden_le"
ALL_LIGHTS = ["switch.led_light", "switch.halo_led", "light.digiamp_player_ambient_light", "light.digiamp_player_vu_meter"]
DEVICE_ENTITIES = {
    "LED light": "switch.led_light",
    "Decor light": "switch.halo_led",
    "Ambient light": "light.digiamp_player_ambient_light",
    "VU meter": "light.digiamp_player_vu_meter",
    "Amp": "switch.living_room_amplifier",
    "TV": TV,
    "everything": None,
}
LIGHTS = ("LED light", "Decor light", "Ambient light", "VU meter")
SPEAKERS = {
    "Pi": "media_player.raspberrypi",
    "DigiAMP": "media_player.digiamp_player",
    "Both": "media_player.nappali",
    "Work PC": "media_player.work_pc",
}
DEFAULT_SPEAKER = "Pi"
# The speakers a satellite is next to, in order of preference, when several things play at once. Both kiosks
# and the Mac are in the living room with the "nappali" group (Pi + DigiAMP).
HOME_SPEAKERS = ("media_player.nappali", "media_player.raspberrypi", "media_player.digiamp_player")
SATELLITE_SPEAKERS = {}
HANDOFF = ("music", "music_only", "none")  # actions the worker handles; "movie" too unless the title is certain
TRANSPORT = control.TRANSPORT
CONFIDENT_TITLE = 0.9  # titles.best similarity needed to start a film locally without asking Claude
ACTION_BUDGET = 2.0  # seconds from the service call to a verified (or failed) reply; parsing adds ~0.3-0.5 s
FIRST_TRY = 1.3  # when there is a second target to try, the first one gets this long
POLL = 0.1
JELLYFIN_TIMEOUT = 1.0
ADB_TIMEOUT = 1.0
TV_KEYS = {"pause": "MEDIA_PAUSE", "resume": "MEDIA_PLAY", "stop": "MEDIA_STOP", "next": "MEDIA_NEXT"}
MEDIA_SERVICES = {"pause": "media_pause", "resume": "media_play", "next": "media_next_track", "stop": "media_stop"}
# Replies by language; English is the fallback
REPLIES = {
    "en": {
        "dim": "{0} can't be dimmed.", "level": "{0} at {1} percent.", "level_failed": "Couldn't dim {0}.",
        "what": "What should I play?", "playing": "Playing {0}.", "starting": "Starting {0}.", "missing": "I can't find {0}.",
        "all_on": "All lights on.", "all_off": "All lights off.", "all_failed": "These didn't switch: {0}.",
        "switched_on": "{0} on.", "switched_off": "{0} off.", "already_on": "{0} was already on.",
        "already_off": "{0} was already off.", "switch_failed": "Couldn't switch {0} {1}.",
        "tv_slow": "Turning the TV on, it hasn't answered yet.",
        "music_only": "That only works for music.", "down": "The voice model isn't responding.",
        "claude_down": "Claude isn't available right now.", "cancelled": "Stopped Claude.",
        "liked": "Added to favourites.", "saved": "Added to {0}.", "which_list": "Which playlist?",
        "handed": "Asking Claude.",
    },
    "hu": {
        "dim": "{0} nem szabályozható.", "level": "{0} fényereje {1} százalék.", "level_failed": "Nem sikerült állítani: {0}.",
        "what": "Mit játsszak?", "playing": "Lejátszom: {0}.", "starting": "Indítom: {0}.", "missing": "Nem találom: {0}.",
        "all_on": "Felkapcsoltam a lámpákat.", "all_off": "Lekapcsoltam a lámpákat.", "all_failed": "Nem kapcsolt: {0}.",
        "switched_on": "{1} {0}.", "switched_off": "{1} {0}.", "already_on": "{0} már be volt kapcsolva.",
        "already_off": "{0} már ki volt kapcsolva.", "switch_failed": "Nem sikerült {1} {0}.",
        "tv_slow": "Kapcsolom a tévét, de még nem jelzett vissza.",
        "music_only": "Ez csak zenénél működik.", "down": "A hangmodell nem válaszol.",
        "claude_down": "Claude most nem elérhető.", "cancelled": "Leállítottam Claude-ot.",
        "liked": "Hozzáadtam a kedvencekhez.", "saved": "Hozzáadtam: {0}.", "which_list": "Melyik listába?",
        "handed": "Szólok Claude-nak.",
    },
}
TITLE_REFRESH = timedelta(hours=6)
NAMES = {"hu": {"LED light": "LED lámpa", "Decor light": "Dekor lámpa", "Ambient light": "Hangulatvilágítás",
                "VU meter": "VU-mérő", "Amp": "Erősítő"}}
# Hungarian device names as the subject (with article, sentence start) and as the object
SUBJECTS = {"hu": {"LED light": "A LED lámpa", "Decor light": "A dekor lámpa", "Ambient light": "A hangulatvilágítás",
                   "VU meter": "A VU-mérő", "Amp": "Az erősítő", "TV": "A tévé"}}
OBJECTS = {"hu": {"LED light": "a LED lámpát", "Decor light": "a dekor lámpát", "Ambient light": "a hangulatvilágítást",
                  "VU meter": "a VU-mérőt", "Amp": "az erősítőt", "TV": "a tévét"}}
# (done, infinitive) per kind of device: lamps go "fel / le", the rest "be / ki"
VERBS = {"hu": {("light", "on"): ("Felkapcsoltam", "felkapcsolni"), ("light", "off"): ("Lekapcsoltam", "lekapcsolni"),
                ("device", "on"): ("Bekapcsoltam", "bekapcsolni"), ("device", "off"): ("Kikapcsoltam", "kikapcsolni")}}
SYSTEM = prompt.system(DEVICE_ENTITIES, SPEAKERS)
SCHEMA = prompt.schema(DEVICE_ENTITIES, SPEAKERS)


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([VoiceBrainAgent(entry)])


class VoiceBrainAgent(conversation.ConversationEntity, conversation.AbstractConversationAgent):
    _attr_has_entity_name = True
    _attr_name = "Voice Brain"
    _attr_supported_features = conversation.ConversationEntityFeature.CONTROL

    def __init__(self, entry):
        self.entry = entry
        self._attr_unique_id = entry.entry_id

    @property
    def supported_languages(self):
        return "*"

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self.entry, self)
        # Caches the system prompt, so the first real command is as fast as the rest
        self.entry.async_create_background_task(self.hass, self._warm_up(), "voice_brain_warm_up")
        self.titles = await self.hass.async_add_executor_job(titles.load, self.hass.config.path(titles.CACHE))
        self.entry.async_create_background_task(self.hass, titles.async_refresh(self.hass, self.titles), "voice_brain_titles")
        self.async_on_remove(async_track_time_interval(self.hass, self._refresh_titles, TITLE_REFRESH))

    async def async_will_remove_from_hass(self):
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()

    async def _warm_up(self):
        try:
            await self._parse("hello", WARM_UP_TIMEOUT)
        except (TimeoutError, OSError, KeyError, ValueError) as err:
            _LOGGER.warning("Warm-up failed: %r", err)

    async def _parse(self, text, timeout=LLM_TIMEOUT):
        body = {
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}],
            "temperature": 0,
            "max_tokens": 40,
            "cache_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {"schema": SCHEMA}},
        }
        session = async_get_clientsession(self.hass)
        async with session.post(LLM_URL, json=body, timeout=timeout) as resp:
            data = await resp.json()
        return json.loads(data["choices"][0]["message"]["content"])

    # ------------------------------------------------------------------------------------ calling and checking
    def _call(self, domain, service, data):
        """Fire and forget: only for starting music when Claude is down (nothing quick to verify)."""
        self.hass.async_create_task(self.hass.services.async_call(domain, service, data, blocking=False))

    @staticmethod
    def _left(deadline):
        return deadline - asyncio.get_running_loop().time()

    async def _call_and_wait(self, domain, service, data, check, deadline):
        """Await the service call (up to the deadline), then poll until check() is true. True if verified.

        The call runs as its own task, so a slow device isn't cancelled when the deadline passes."""
        call = self.hass.async_create_task(self.hass.services.async_call(domain, service, data, blocking=True))
        call.add_done_callback(lambda t: t.cancelled() or t.exception())  # a late failure is logged by HA, not here
        done, _ = await asyncio.wait({call}, timeout=max(0.05, self._left(deadline)))
        if call in done and call.exception():
            _LOGGER.warning("%s.%s %s failed: %r", domain, service, data, call.exception())
            return False
        return await self._wait(check, deadline)

    async def _wait(self, check, deadline):
        while True:
            if check():
                return True
            if self._left(deadline) <= 0:
                return False
            await asyncio.sleep(min(POLL, max(0.01, self._left(deadline))))

    def _player_now(self, entity, kind="music"):
        state = self.hass.states.get(entity)
        if state is None:
            return control.Player(entity, kind, "unavailable")
        return control.player(entity, state.state, state.attributes, kind)

    async def _refresh(self, entity, timeout=ADB_TIMEOUT):
        """Make a polled entity (the TV's ADB one) read its device now. False if that didn't finish in time."""
        call = self.hass.async_create_task(self.hass.services.async_call(
            "homeassistant", "update_entity", {"entity_id": entity}, blocking=True))
        call.add_done_callback(lambda t: t.cancelled() or t.exception())
        done, _ = await asyncio.wait({call}, timeout=timeout)
        return call in done and not call.exception()

    # ------------------------------------------------------------------------------------ what is playing
    async def _film(self):
        """The Jellyfin film on the TV as a Player (state playing / paused), or None."""
        try:
            async with asyncio.timeout(JELLYFIN_TIMEOUT):
                session = await jellyfin_panel._session(self.hass, WATCH_DEVICES["tv"])
        except Exception as err:  # Jellyfin down or slow: treat as no film
            _LOGGER.debug("Jellyfin session unavailable: %r", err)
            return None
        if not session or not session.get("NowPlayingItem"):
            return None
        item = session["NowPlayingItem"]
        paused = (session.get("PlayState") or {}).get("IsPaused")
        return control.Player("jellyfin", "film", "paused" if paused else "playing", title=item.get("Name"),
                              content_id=item.get("Id"), ref=session.get("Id", ""))

    async def _players(self, action):
        """Everything that could be playing: every Music Assistant player, a Jellyfin film on the TV and, when
        neither plays, whatever an app on the TV plays (read over ADB)."""
        registry = er.async_get(self.hass)
        players = []
        for entry in list(registry.entities.values()):
            if entry.domain == "media_player" and entry.platform == "music_assistant" and not entry.disabled_by:
                if (state := self.hass.states.get(entry.entity_id)) is not None:
                    players.append(control.player(entry.entity_id, state.state, state.attributes))
        tv = self.hass.states.get(TV)
        if tv is None or tv.state in ("off", "unavailable", "unknown", "standby"):
            return players
        if film := await self._film():
            players.append(film)
        wanted = control.WANTED[action]
        if not any(p.state in wanted for p in players) and await self._refresh(TV_ADB):
            app = self._player_now(TV_ADB, "tv")
            if app.state in ("playing", "paused"):
                players.append(app)
        return players

    def _preferred(self, satellite):
        return SATELLITE_SPEAKERS.get(satellite, HOME_SPEAKERS)

    # ------------------------------------------------------------------------------------ doing it
    async def _execute(self, action, target, deadline, n=0, absolute=False):
        """Run a transport command on one target and wait for its state to show it: (outcome, after)."""
        if target.kind == "film" and action in MEDIA_SERVICES:
            return await self._film_command(action, target, deadline)
        if target.kind in ("film", "tv") and action.startswith("volume"):
            target = self._player_now(TV, "tv")
        if target.kind == "tv" and action in TV_KEYS:
            return await self._tv_command(action, target, deadline)
        entity = target.entity
        before = self._player_now(entity, target.kind)
        data = {"entity_id": entity}
        if action.startswith("volume"):
            level = control.volume_target(before.volume, action, n, absolute)
            state = self.hass.states.get(entity)
            if level is not None and state is not None and state.attributes.get("supported_features", 0) & 4:
                service, data["volume_level"] = "volume_set", level
            else:
                service, level = action, None
            check = control.expect(action, before, level)
        else:
            service, check = MEDIA_SERVICES[action], control.expect(action, before)
        ok = await self._call_and_wait("media_player", service, data, lambda: check(self._player_now(entity, target.kind)),
                                       deadline)
        return ("ok" if ok else "failed"), self._player_now(entity, target.kind)

    async def _film_command(self, action, target, deadline):
        command = {"pause": "Pause", "resume": "Unpause", "stop": "Stop"}.get(action)
        if not command or not target.ref:
            return "failed", None
        try:
            async with asyncio.timeout(max(0.1, self._left(deadline))):
                await jellyfin_panel._jellyfin(self.hass, "POST", f"/Sessions/{target.ref}/Playing/{command}")
        except Exception as err:  # reported as not done
            _LOGGER.warning("Jellyfin %s failed: %r", command, err)
            return "failed", None
        check = control.expect(action, target)
        while True:
            after = await self._film() or control.Player("jellyfin", "film", "idle")
            if check(after):
                return "ok", after
            if self._left(deadline) <= 0.3:
                return "failed", after
            await asyncio.sleep(0.3)

    async def _tv_command(self, action, target, deadline):
        """Another app on the TV: send the media key, then read the state over ADB (slow, so it may stay unknown)."""
        check = control.expect(action, target)
        sent = await self._call_and_wait("remote", "send_command", {"entity_id": TV_REMOTE, "command": TV_KEYS[action]},
                                         lambda: True, deadline)
        if not sent:
            return "failed", None
        await asyncio.sleep(0.4)
        if not await self._refresh(TV_ADB, max(0.2, self._left(deadline))):
            return "unverified", None
        after = self._player_now(TV_ADB, "tv")
        return ("ok" if check(after) else "unverified"), after

    async def _execute_or_retry(self, action, target, players, deadline, n, absolute):
        """The command on the target; if it doesn't take, once more on its group / member."""
        other = control.alternative(target, players)
        first = min(deadline, asyncio.get_running_loop().time() + FIRST_TRY) if other else deadline
        outcome, after = await self._execute(action, target, first, n, absolute)
        if outcome == "failed" and other and self._left(deadline) > 0.3:
            _LOGGER.info("%s on %s not confirmed, trying %s", action, target.entity, other.entity)
            outcome2, after2 = await self._execute(action, other, deadline, n, absolute)
            if outcome2 == "ok":
                return other, outcome2, after2
        return target, outcome, after

    async def _transport(self, cmd, say, user_input, language):
        action, device, n = cmd["a"], cmd["d"], cmd["n"]
        named = SPEAKERS.get(device) or ("TV" if device == "TV" else None)
        players = await self._players(action)
        status, targets = control.resolve(action, players, named, self._preferred(self._satellite(user_input)))
        cmd["targets"] = [t.entity for t in targets]
        if status == "nothing" and action in ("pause", "stop", "next"):
            return control.NOTHING.get(language, control.NOTHING["en"]), "local-nothing"
        if status == "idle":
            where = control.where(targets[0], language)
            text = control.IDLE.get(language, control.IDLE["en"]).format(where=where)
            return text[:1].upper() + text[1:], "local-nothing"
        if status != "ok":
            # Nothing paused to resume, no player for the volume, or several candidates: Claude decides
            return await self._hand_off_speech(user_input, language, say), f"claude-{status}"
        if action == "next" and all(t.kind != "music" for t in targets):
            return say("music_only"), "local"
        deadline = asyncio.get_running_loop().time() + ACTION_BUDGET
        absolute = router.volume_absolute(user_input.text)
        results = await asyncio.gather(*(self._execute_or_retry(action, t, players, deadline, n, absolute)
                                         for t in targets))
        cmd["verified"] = [o for _, o, _ in results]
        return control.reply(action, results, language), "local"

    async def _stop(self, say, user_input, language):
        """"Állj" and friends: stop a running Claude task and whatever is playing, and say which of them happened.
        "Mégse" only cancels Claude."""
        cancel = asyncio.create_task(worker.cancel(self.hass))
        status, targets, players, results = "nothing", [], [], []
        if router.stops_playback(user_input.text):
            players = await self._players("stop")
            status, targets = control.resolve("stop", players, None, self._preferred(self._satellite(user_input)))
        if status == "ok":
            deadline = asyncio.get_running_loop().time() + ACTION_BUDGET
            results = await asyncio.gather(*(self._execute_or_retry("stop", t, players, deadline, 0, False)
                                             for t in targets))
        cancelled = await cancel
        parts = []
        if cancelled and cancelled.get("cancelled"):
            parts.append(say("cancelled"))
        if results:
            parts.append(control.reply("stop", results, language))
        return " ".join(parts) or control.NOTHING.get(language, control.NOTHING["en"])

    async def _switch(self, action, device, say, language):
        deadline = asyncio.get_running_loop().time() + ACTION_BUDGET
        if device == "everything":
            lights = [e for e in ALL_LIGHTS if (s := self.hass.states.get(e)) and s.state not in control.DEAD]
            def all_done():
                return all(control.switched(action, self.hass.states.get(e).state) for e in lights)
            if action == "off":
                ok = await self._call_and_wait("script", "turn_on", {"entity_id": ALL_OFF}, all_done, deadline)
            else:
                ok = await self._call_and_wait("homeassistant", "turn_on", {"entity_id": lights}, all_done, deadline)
            if ok:
                return say(f"all_{action}")
            names = {v: k for k, v in DEVICE_ENTITIES.items() if v}
            stuck = [names.get(e, e) for e in lights if not control.switched(action, self.hass.states.get(e).state)]
            return say("all_failed", ", ".join(NAMES.get(language, {}).get(d, d) for d in stuck))
        entity = DEVICE_ENTITIES[device]
        before = self.hass.states.get(entity)
        if before is not None and before.state not in control.DEAD and control.switched(action, before.state) \
                and device != "TV":
            return say(f"already_{action}", SUBJECTS.get(language, {}).get(device, device))
        def done():
            state = self.hass.states.get(entity)
            return state is not None and control.switched(action, state.state)
        if device == "TV":
            service = ("script", "turn_on", {"entity_id": "script.tv_wake"}) if action == "on" else \
                ("media_player", "turn_off", {"entity_id": TV})
        else:
            service = ("homeassistant", f"turn_{action}", {"entity_id": entity})
        if await self._call_and_wait(*service, done, deadline):
            return self._switched_text(language, action, device, True, say)
        if device == "TV" and action == "on":
            return say("tv_slow")
        return self._switched_text(language, action, device, False, say)

    @staticmethod
    def _switched_text(language, action, device, ok, say):
        kind = "light" if device in LIGHTS else "device"
        verbs = VERBS.get(language, {}).get((kind, action))
        if verbs and language in OBJECTS:
            obj = OBJECTS[language].get(device, device)
            return say(f"switched_{action}", obj, verbs[0]) if ok else say("switch_failed", obj, verbs[1])
        return say(f"switched_{action}", device) if ok else say("switch_failed", device, action)

    async def _brightness(self, device, value, say, language):
        entity = DEVICE_ENTITIES.get(device)
        subject = SUBJECTS.get(language, {}).get(device, device)
        if not entity or not entity.startswith("light."):
            return say("dim", subject)
        value = max(1, min(100, value))
        def done():
            state = self.hass.states.get(entity)
            return state is not None and control.switched("on", state.state, state.attributes, value)
        deadline = asyncio.get_running_loop().time() + ACTION_BUDGET
        if await self._call_and_wait("light", "turn_on", {"entity_id": entity, "brightness_pct": value}, done, deadline):
            return say("level", subject, value)
        return say("level_failed", device)

    # ------------------------------------------------------------------------------------ the worker
    async def _refresh_titles(self, _now):
        await titles.async_refresh(self.hass, self.titles)

    def _active_speaker(self, named=""):
        if named in SPEAKERS:
            return SPEAKERS[named]
        for entity in SPEAKERS.values():
            state = self.hass.states.get(entity)
            if state and state.state == "playing":
                return entity
        return SPEAKERS[DEFAULT_SPEAKER]

    def _playing_speaker(self, named=""):
        """The named speaker, else the one playing, else None (the worker then picks)."""
        if named in SPEAKERS:
            return SPEAKERS[named]
        return next((e for e in SPEAKERS.values() if (s := self.hass.states.get(e)) and s.state == "playing"), None)

    def _satellite(self, user_input):
        """The assist_satellite entity the request came from. Assist pipelines started by a satellite pass its
        entity id as satellite_id; otherwise look up the satellite entity on the device."""
        if (sat := user_input.satellite_id) and sat.startswith("assist_satellite."):
            return sat
        if user_input.device_id:
            for entry in er.async_entries_for_device(er.async_get(self.hass), user_input.device_id):
                if entry.domain == "assist_satellite":
                    return entry.entity_id
        return None

    async def _hand_off(self, user_input, language):
        """(accepted, what to say): the worker's ack, or its reason for refusing ("" if unreachable)."""
        reply = await worker.task(self.hass, user_input.text, language, self._satellite(user_input),
                                  user_input.device_id)
        if reply and reply.get("accepted"):
            return True, reply.get("ack") or ""
        return False, (reply or {}).get("say") or ""

    async def _hand_off_speech(self, user_input, language, say):
        accepted, said = await self._hand_off(user_input, language)
        return (said or say("handed")) if accepted else (said or say("claude_down"))

    async def _quick(self, cmd, say):
        player = self._playing_speaker(cmd["d"])
        if cmd["a"] == "like":
            reply = await worker.quick(self.hass, "like", player)
            fallback = say("liked")
        else:
            playlist = cmd["q"].strip()
            if not playlist:
                return say("which_list")
            reply = await worker.quick(self.hass, "save_to_playlist", player, playlist)
            fallback = say("saved", playlist)
        if reply is None:
            return say("claude_down")
        return reply.get("say") or (fallback if reply.get("ok") else say("claude_down"))

    async def _act(self, cmd, say):
        """Music and films the local way (only when Claude can't take them)."""
        action, device, query = cmd["a"], cmd["d"], cmd["q"].strip()
        if action in ("music", "music_only"):
            if not query:
                return say("what")
            title, by, artist = query.rpartition(" by ")
            self._call("music_assistant", "play_media", {
                # Music Assistant's search understands "Artist - Title"
                "entity_id": self._active_speaker(device),
                "media_id": f"{artist} - {title}" if by else query,
                "enqueue": "replace",
                "radio_mode": action == "music",
            })
            return say("playing", query)
        if action == "movie":
            match = titles.resolve(query, self.titles) if query else None
            name = await async_start_title(self.hass, match or query, next(iter(WATCH_DEVICES)))
            return say("starting", name) if name else say("missing", query)
        return say("claude_down")

    async def _answer(self, user_input, language, say):
        """The worker asked a question and waits: this utterance is the answer. Its ack may be empty on purpose
        (it speaks next itself), then nothing is said here."""
        accepted, said = await self._hand_off(user_input, language)
        return said if accepted else (said or say("claude_down"))

    async def async_process(self, user_input):
        start = time.perf_counter()
        response = intent.IntentResponse(language=user_input.language)
        language = user_input.language.split("-")[0]
        replies, names = REPLIES.get(language, REPLIES["en"]), NAMES.get(language, {})
        def say(key, *args):
            return replies[key].format(*(names.get(arg, arg) for arg in args))

        speech = ""
        cmd = None
        route = "local"
        text = user_input.text
        try:
            pending = None
            if not router.has_claude(text) and router.is_answer_like(text):
                pending = await worker.pending(self.hass)
            if router.pending_for(pending, self._satellite(user_input)):
                cmd = {"a": "answer", "d": "", "q": "", "n": 0, "rule": f"pending {pending.get('kind')}"}
            elif pre := router.route(text):
                kind, arg = pre
                # "none" hands off to Claude; arg is the playlist name for save_to_playlist, else the rule's reason
                cmd = {"a": "none" if kind == "claude" else kind, "d": "", "q": arg if kind == "save_to_playlist" else "",
                       "n": 0, "rule": f"{kind} {arg}".strip()}
            else:
                try:
                    cmd = await self._parse(text)
                    checked = router.check_model(text, cmd["a"])
                    if checked != cmd["a"]:
                        # The model said like / save / cancel but the transcript doesn't back it: let Claude decide
                        cmd = {**cmd, "a": "none", "q": "", "rule": f"model {cmd['a']} rejected"}
                except (TimeoutError, OSError, KeyError, ValueError) as err:
                    # The local model is down: Claude may still understand it
                    _LOGGER.warning("Parse failed on %r: %r", text, err)
                    accepted, said = await self._hand_off(user_input, language)
                    route = "claude" if accepted else "down"
                    speech = (said or say("handed")) if accepted else f"{say('down')} {said}".strip()
                    cmd = {"a": "?", "d": "", "q": "", "n": 0}
            # The model sometimes invents a speaker; only trust one that was actually said
            if cmd["d"] in SPEAKERS and cmd["d"].lower() not in text.lower():
                cmd["d"] = ""
            if cmd["a"] in ("stop", "pause") and router.is_bare_stop(text):
                # A bare "állj" is meant for whatever is going on: Claude's task and the playback
                cmd["a"] = "cancel"
            parsed = time.perf_counter()
            action = cmd["a"]
            unclear = (action in ("on", "off", "brightness") and cmd["d"] not in DEVICE_ENTITIES) or \
                (action == "movie" and not self._certain_title(cmd["q"]))
            if action == "?":
                pass
            elif action == "answer":
                route = "worker-answer"
                speech = await self._answer(user_input, language, say)
            elif action == "cancel":
                route = "local-stop"
                speech = await self._stop(say, user_input, language)
            elif action in ("like", "save_to_playlist"):
                route = "worker-quick"
                speech = await self._quick(cmd, say)
            elif action in HANDOFF or unclear:
                accepted, said = await self._hand_off(user_input, language)
                if accepted:
                    route = "claude"
                    speech = said or say("handed")
                elif action in ("music", "music_only", "movie") and cmd["q"].strip():
                    # Claude can't take it: do what we did before Claude, and say why it may be less clever
                    route = "claude-down-local"
                    speech = f"{said or say('claude_down')} {await self._act(cmd, say)}"
                else:
                    route = "claude-down"
                    speech = said or say("claude_down")
            elif action in ("on", "off"):
                speech = await self._switch(action, cmd["d"], say, language)
            elif action == "brightness":
                speech = await self._brightness(cmd["d"], cmd["n"], say, language)
            elif action in TRANSPORT:
                speech, route = await self._transport(cmd, say, user_input, language)
            else:
                speech = await self._hand_off_speech(user_input, language, say)
                route = "claude"
            _LOGGER.info("%.0f ms parse, %.0f ms total: %r -> %s via %s", (parsed - start) * 1000,
                         (time.perf_counter() - start) * 1000, text, cmd, route)
        except (TimeoutError, OSError, KeyError, ValueError) as err:
            _LOGGER.warning("Failed on %r (%s): %r", text, cmd, err)
            speech = say("down")
        response.async_set_speech(speech)
        return conversation.ConversationResult(
            response=response, conversation_id=user_input.conversation_id or ulid.ulid_now()
        )

    def _certain_title(self, query):
        if not query.strip():
            return False
        name, score = titles.best(query, self.titles)
        return name is not None and score >= CONFIDENT_TITLE
