# P2-01 Redis And Task Queue Design

## Scope

Add Redis-backed Celery workers and site-neutral task routing. This task does
not add scheduling, source adapters, real source access, credentials, or
production deployment.

## Runtime Model

Redis is Celery's broker only. PostgreSQL remains the durable system of record
for source data and change events; no Celery result backend is configured.
Compose defines Redis plus separate `worker-http` and `worker-browser`
services. Redis uses a named local volume for restart resilience.

`multisite_crawler.queueing` owns Celery configuration and queue metrics.
`multisite_crawler.tasks` owns site-neutral task entry points. Task payloads
contain only source identifiers and other non-sensitive values. No task,
scheduler, or queue contains source-specific selectors, parsing, or storage
rules.

## Delivery Safety

Both queues use late acknowledgement, rejection on worker loss, a prefetch
multiplier of one, and JSON serialization. These settings ensure an unfinished
task is eligible for redelivery after a worker exit. P1-04 record persistence
remains the idempotency boundary for repeated delivery.

Transient task failures retry at most three times with exponential backoff.
Tasks receive a 60-second soft time limit and a 75-second hard time limit.
Celery warm shutdown is used so workers stop accepting new work while allowing
an active task to finish within its timeout.

## Queues And Metrics

Routes are explicit: `http` tasks enter the `http` queue and `browser` tasks
enter the `browser` queue. Queue-length metrics query Redis list lengths and
return a typed snapshot for each queue. Metrics do not expose task payloads or
credentials.

## Verification

Tests cover task routing, retry policy, queue metric parsing, and task
idempotency delegation. A Docker integration check starts Redis and both worker
services, verifies Redis restart recovery, worker-loss redelivery, correct
queue routing, and repeated task delivery without duplicate business effects.
All repository quality checks run before P2-01 is checked in the work list.
