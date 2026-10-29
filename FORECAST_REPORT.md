# Forecast / Backtest status — rc3

No forecasting model is active. UI explicitly reports UNAVAILABLE; no future candles, artificial forecast path or invented success probability are drawn. Investment Time Machine is preserved separately and is not relabelled as a validated crypto model.

Implemented foundation: immutable typed RegimeSnapshot, ForecastPoint, Forecast, DecisionContext, ForecastEngine protocol. UnavailableForecastEngine returns no points. ForecastHistory accepts only EXPERIMENTAL predictions, validates causal timestamps, future UTC-aligned horizons, finite positive ordered bands and nominal coverage. VALIDATED promotion is blocked until an independent validation registry exists.

A prediction is insert-only by ID/content. Same ID/same content is idempotent after restart; different content is rejected. DB triggers also reject update/delete. Actual outcomes are separate append-only records obtained from persisted closed candles after target maturity. Unclosed/missing/future candles are ignored. This is a storage/causality contract, not proof of model quality; nominal interval level is not empirical coverage.

Tests cover no-model output, late publication, target alignment, future input, invalid bands, false validation claims, immutable history, closure/maturity, duplicate outcomes and restart. No public forecast is generated during startup.

Not implemented: crypto Historical Volatility/Random Walk/Trend Persistence baselines, calibrated quantiles, walk-forward/purge/embargo pipeline, held-out data, next-quote execution backtest, empirical forecast coverage/MAE/RMSE/pinball loss, sensitivity/regime tests and Forecast Overlay. Therefore no numerical forecast/backtest result is supplied. A dataset-backed report requires a subsequent v0.9 research phase.

The pinned six-module day-trader-skill review is in docs/research. Its NYSE slot bootstrap and TP/(TP+SL) conditional rate cannot be treated as a calibrated Crypto probability or copied without modeling costs, gap execution and validation. No upstream script was executed or installed.
