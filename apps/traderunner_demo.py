"""
Small demo wiring GotobiBT into the TradeRunner backend using Backtrader.
Run with: python apps/traderunner_demo.py
"""

from pathlib import Path

from backend import RunnerConfig, StrategySpec, TradeRunnerBuilder, DataHandler
from strategies.gotobi_bt import GotobiBT


def main():
    data_path = Path("data/usdjpy_1min_2024-01-01_2025-10-01.parquet")
    if not data_path.exists():
        raise SystemExit(f"Missing sample data at {data_path}")

    handler = DataHandler()
    df = handler.load_parquet(data_path)

    spec = StrategySpec(
        symbol="USDJPY",
        strategy=GotobiBT,
        data=df,
        params={
            "entry_time": "01:30:00",
            "exit_time": "08:30:00",
            "trade_size": 1.0,
        },
        name="gotobi-usdjpy",
        cash=250_000,
        commission=0.0,
    )

    pool = TradeRunnerBuilder().build([spec], config=RunnerConfig(mode="backtest"))
    runner = pool.runners[0]
    runner.run()

    broker_value = runner.cerebro.broker.getvalue() if runner.cerebro else None
    print(f"Completed run. Final broker value: {broker_value}")


if __name__ == "__main__":
    main()
