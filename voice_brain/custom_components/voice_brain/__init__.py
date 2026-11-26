"""Fast local voice commands: a language model on the Proxmox GPU turns text into actions.
Anything that isn't quick device control is handed to the Claude worker (see worker.py)."""
from . import views, worker


async def async_setup_entry(hass, entry):
    data = hass.data.setdefault(worker.DOMAIN, {})
    data["worker_url"] = entry.options.get("worker_url", worker.WORKER_URL).rstrip("/")
    if not data.get("views"):  # HTTP views can't be unregistered, so only once per HA run
        views.register(hass)
        data["views"] = True
    await hass.config_entries.async_forward_entry_setups(entry, ["conversation"])
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, ["conversation"])
