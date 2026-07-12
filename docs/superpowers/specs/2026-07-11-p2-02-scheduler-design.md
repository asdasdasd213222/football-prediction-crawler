# P2-02 Scheduler Design

Use an independent Redis-backed scheduler service. Per-source interval,
paused flag, last dispatch, and next run are stored in Redis; next run values
are calculated in `Asia/Shanghai`. Restart dispatches at most one overdue run
per source. The service provides manual trigger, pause, resume, and next-run
inspection, and sends only site-neutral source identifiers to P2-01 queues.
No locking or overlap prevention is implemented before P2-03.
