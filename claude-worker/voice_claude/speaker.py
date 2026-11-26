"""Speaking through Home Assistant satellites, with the status-update rate limit."""
import asyncio
import logging
import time

_LOGGER = logging.getLogger(__name__)


class Speaker:
    """Serialises announcements so a status line and the final answer never overlap."""

    def __init__(self, ha):
        self.ha = ha
        self._lock = asyncio.Lock()

    async def say(self, satellite, text):
        async with self._lock:
            _LOGGER.info("announce %s: %s", satellite, text)
            try:
                await self.ha.announce(satellite, text)
            except Exception as err:
                _LOGGER.warning("announce failed on %s: %r", satellite, err)

    async def ask(self, satellite, text):
        """Speak a question and let the satellite listen for the answer (no wake word); announce if that fails."""
        async with self._lock:
            _LOGGER.info("ask %s: %s", satellite, text)
            try:
                await self.ha.start_conversation(satellite, text)
                return True
            except Exception as err:
                _LOGGER.warning("start_conversation failed on %s: %r; announcing instead", satellite, err)
            try:
                await self.ha.announce(satellite, text)
            except Exception as err:
                _LOGGER.warning("announce failed on %s: %r", satellite, err)
            return False


class DryRunSpeaker:
    def __init__(self):
        self.spoken = []
        self.asked = []
        self._lock = asyncio.Lock()

    async def say(self, satellite, text):
        async with self._lock:
            self.spoken.append((time.monotonic(), satellite, text))
            _LOGGER.info("[dry-run] would announce on %s: %s", satellite, text)

    async def ask(self, satellite, text):
        async with self._lock:
            self.spoken.append((time.monotonic(), satellite, text))
            self.asked.append(text)
            _LOGGER.info("[dry-run] would start_conversation on %s: %s", satellite, text)
        return True


class StatusGate:
    """Decides whether a status update may be spoken now.

    Nothing in the first quiet_after_ack_s after the ack, at least min_gap_s between two, at most
    max_per_task per task.
    """

    def __init__(self, min_gap_s=6, quiet_after_ack_s=4, max_per_task=4, clock=time.monotonic, start=None):
        self.min_gap = min_gap_s
        self.quiet = quiet_after_ack_s
        self.max = max_per_task
        self.clock = clock
        self.ack_at = clock() if start is None else start
        self.last_at = None
        self.count = 0

    def check(self):
        now = self.clock()
        if self.count >= self.max:
            return "limit"
        if now - self.ack_at < self.quiet:
            return "too_early"
        if self.last_at is not None and now - self.last_at < self.min_gap:
            return "too_soon"
        return None

    def mark(self):
        self.last_at = self.clock()
        self.count += 1

    def since_last(self):
        return self.clock() - (self.last_at if self.last_at is not None else self.ack_at)
