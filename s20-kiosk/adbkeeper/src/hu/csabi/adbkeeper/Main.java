package hu.csabi.adbkeeper;

import android.app.Activity;
import android.os.Bundle;
import android.widget.Toast;

public class Main extends Activity {
    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        Keeper.ensure(this);
        Keeper.schedule(this);
        // 1.5's screen guard made this app a device admin; 1.6 no longer needs it
        android.app.admin.DevicePolicyManager dpm = getSystemService(android.app.admin.DevicePolicyManager.class);
        android.content.ComponentName admin = new android.content.ComponentName(this, Admin.class);
        if (dpm.isAdminActive(admin)) dpm.removeActiveAdmin(admin);
        Toast.makeText(this, "Wireless debugging kept on", Toast.LENGTH_SHORT).show();
        finish();
    }
}
