package hu.csabi.adbkeeper;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.ServiceInfo;
import android.os.IBinder;
import android.util.Log;

/**
 * Keeps PowerGuard registered: Android 8+ no longer delivers charger broadcasts to manifest receivers,
 * so a running (foreground) service has to hold the receiver.
 */
public class GuardService extends Service {
    private PowerGuard guard;

    static void start(Context c) {
        try {
            c.startForegroundService(new Intent(c, GuardService.class));
        } catch (RuntimeException e) {
            Log.w(Keeper.TAG, "power guard service not started: " + e);
        }
    }

    @Override public void onCreate() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel("guard", "Screen guard", NotificationManager.IMPORTANCE_MIN));
        Notification n = new Notification.Builder(this, "guard").setSmallIcon(android.R.drawable.ic_lock_idle_charging)
                .setContentTitle("Screen guard").setContentText("Keeps the screen off when the charger flickers").build();
        startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        guard = new PowerGuard();
        IntentFilter f = new IntentFilter(Intent.ACTION_POWER_CONNECTED);
        f.addAction(Intent.ACTION_POWER_DISCONNECTED);
        registerReceiver(guard, f, Context.RECEIVER_NOT_EXPORTED);
        Log.i(Keeper.TAG, "power guard listening");
    }

    @Override public int onStartCommand(Intent i, int flags, int id) { return START_STICKY; }
    @Override public void onDestroy() { if (guard != null) unregisterReceiver(guard); }
    @Override public IBinder onBind(Intent i) { return null; }
}
