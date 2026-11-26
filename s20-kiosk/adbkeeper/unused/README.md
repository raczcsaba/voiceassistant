Screen guard (ADB Keeper 1.5), removed in 1.6 on 2026-11-24.
It turned the screen off again (DevicePolicyManager.lockNow) when a charger reconnect woke it. That broke Kiosk
Satellite's motion wake: KS treats a screen it didn't switch off as "dashboard, no screensaver", and then motion only
resets its idle timer, so the tablet stayed dark. Don't bring it back without telling KS (e.g. its own screenOff command).
