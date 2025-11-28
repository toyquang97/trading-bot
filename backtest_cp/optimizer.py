# backtest/optimizer.py

def grid_search(df, strategy_class, param_grid):
    results = []
    
    for params in param_grid:
        strat = lambda engine: strategy_class(engine, **params)
        engine = HybridBacktestEngine(df, strat)
        out = engine.run()
        
        results.append({
            "params": params,
            "balance": out["balance"]
        })
    
    results = sorted(results, key=lambda x: -x["balance"])
    return results
