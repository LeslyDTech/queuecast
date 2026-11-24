# 3. Separate random streams and time-rescaled arrivals

**Status:** Accepted

## Context

Calibration searches for the demand that makes a ride's simulated average wait match its real one. The first version drew everything from one `random.Random`: arrivals (by thinning), lane choice, and breakdowns.

Changing demand even slightly changed how many random numbers arrivals consumed. That shifted every later draw, including when breakdowns happened, so neighboring demand values produced unrelated days. In practice:

- With 3 seeds, the search *looked* accurate (errors of 1–2 minutes).
- Re-measuring with 5 seeds after rounding demand to a whole number showed the truth: a 6.3-minute average error, with a worst case of 24 minutes.
- Gringotts moved from 45 to 50 minutes just from rounding.

## Decision

1. **Common random numbers.** Arrivals, lane choice, and breakdowns each get their own seeded stream (`"{seed}:arrivals"`, and so on). Breakdown timing no longer depends on demand.
2. **Time-rescaled arrivals.** Generate a unit-rate Poisson process and map each point through the inverse of the cumulative arrival curve. Raising demand compresses arrival times smoothly while reusing the same random draws.
3. **Calibrate on 20 simulated days** instead of 3–5, because breakdowns make single days vary widely. One Gringotts day ranges from about 25 to 137 minutes.
4. **Always re-measure after rounding** and report that number.

## Consequences

- Simulated waits now change smoothly as demand changes, so bisection converges.
- On 40 days the calibration never saw, the mean error is 2.8 minutes and every ride is within 5.
- What-if comparisons in the dashboard and CLI are fairer: changing the priority share no longer changes when breakdowns happen.
- Every run produces different numbers than the first release, so README examples were regenerated.
