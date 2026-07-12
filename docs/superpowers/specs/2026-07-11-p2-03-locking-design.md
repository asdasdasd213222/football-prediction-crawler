# P2-03 Distributed Locking Design

P2-03 adds site-neutral Redis leases around source task execution. A lease uses
an atomic Redis `SET` with `NX`, a bounded expiry, and a random owner token.
Only the owner token may extend or release the lock. The task keeps its lease
alive for longer-running work and safely records `skipped_overlap` when another
task already owns the source lease.

Locks are keyed by source id by default. A public page-scope key builder is
included for later paginated work, but no pagination behavior is added here.
Workers that crash stop renewing their leases; expiry then allows recovery. No
retry, backoff, rate limiting, circuit breaker, CAPTCHA handling, or source
collection logic is included in this task.
