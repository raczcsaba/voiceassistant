"""Home control for Claude: read-only states and a fixed allowlist of Home Assistant actions from config.json.

config "home_control":
  "readable": {"group": ["entity_id", ...]}       entities ha_get_states may read, by group
  "actions": {"action_id": {                      the only writes Claude can make
      "description": "Hungarian/English: what it does and when to use it",
      "service": "domain.service",                or "post": "/api/path" (an HA endpoint, JSON body)
      "data": {...},                              fixed data (entity_id, variables...)
      "params": {"name": {"type": "string"|"integer"|"entities", "enum": [...], "min", "max", "required",
                          "description", "into": "variables"|"data" (default data), "as": "other_key",
                          "scale": 0.01}}}}
  "manual": ["house manual lines for the system prompt"]

Defence in depth: whatever the config says, actions and readable entities that touch the intruder alarm,
restarts, reloads, deletions or shell commands are dropped at load time. Every write goes through Tools._ha_write
(dry-run aware, logged).
"""
import logging
import re

_LOGGER = logging.getLogger(__name__)

# Nothing matching this may ever be read or written through the allowlist
DENY = re.compile(r"intruder|alarm|alert|restart|reboot|reload|delete|remove|purge|shell_command|"
                  r"hassio|backup|lockdown|remote_management|clear_cache|^homeassistant\.(?!turn_on$|turn_off$)",
                  re.IGNORECASE)
TYPES = ("string", "integer", "number", "entities", "boolean")
# Attributes worth showing Claude, by domain; everything else is trimmed
ATTRS = {
    "light": ("brightness",),
    "media_player": ("media_title", "media_artist", "media_series_title", "app_name", "source", "volume_level",
                     "is_volume_muted"),
    "weather": ("temperature", "apparent_temperature", "humidity", "wind_speed", "precipitation_unit",
                "temperature_unit", "wind_speed_unit", "cloud_coverage"),
    "sun": ("next_rising", "next_setting", "elevation"),
    "input_select": ("options",),
    "select": ("options",),
    "person": (),
}


def _strings(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)
    elif value is not None:
        yield str(value)


def denied(*values):
    return any(DENY.search(s) for s in _strings(list(values)))


class HomeConfigError(ValueError):
    pass


def load(cfg):
    """(readable {group: [ids]}, actions {id: spec}) with denied items removed and specs validated."""
    hc = cfg.get("home_control") or {}
    readable = {}
    for group, ids in (hc.get("readable") or {}).items():
        ok = [e for e in ids or [] if isinstance(e, str) and "." in e and not denied(e)]
        dropped = set(ids or []) - set(ok)
        if dropped:
            _LOGGER.warning("home_control: not readable (denied): %s", sorted(dropped))
        if ok:
            readable[str(group)] = ok
    actions = {}
    for action_id, spec in (hc.get("actions") or {}).items():
        try:
            actions[action_id] = _check(action_id, spec)
        except HomeConfigError as err:
            _LOGGER.warning("home_control: action %s dropped: %s", action_id, err)
    return readable, actions


def _check(action_id, spec):
    if not isinstance(spec, dict):
        raise HomeConfigError("not an object")
    enums = [p.get("enum") for p in (spec.get("params") or {}).values() if isinstance(p, dict)]
    if denied(action_id, spec.get("service"), spec.get("post"), spec.get("data"), enums):
        raise HomeConfigError("denied (alarm/restart/delete/...)")
    if bool(spec.get("service")) == bool(spec.get("post")):
        raise HomeConfigError("needs exactly one of service or post")
    if spec.get("service") and not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", spec["service"]):
        raise HomeConfigError("bad service name")
    if spec.get("post") and not str(spec["post"]).startswith("/api/"):
        raise HomeConfigError("post must be an /api/ path")
    if not spec.get("description"):
        raise HomeConfigError("description missing")
    for name, p in (spec.get("params") or {}).items():
        if p.get("type", "string") not in TYPES:
            raise HomeConfigError(f"param {name}: bad type")
        if p.get("type") == "entities" and not p.get("enum"):
            raise HomeConfigError(f"param {name}: entities need an enum")
    return spec


def _value(name, p, raw):
    kind = p.get("type", "string")
    if kind == "entities":
        items = [raw] if isinstance(raw, str) else raw
        if not isinstance(items, list) or not items or any(i not in p["enum"] for i in items):
            raise ValueError(f"{name} must be one or more of: {', '.join(p['enum'])}")
        return items
    if kind in ("integer", "number"):
        try:
            value = int(raw) if kind == "integer" else float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be a number") from None
        if ("min" in p and value < p["min"]) or ("max" in p and value > p["max"]):
            raise ValueError(f"{name} must be between {p.get('min')} and {p.get('max')}")
        return value * p["scale"] if p.get("scale") else value
    if kind == "boolean":
        return bool(raw)
    value = str(raw).strip()
    if p.get("enum"):
        match = next((o for o in p["enum"] if o.lower() == value.lower()), None)
        if match is None:
            raise ValueError(f"{name} must be one of: {', '.join(p['enum'])}")
        value = match
    return value


def build_call(spec, params):
    """The exact HA call for an allowlisted action: ("service", "domain.service", data) or ("post", path, body).
    Raises ValueError for unknown, missing or out-of-range params."""
    params = dict(params or {})
    specs = spec.get("params") or {}
    unknown = set(params) - set(specs)
    if unknown:
        raise ValueError(f"unknown params: {', '.join(sorted(unknown))}; allowed: {', '.join(specs) or 'none'}")
    data = {k: (dict(v) if isinstance(v, dict) else v) for k, v in (spec.get("data") or {}).items()}
    for name, p in specs.items():
        if name not in params or params[name] in (None, ""):
            if p.get("required"):
                raise ValueError(f"{name} is required")
            continue
        value = _value(name, p, params[name])
        key = p.get("as", name)
        if p.get("into") == "variables":
            data.setdefault("variables", {})[key] = value
        else:
            data[key] = value
    if spec.get("service"):
        return "service", spec["service"], data
    return "post", spec["post"], data


def describe(actions):
    """The ha_action tool description: one line per allowlisted action."""
    lines = []
    for action_id, spec in actions.items():
        params = []
        for name, p in (spec.get("params") or {}).items():
            kind = p.get("type", "string")
            bits = [kind]
            if p.get("enum") and len(p["enum"]) <= 60:
                bits.append("|".join(p["enum"]))
            if "min" in p or "max" in p:
                bits.append(f"{p.get('min')}..{p.get('max')}")
            if p.get("required"):
                bits.append("required")
            if p.get("description"):
                bits.append(p["description"])
            params.append(f"{name} ({', '.join(bits)})")
        lines.append(f"- {action_id}: {spec['description']}" + (f" Params: {'; '.join(params)}." if params else ""))
    return "\n".join(lines)


def compact_state(st):
    """A state trimmed to what Claude needs."""
    entity = st.get("entity_id", "")
    domain = entity.split(".")[0]
    attrs = st.get("attributes") or {}
    out = {"id": entity, "state": st.get("state"), "name": (attrs.get("friendly_name") or "").strip()}
    for key in ATTRS.get(domain, ()):
        if attrs.get(key) not in (None, "", []):
            value = attrs[key]
            if key == "brightness":
                value = round(value / 2.55)
                key = "brightness_pct"
            elif key == "volume_level":
                value = round(value * 100)
                key = "volume_pct"
            out[key] = value
    return out
