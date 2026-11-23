package hu.csabi.adbkeeper;

import android.app.job.JobParameters;
import android.app.job.JobService;

public class KeepJob extends JobService {
    @Override public boolean onStartJob(JobParameters p) {
        Keeper.ensure(this);
        if (p.getJobId() == Keeper.JOB_ON_CHANGE) Keeper.watch(this);
        return false;
    }
    @Override public boolean onStopJob(JobParameters p) { return true; }
}
