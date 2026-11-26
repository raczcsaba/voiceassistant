"""Pricing, the per-call usage ledger and the monthly cap."""
import json
import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo


def _get(obj, name, default=0):
    if obj is None:
        return default
    if isinstance(obj, dict):
        value = obj.get(name, default)
    else:
        value = getattr(obj, name, default)
    return default if value is None else value


def usage_dict(usage):
    """Flatten an API usage object (SDK model or dict) into the fields we bill."""
    creation = _get(usage, "cache_creation", None)
    server = _get(usage, "server_tool_use", None)
    write_total = _get(usage, "cache_creation_input_tokens")
    write_1h = _get(creation, "ephemeral_1h_input_tokens")
    return {
        "input_tokens": _get(usage, "input_tokens"),
        "cache_write_5m_tokens": max(0, write_total - write_1h),
        "cache_write_1h_tokens": write_1h,
        "cache_read_tokens": _get(usage, "cache_read_input_tokens"),
        "output_tokens": _get(usage, "output_tokens"),
        "web_search_requests": _get(server, "web_search_requests"),
    }


class Pricing:
    def __init__(self, cfg):
        self.models = cfg["models"]
        self.web_search = cfg.get("web_search_per_1000", 10.0) / 1000.0

    def cost(self, model, usage):
        """Return {total, input, cache_write, cache_read, output, web_search} in USD."""
        p = self.models.get(model)
        if p is None:
            raise KeyError(f"no pricing configured for model {model}")
        u = usage if isinstance(usage, dict) and "cache_write_5m_tokens" in usage else usage_dict(usage)
        mtok = 1_000_000
        parts = {
            "input": u["input_tokens"] * p["input"] / mtok,
            "cache_write": (u["cache_write_5m_tokens"] * p["cache_write_5m"]
                            + u["cache_write_1h_tokens"] * p.get("cache_write_1h", p["cache_write_5m"] * 1.6)) / mtok,
            "cache_read": u["cache_read_tokens"] * p["cache_read"] / mtok,
            "output": u["output_tokens"] * p["output"] / mtok,
            "web_search": u["web_search_requests"] * self.web_search,
        }
        parts["total"] = sum(parts.values())
        return {k: round(v, 6) for k, v in parts.items()}


class Ledger:
    """Append-only JSONL of every API call; keeps a running total per calendar month."""

    def __init__(self, path, pricing, monthly_limit, tz="Europe/Budapest"):
        self.path = path
        self.pricing = pricing
        self.monthly_limit = monthly_limit
        self.tz = ZoneInfo(tz)
        self._lock = threading.Lock()
        self._totals = {}
        self._requests = {}
        self._size = 0
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._load()

    def _load(self):
        """(Re)read the file; also picks up calls other processes (the test scripts) appended."""
        self._totals, self._requests, self._size = {}, {}, 0
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    self._add(entry.get("month"), entry.get("cost", {}).get("total", 0.0), entry.get("kind"))
            self._size = os.path.getsize(self.path)

    def _sync(self):
        try:
            if os.path.getsize(self.path) != self._size:
                with self._lock:
                    self._load()
        except OSError:
            pass

    def _add(self, month, amount, kind):
        self._totals[month] = self._totals.get(month, 0.0) + amount
        if kind != "message_continuation":
            self._requests[month] = self._requests.get(month, 0) + 1

    def month(self, now=None):
        return (now or datetime.now(self.tz)).astimezone(self.tz).strftime("%Y-%m")

    def record(self, model, usage, task_id=None, kind="message"):
        u = usage_dict(usage) if not (isinstance(usage, dict) and "cache_write_5m_tokens" in usage) else usage
        cost = self.pricing.cost(model, u)
        now = datetime.now(self.tz)
        entry = {"ts": now.isoformat(timespec="seconds"), "month": self.month(now), "task": task_id,
                 "model": model, "kind": kind, "usage": u, "cost": cost}
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            self._add(entry["month"], cost["total"], kind)
            self._size = os.path.getsize(self.path)
        return cost

    def spent(self, month=None):
        self._sync()
        return round(self._totals.get(month or self.month(), 0.0), 6)

    def requests(self, month=None):
        self._sync()
        return self._requests.get(month or self.month(), 0)

    def over_limit(self):
        return self.spent() >= self.monthly_limit
