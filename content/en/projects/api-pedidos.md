---
title: High-throughput orders API
summary: An asynchronous API that processes thousands of orders per minute with predictable latency.
repo: octocat/Spoon-Knife
skills: [python, fastapi, asyncio, sqlalchemy, postgres, pytest, docker]
tags: [api, async, data]
featured: true
order: 2
year: 2024
---
## Problem

The previous monolith stalled at peak hours: order queues grew and the p95 went past 480 ms.

## Solution

I rewrote the critical flow as an asynchronous API with FastAPI, SQLAlchemy 2 in async mode and PostgreSQL, moving slow operations into background tasks.

## Architecture

Routes are thin and delegate to testable services. Idempotent operations use idempotency keys so client retries never duplicate orders.

## Results

- p95 from 480 ms to 130 ms.
- Zero duplicated orders after adopting idempotency keys.
- Test coverage from 40% to 88%.

## Lessons learned

Measuring before optimizing saved weeks: the bottleneck was two queries, not the framework.
