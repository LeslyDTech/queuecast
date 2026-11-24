# Data sources and calibration

## What's real, what's estimated

| Field | Source | Real or estimated |
| --- | --- | --- |
| Ride name, park, land | [Queue-Times.com](https://queue-times.com/) park listings | Real |
| `queue_times_id`, `queue_times_park_id` | Queue-Times.com | Real |
| `real_avg_posted_wait_min` | Queue-Times.com "average queue time by ride (all time)" | Real (posted waits) |
| `vehicle_capacity`, `dispatch_interval_s` | Public descriptions of each ride system | **Estimated** |
| `mtbf_minutes`, `mttr_minutes` | Same default for every ride (6 h between failures, 20 min repairs) | **Assumed** |
| `base_arrivals_per_hour` | Solved by `queuecast calibrate` | **Calibrated** |

Rides listed by Queue-Times that aren't a ride line of their own were left out: single-rider lines, Ollivanders, character meets, and walk-through attractions.

## Calibration method

Demand (guests per hour at peak) is the one number nobody publishes, so it's solved for:

1. Express demand as a fraction of the ride's estimated hourly capacity, from 5% to 200%.
2. For a candidate demand, simulate 20 days (seeds 1–20) with the default daily crowd curve and no priority lane.
3. For each day, compute the **average posted wait**: the mean standby wait in each 15-minute window, averaged across the day. This mirrors how a posted-wait average is built, with one reading per time window.
4. Use bisection to find the demand where the 20-day mean matches the real average.
5. Round the demand to a whole number, re-measure, and report the remaining error.

### Results

Checked against 40 simulated days the calibration never saw (seeds 21–60):

- Mean absolute error: **2.8 minutes**.
- All 41 rides were within 5 minutes of their real average.
- Errors lean slightly high: rare long breakdowns create a long tail of very bad days.

## Limits worth knowing

- **Posted waits aren't actual waits.** Parks often pad posted times, and Queue-Times notes that posted times are frequently incorrect.
- **Capacity estimates drive everything else.** If a ride's real capacity is higher than estimated, calibration will infer more demand to compensate. The *posted wait* fit stays right, but the guest counts would be off.
- **One crowd curve for every ride and every day.** Real parks vary by season, day of week, and park hours.
- **Guests never leave the line**, so very high crowd settings produce unrealistically long waits. This is on the roadmap.
- **Priority lanes are set to zero during calibration.** Real posted waits already include the effect of Universal Express, so the calibrated demand absorbs it.

## Attribution

Live and historical wait data is [Powered by Queue-Times.com](https://queue-times.com/). QueueCast is not affiliated with Universal or Queue-Times.com.
