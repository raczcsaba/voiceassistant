package hu.csabi.adbkeeper;

import android.app.Activity;
import android.os.Bundle;
import android.widget.Toast;

public class Main extends Activity {
    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        Keeper.ensure(this);
        Keeper.schedule(this);
        Toast.makeText(this, "Wireless debugging kept on", Toast.LENGTH_SHORT).show();
        finish();
    }
}
