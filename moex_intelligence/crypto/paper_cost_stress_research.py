"""Fixed-scenario execution-cost sensitivity for v0.9 sealed research ONLY.

No parameter search, model fitting, trade recommendation, or live execution.
Scenarios are PREDEFINED hypothetical spread and slippage assumptions,
not observed bid/ask tapes or account-specific exchange fees.
"""
from __future__ import annotations

from decimal import Decimal

from .costs import CostModel, ExecutionAssumptions
from .paper_path_research import simulate_paper_paths
from .paper_rules_research import ResearchSpotRules

VERSION="offline-cost-stress-v09-1"

# PRE-REGISTERED BEFORE any data inspection. All values in basis points.
# A 1bp assumption is 0.01% of notional; taker fee is 10bps each way
# under local default Paper FeeSchedule, separate from these values.
SCENARIOS=(
    ("LOW_COST_ASSUMPTION",0,2),
    ("PAPER_LIKE_ASSUMPTION",4,5),
    ("STRESSED_COST_ASSUMPTION",15,15),
)


def run_paper_cost_stress(candles, symbol, timeframe, *,
                          initial_cash="10000", max_hold_bars=16,
                          assumed_rules=None, min_required_origins=30,
                          base_fee_model=None):
    """Repeat identical fixed-rule research under 3 independent cost scenarios.

    Trading signals use identical causal source history and model versions,
    but chosen trade quantities and even executed hypothetical trades may
    differ as the cost/risk gates change. Not a per-trade paired comparison.
    No final 20% price outcome is scored or used for scenario selection.
    """
    base = CostModel() if base_fee_model is None else base_fee_model
    if not isinstance(base,CostModel):
        raise ValueError("Expected a validated CostModel")
    if assumed_rules is not None and (
            not isinstance(assumed_rules,ResearchSpotRules)
            or assumed_rules.symbol!=symbol):
        raise ValueError("Cost scenario assumed-rule symbol mismatch")
    cases=[]
    sealed=None
    fold_windows=None
    for name,spread,slippage in SCENARIOS:
        model=CostModel(
            fees=base.fees,
            execution=ExecutionAssumptions(
                slippage_bps=str(slippage),
                version="offline-hypothetical-cost-sensitivity-v09"))
        result=simulate_paper_paths(
            candles,symbol,timeframe,
            assumed_spread_bps=spread,
            initial_cash=initial_cash,max_hold_bars=max_hold_bars,
            cost_model=model,min_required_origins=min_required_origins,
            assumed_rules=assumed_rules)
        if result["final_holdout_evaluated"] or result["trading_edge_verified"]:
            raise ValueError("Cost stress violated sealed final research gate")
        fingerprint=result["final_holdout_sha256"]
        windows=tuple((f["start_index"],f["end_exclusive"])
                      for f in result["folds"])
        if sealed is None:
            sealed=fingerprint
            fold_windows=windows
        if fingerprint!=sealed or fold_windows!=windows:
            raise ValueError("Cost stress failed fold/holdout parity")
        cases.append({
            "scenario":name,
            "spread_assumed_bps":str(spread),
            "slippage_assumed_bps_per_side":str(slippage),
            "taker_fee_assumed":model.fees.taker,
            "trade_count":sum(f["trade_count"] for f in result["folds"]),
            "folds":[{
                "number":f["fold"],
                "start_index":f["start_index"],
                "end_exclusive":f["end_exclusive"],
                "trade_count":f["trade_count"],
                "net_return_pct":f["net_return_pct"],
                "ending_cash":f["ending_cash"],
                "max_marked_drawdown_pct":
                    f["marked_equity_guards"]["max_marked_drawdown_pct"],
                "blocked_day_loss":f["events"]["blocked_day_loss"],
                "blocked_week_loss":f["events"]["blocked_week_loss"],
                "blocked_drawdown":f["events"]["blocked_drawdown"],
                "rejected_rules":f["events"]["rejected_rules"],
            } for f in result["folds"]],
            "status":result["status"],
        })
    return {
        "mode":"PREDECLARED_OFFLINE_COST_ASSUMPTION_STRESS",
        "version":VERSION,
        "symbol":symbol,"timeframe":timeframe,
        "cost_scenarios":cases,
        "scenario_count":len(cases),
        "scenario_defs_fixed_in_source":True,
        "assumed_spot_rules":assumed_rules.snapshot() if assumed_rules else None,
        "final_holdout_sha256":sealed,
        "final_holdout_evaluated":False,
        "trading_edge_verified":False,
        "live_trading_enabled":False,
        "note":"All scenario numbers are hypothetical, not observed quotes "
               "or account fees. More expensive execution can change entry "
               "size, eligibility, stops and trade paths. Reports are NOT "
               "per-trade paired, even if same source candles and sealed "
               "fold boundaries are used. No model/signal selection or "
               "profitability claim is authorized by this analysis. "
               "Each fold starts with new cash; no combined portfolio return."}
