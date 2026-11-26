"""Conversation agent: text -> JSON command from the language model -> Home Assistant action.

Quick device control (lights, TV on/off, transport, volume) and like / save / cancel stay local and fast.
Everything else (music requests, questions, unclear films) is handed to the Claude worker with the original text;
the worker answers on the satellite itself. If the worker is down, music and films fall back to the local way."""
import json
import logging
import time
from datetime import timedelta

from custom_components.jellyfin_panel import DEVICES as WATCH_DEVICES
from custom_components.jellyfin_panel import async_control, async_now_playing, async_start_title
from homeassistant.components import conversation
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import ulid

from . import prompt, titles, worker

_LOGGER = logging.getLogger(__name__)
DOMAIN = "voice_brain"
LLM_URL = "http://192.168.1.142:8081/v1/chat/completions"
LLM_TIMEOUT = 3
WARM_UP_TIMEOUT = 20  # an uncached system prompt takes several seconds to process
TV = "media_player.philips_uhd_android_tv"
TV_REMOTE = "remote.philips_uhd_android_tv"
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
SPEAKERS = {
    "Pi": "media_player.raspberrypi",
    "DigiAMP": "media_player.digiamp_player",
    "Both": "media_player.nappali",
    "Work PC": "media_player.work_pc",
}
DEFAULT_SPEAKER = "Pi"
HANDOFF = ("music", "music_only", "none")  # actions the worker handles; "movie" too unless the title is certain
CONFIDENT_TITLE = 0.9  # titles.best similarity needed to start a film locally without asking Claude
# Replies by language; English is the fallback
REPLIES = {
    "en": {
        "unknown": "I don't know which device you mean.", "dim": "{0} can't be dimmed.", "level": "{0} {1} percent.",
        "what": "What should I play?", "playing": "Playing {0}.", "starting": "Starting {0}.", "missing": "I can't find {0}.",
        "all_on": "All lights on.", "all_off": "All lights off.", "dev_on": "{0} on.", "dev_off": "{0} off.",
        "louder": "Louder.", "quieter": "Quieter.", "music_only": "That only works for music.", "ok": "Okay.",
        "none": "Sorry, I didn't catch a command.", "down": "The voice model isn't responding.",
        "claude_down": "Claude isn't available right now.", "cancelled": "Okay, I stopped it.",
        "liked": "Added to favourites.", "saved": "Added to {0}.", "which_list": "Which playlist?",
        "handed": "Asking Claude.",
    },
    "hu": {
        "unknown": "Nem tudom, melyik eszközre gondolsz.", "dim": "A(z) {0} nem szabályozható.", "level": "{0} {1} százalék.",
        "what": "Mit játsszak?", "playing": "Lejátszom: {0}.", "starting": "Indítom: {0}.", "missing": "Nem találom: {0}.",
        "all_on": "Minden lámpa bekapcsolva.", "all_off": "Minden lámpa lekapcsolva.", "dev_on": "{0} bekapcsolva.", "dev_off": "{0} kikapcsolva.",
        "louder": "Hangosabban.", "quieter": "Halkabban.", "music_only": "Ez csak zenénél működik.", "ok": "Rendben.",
        "none": "Bocsi, ezt nem értettem.", "down": "A hangmodell nem válaszol.",
        "claude_down": "Claude most nem elérhető.", "cancelled": "Rendben, leállítottam.",
        "liked": "Hozzáadtam a kedvencekhez.", "saved": "Hozzáadtam: {0}.", "which_list": "Melyik listába?",
        "handed": "Szólok Claude-nak.",
    },
}
TITLE_REFRESH = timedelta(hours=6)
NAMES = {"hu": {"LED light": "LED lámpa", "Decor light": "Dekor lámpa", "Ambient light": "Hangulatvilágítás",
                "VU meter": "VU-mérő", "Amp": "Erősítő"}}
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

    def _call(self, domain, service, data):
        # Not awaited: the reply must not wait for a slow device
        self.hass.async_create_task(self.hass.services.async_call(domain, service, data, blocking=False))

    def _active_speaker(self, named=""):
        if named in SPEAKERS:
            return SPEAKERS[named]
        for entity in SPEAKERS.values():
            state = self.hass.states.get(entity)
            if state and state.state == "playing":
                return entity
        return SPEAKERS[DEFAULT_SPEAKER]

    async def _refresh_titles(self, _now):
        await titles.async_refresh(self.hass, self.titles)

    def _music_playing(self):
        return any((s := self.hass.states.get(e)) and s.state == "playing" for e in SPEAKERS.values())

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

    async def _quick(self, cmd, say):
        player = self._playing_speaker(cmd["d"])
        if cmd["a"] == "cancel":
            done = await worker.cancel(self.hass)
            return say("cancelled") if done is not None else say("claude_down")
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
        action, device, query, value = cmd["a"], cmd["d"], cmd["q"].strip(), cmd["n"]
        if action in ("on", "off"):
            return self._switch(action, device, say)
        if action == "brightness":
            entity = DEVICE_ENTITIES.get(device)
            if not entity or not entity.startswith("light."):
                return say("dim", device or "?")
            self._call("light", "turn_on", {"entity_id": entity, "brightness_pct": max(1, min(100, value))})
            return say("level", device, value)
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
        return await self._transport(action, device, say)

    def _switch(self, action, device, say):
        if device == "everything":
            if action == "off":
                self._call("script", "turn_on", {"entity_id": ALL_OFF})
            else:
                self._call("homeassistant", "turn_on", {"entity_id": ALL_LIGHTS})
            return say(f"all_{action}")
        if device == "TV":
            if action == "on":
                self._call("script", "turn_on", {"entity_id": "script.tv_wake"})
            else:
                self._call("media_player", "turn_off", {"entity_id": TV})
            return say(f"dev_{action}", "TV")
        entity = DEVICE_ENTITIES.get(device)
        if not entity:
            return say("unknown")
        self._call("homeassistant", f"turn_{action}", {"entity_id": entity})
        return say(f"dev_{action}", device)

    async def _transport(self, action, device, say):
        # Whatever is playing gets the command; a film only if no music is playing
        film = not self._music_playing() and device not in SPEAKERS and await async_now_playing(self.hass)
        if action in ("volume_up", "volume_down"):
            if film or device == "TV":
                self._call("remote", "send_command", {"entity_id": TV_REMOTE, "command": action.upper()})
            else:
                self._call("media_player", action, {"entity_id": self._active_speaker(device)})
            return say("louder" if action == "volume_up" else "quieter")
        if film:
            control = {"pause": "playpause", "resume": "playpause", "stop": "stop"}.get(action)
            if not control:
                return say("music_only")
            await async_control(self.hass, control)
            return say("ok")
        service = {"pause": "media_pause", "resume": "media_play", "next": "media_next_track", "stop": "media_stop"}[action]
        self._call("media_player", service, {"entity_id": self._active_speaker(device)})
        return say("ok")

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
        try:
            if prompt.is_cancel(user_input.text):
                cmd = {"a": "cancel", "d": "", "q": "", "n": 0}
            else:
                try:
                    cmd = await self._parse(user_input.text)
                except (TimeoutError, OSError, KeyError, ValueError) as err:
                    # The local model is down: Claude may still understand it
                    _LOGGER.warning("Parse failed on %r: %r", user_input.text, err)
                    accepted, said = await self._hand_off(user_input, language)
                    route = "claude" if accepted else "down"
                    speech = (said or say("handed")) if accepted else f"{say('down')} {said}".strip()
                    cmd = {"a": "?", "d": "", "q": "", "n": 0}
            # The model sometimes invents a speaker; only trust one that was actually said
            if cmd["d"] in SPEAKERS and cmd["d"].lower() not in user_input.text.lower():
                cmd["d"] = ""
            parsed = time.perf_counter()
            action = cmd["a"]
            if action == "?":
                pass
            elif action in ("like", "save_to_playlist", "cancel"):
                route = "worker-quick"
                speech = await self._quick(cmd, say)
            elif action in HANDOFF or (action == "movie" and not self._certain_title(cmd["q"])):
                accepted, said = await self._hand_off(user_input, language)
                if accepted:
                    route = "claude"
                    speech = said or say("handed")
                elif action == "none":
                    route = "claude-down"
                    speech = said or say("claude_down")
                else:
                    # Claude can't take it: do what we did before Claude, and say why it may be less clever
                    route = "claude-down-local"
                    speech = f"{said or say('claude_down')} {await self._act(cmd, say)}"
            else:
                speech = await self._act(cmd, say)
            _LOGGER.info("%.0f ms parse, %.0f ms total: %r -> %s via %s", (parsed - start) * 1000,
                         (time.perf_counter() - start) * 1000, user_input.text, cmd, route)
        except (TimeoutError, OSError, KeyError, ValueError) as err:
            _LOGGER.warning("Failed on %r (%s): %r", user_input.text, cmd, err)
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
