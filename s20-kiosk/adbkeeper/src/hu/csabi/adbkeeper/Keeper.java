package hu.csabi.adbkeeper;

import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.ContentResolver;
import android.content.Context;
import android.provider.Settings;
import android.util.Log;

/** Keeps wireless debugging switched on. Needs WRITE_SECURE_SETTINGS, granted once over adb. */
final class Keeper {
    static final String TAG = "AdbKeeper";
    static final int JOB_PERIODIC = 1, JOB_ON_CHANGE = 2, JOB_SOON = 3;

    static void ensure(Context c) {
        ContentResolver r = c.getContentResolver();
        try {
            // Paired computers never lose their authorisation
            if (Settings.Global.getLong(r, "adb_allowed_connection_time", -1) != 0)
                Settings.Global.putLong(r, "adb_allowed_connection_time", 0);
            if (Settings.Global.getInt(r, "adb_wifi_enabled", 0) != 1) {
                Settings.Global.putInt(r, "adb_wifi_enabled", 1);
                Log.i(TAG, "wireless debugging re-enabled");
            }
        } catch (SecurityException e) {
            Log.e(TAG, "missing WRITE_SECURE_SETTINGS: adb shell pm grant hu.csabi.adbkeeper android.permission.WRITE_SECURE_SETTINGS");
        }
    }

    static void schedule(Context c) {
        JobScheduler js = c.getSystemService(JobScheduler.class);
        ComponentName job = new ComponentName(c, KeepJob.class);
        // Each job on its own, so one refused job never stops the others
        trySchedule(js, new JobInfo.Builder(JOB_PERIODIC, job)
                .setPeriodic(15 * 60 * 1000L).setPersisted(true).build());
        trySchedule(js, new JobInfo.Builder(JOB_SOON, job)
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_UNMETERED)
                .setMinimumLatency(5000).build());
        watch(c);
    }

    static void trySchedule(JobScheduler js, JobInfo info) {
        try {
            js.schedule(info);
        } catch (RuntimeException e) {
            Log.e(TAG, "job " + info.getId() + " refused: " + e);
        }
    }

    /** Fires when Android switches wireless debugging off (reboot, Wi-Fi change), once Wi-Fi is up. */
    static void watch(Context c) {
        trySchedule(c.getSystemService(JobScheduler.class), new JobInfo.Builder(JOB_ON_CHANGE, new ComponentName(c, KeepJob.class))
                .addTriggerContentUri(new JobInfo.TriggerContentUri(Settings.Global.getUriFor("adb_wifi_enabled"), 0))
                .setTriggerContentUpdateDelay(1000)
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_UNMETERED)
                .build());
    }
}
