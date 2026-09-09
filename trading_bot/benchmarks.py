"""Deterministic, LLM-free benchmarks tracked once per cycle.

- btc_buy_hold: all initial cash into BTC-USDT at the first cycle, held.
- equal_weight: initial cash split equally across the experiment universe, held.
- momentum_baseline: rebalance each cycle to an equal split across symbols whose
  supplied momentum is positive; otherwise hold USDT. No look-ahead, no model.

State is a plain dict so the cycle can persist it in state/experiment.json (or a
dedicated file) and pass it back next cycle.
"""


def init_state(prices: dict, initial_cash: float) -> dict:
    syms = sorted(prices)
    per = initial_cash / len(syms)
    return {
        'initial_cash': float(initial_cash),
        'start_prices': {s: float(prices[s]) for s in syms},
        'btc_units': (initial_cash / prices['BTC-USDT']) if 'BTC-USDT' in prices else 0.0,
        'ew_units': {s: per / float(prices[s]) for s in syms},
        'mom_cash': float(initial_cash),
        'mom_units': {s: 0.0 for s in syms},
        'equity': {
            'btc_buy_hold': float(initial_cash),
            'equal_weight': float(initial_cash),
            'momentum_baseline': float(initial_cash),
        },
    }


def _mom_equity(state, prices):
    return state['mom_cash'] + sum(state['mom_units'][s] * prices[s] for s in state['mom_units'])


def update(state: dict, prices: dict, momentum: dict | None = None) -> dict:
    """Return a new state with equities recomputed and the momentum book rebalanced."""
    st = {**state,
          'btc_units': state['btc_units'],
          'ew_units': dict(state['ew_units']),
          'mom_units': dict(state['mom_units']),
          'mom_cash': state['mom_cash']}

    btc_eq = st['btc_units'] * prices.get('BTC-USDT', 0.0)
    ew_eq = sum(st['ew_units'][s] * prices[s] for s in st['ew_units'] if s in prices)

    if momentum is not None:
        equity_now = _mom_equity(st, prices)
        winners = sorted(s for s, m in momentum.items() if m is not None and m > 0 and s in prices)
        st['mom_units'] = {s: 0.0 for s in st['mom_units']}
        if winners:
            per = equity_now / len(winners)
            for s in winners:
                st['mom_units'][s] = per / prices[s]
            st['mom_cash'] = 0.0
        else:
            st['mom_cash'] = equity_now
    mom_eq = _mom_equity(st, prices)

    st['equity'] = {
        'btc_buy_hold': btc_eq,
        'equal_weight': ew_eq,
        'momentum_baseline': mom_eq,
    }
    return st
