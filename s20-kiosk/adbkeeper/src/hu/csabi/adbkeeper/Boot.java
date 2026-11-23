package hu.csabi.adbkeeper;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class Boot extends BroadcastReceiver {
    @Override public void onReceive(Context c, Intent i) {
        Keeper.ensure(c);
        Keeper.schedule(c);
    }
}
