# American Picks Source Architecture

## Goal

Keep `Pick 3` and `Pick 4` complete for the current day without depending on a single source.

## Source priority

### 1. Primary live source

Use the fastest live source per state/draw:

- `pick-3.com`
- `pick-4.com`
- direct state-specific subdomains when they are stronger than the overview

This is the source used for same-day freshness.

### 2. Secondary live fallback

Use `lotteryusa.com` for IDs that remain empty after the first pass.

Current critical fallback coverage includes:

- `AZ` pick3
- `OK` pick3
- `NE` pick3
- `CT` pick4
- `FL` pick4
- `IL` pick4
- `IN` pick4
- `MS` pick4
- `MO` pick4
- `NC` pick4
- `NE` pick4
- `TX` pick4
- `VA` pick4
- `NJ` pick3/pick4 backup
- `WA` Match 4

### 3. Historical / reconciliation source

Use a paid aggregator only for reconciliation, audits, and backfill, not as the main same-day source.

Reason:

- paid aggregators such as Magayo are useful for normalized data
- but their published update window is not tight enough to be the only live source for an active POS market

## Save rules

### Never downgrade a published pick

If a result already has a number:

- a new `pending`
- an empty row
- or a weaker scrape

must not overwrite it.

### Allow upgrade

If an existing row is `pending` and a new row has a real number:

- promote to published
- keep fresh timestamps

## Cache strategy

### Current day

- scrape live
- save merged result set
- preserve stronger rows

### Previous days

- prefer saved cache
- backfill only when a row is missing or marked bad

## Retry policy

### Request level

- retry network failures up to 3 times
- exponential backoff
- do not keep retrying 4xx client errors

### State-critical fallback

If these remain empty after first pass, trigger secondary fetch immediately:

- `NJ`
- `FL`
- `IL`
- `IN`
- `NC`
- `TX`
- `VA`
- `CT`
- `MO`
- `MS`
- `AZ`
- `OK`
- `NE`

## Production flow

1. Run live scrape for `pick3` and `pick4`
2. Fill from state history pages
3. Fill missing IDs from `Lottery USA`
4. Merge with existing cache
5. Save only stronger-or-equal data
6. Publish to app cache

## Operational rule

For current day:

- `pick3_pending` must be `0` after final nightly run
- `pick4_pending` must be `0` after final nightly run

If not:

- log missing IDs explicitly
- run targeted retry by ID/state
- do not silently report success as if market were complete
