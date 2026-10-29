# Signal technical status — rc3

Existing causal EMA/ATR/RSI/ADX/Supertrend, strategy conditions and closed-candle publication preserved. POTENTIAL/WATCHING evaluates the current bar without claiming confirmation; closed-bar signals retain their ID, candle time, availability/detection timestamps and explanations. Lifecycle re-evaluates expiry, invalidation, entry drift and risk, with separate NO_SIGNAL/CONFIRMED/ACTIONABLE states.

Markers use confirmation-boundary timestamps. Hover distinguishes historical condition from actual detected time and execution; no retroactive purchase implied. Store.publish inserts confirmed history only once. Notifications deduplicate by state per event; delivery with a closed browser is not promised. Signal type EXIT sells only an existing long, never opens short.

New manual provenance explicitly links a chosen lifecycle record. The immutable preview keeps state at selection, fill metadata records actual state again under transaction. Changes afterwards do not rewrite the fill. A manual trade can be made without a linked signal if the independent risk gate allows it.

Existing unit tests cover prefix/no-lookahead consistency, intrabar change, closed-only confirmation, expiry/stale gating, restart/deduplication, marker timestamps and streaming/history equivalence. Full execution list is in TEST_REPORT_FINAL.md. No win probability, calibrated score or validated profitability is claimed. Computational incremental checkpoints remain future optimization; no algorithm was replaced to improve screenshots.
