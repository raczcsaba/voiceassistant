package hu.csabi.adbkeeper;

import android.app.admin.DevicePolicyManager;
import android.app.usage.UsageEvents;
import android.app.usage.UsageStatsManager;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.util.Log;

/**
 * Android turns the screen on whenever the charger connects or disconnects. A flaky cable does that
 * many times a night, so: if the screen was off just before a charger event, switch it off again.
 * Needs device admin (dpm set-active-admin) and usage access (appops GET_USAGE_STATS) granted over adb.
 */
public class PowerGuard extends BroadcastReceiver {
    static final String TAG = "AdbKeeper";
    static final long SETTLE_MS = 3000;   // a drop is a disconnect plus a reconnect about 1-2 s later
    static final long BURST_MS = 6000;    // charger events this close belong to one drop
    static final long BEFORE_MS = 3000;   // screen state is read this long before the drop started

    @Override public void onReceive(Context c, Intent i) {
        long now = System.currentTimeMillis();
        SharedPreferences p = c.createDeviceProtectedStorageContext().getSharedPreferences("guard", 0);
        long last = p.getLong("last", 0);
        long start = now - last > BURST_MS ? now : p.getLong("start", now);
        p.edit().putLong("last", now).putLong("start", start).commit();
        PendingResult result = goAsync();
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            try {
                if (p.getLong("last", 0) == now) check(c, start);  // only the last event of a drop acts
            } catch (RuntimeException e) {
                Log.e(TAG, "power guard: " + e);
            } finally {
                result.finish();
            }
        }, SETTLE_MS);
    }

    static void check(Context c, long start) {
        if (!c.getSystemService(PowerManager.class).isInteractive()) return;
        Boolean wasOn = screenOnAt(c, start - BEFORE_MS);
        if (wasOn == null || wasOn) return;
        DevicePolicyManager dpm = c.getSystemService(DevicePolicyManager.class);
        if (!dpm.isAdminActive(new ComponentName(c, Admin.class))) {
            Log.e(TAG, "power guard: not device admin: adb shell dpm set-active-admin hu.csabi.adbkeeper/.Admin");
            return;
        }
        dpm.lockNow();
        Log.i(TAG, "power guard: charger event woke the screen, switched it off again");
    }

    /** Screen state at time t from the usage-event history; null when unknown. */
    static Boolean screenOnAt(Context c, long t) {
        UsageEvents ev = c.getSystemService(UsageStatsManager.class).queryEvents(t - 6 * 3600 * 1000L, t);
        UsageEvents.Event e = new UsageEvents.Event();
        Boolean on = null;
        while (ev.hasNextEvent()) {
            ev.getNextEvent(e);
            if (e.getEventType() == UsageEvents.Event.SCREEN_INTERACTIVE) on = true;
            else if (e.getEventType() == UsageEvents.Event.SCREEN_NON_INTERACTIVE) on = false;
        }
        if (on == null) Log.w(TAG, "power guard: no screen history (usage access missing?)");
        return on;
    }
}
