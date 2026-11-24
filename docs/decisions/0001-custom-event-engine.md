# 1. Write a small event engine instead of using SimPy

**Status:** Accepted

## Context

The simulation needs a discrete-event engine. SimPy is the common Python library for this. It models processes as generators and handles resources and queues for you.

## Decision

Write a small engine (about 150 lines) using `heapq` and `collections.deque`.

## Reasons

- The model only has four event types, so a library adds more concepts than it saves.
- With an explicit event loop, every state change is visible and easy to test. For example, the tie-breaking order at equal timestamps is a single documented enum instead of library behavior.
- The core package stays free of third-party dependencies.

## Consequences

- If the model grows (for example, guests walking between many attractions, or shared staff), this decision should be revisited. SimPy's process and resource abstractions would start paying for themselves.
- Correctness depends on our own tests, so the engine has invariant tests that run on every push.
