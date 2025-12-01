from __future__ import annotations

import importlib
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

import backtrader as bt
import pandas as pd

from ..data.pipeline import DataHandler, DataNormalizer, DataPackage, StreamingOHLCVFeed


@dataclass
class RiskEstimator:
    """
    Basic risk helper used by TradeRunner.
    """

    max_position: float | None = None          # abs units per runner
    max_notional: float | None = None          # price * size cap
    risk_fraction: float = 0.01                # fraction of cash risked per trade
    stop_loss_pct: float | None = None         # optional stop size used for sizing

    def validate(self, price: float, size: float, cash: float | None = None) -> None:
        if self.max_position is not None and abs(size) > self.max_position:
            raise ValueError(f"Size {size} exceeds max_position {self.max_position}")
        if self.max_notional is not None and abs(price * size) > self.max_notional:
            raise ValueError(f"Notional {price * size} exceeds max_notional {self.max_notional}")
        if cash is not None and cash <= 0:
            raise ValueError("Cash must be positive for risk checks")

    def suggested_size(self, price: float, cash: float) -> float:
        if price <= 0:
            return 0.0
        if self.stop_loss_pct and self.stop_loss_pct > 0:
            risk_amt = cash * self.risk_fraction
            per_unit_risk = price * self.stop_loss_pct
            return max(0.0, risk_amt / per_unit_risk)
        return (cash * self.risk_fraction) / price

    def to_sizer(self, cash: float):
        """
        Returns a Backtrader sizer class + kwargs based on risk caps.
        """
        if self.max_notional:
            pct = min(100.0, (self.max_notional / cash) * 100.0)
            return bt.sizers.PercentSizer, {"percents": pct}
        return bt.sizers.FixedSize, {"stake": 1}


@dataclass
class RunnerConfig:
    mode: str = "backtest"                     # "backtest" or "live"
    preload: bool = True
    cheat_on_open: bool = False
    tz: str | None = "UTC"
    resample: str | None = None                # pandas rule, optional
    cerebro_factory: Any | None = None         # override to inject custom Cerebro
    contracts_config_path: str | None = "config/contracts.json"
    contract_sizes: Dict[str, float] | None = None
    default_contract_size_fx: float | None = None  # fallback per-lot size for FX if symbol-specific missing
    base_currency: str = "USD"                 # account/base currency
    invert_fx_to_base: bool = False            # if True and quote!=base, invert price series and flip trade signs


@dataclass
class StrategySpec:
    symbol: str
    strategy: type[bt.Strategy] | str
    data: pd.DataFrame | StreamingOHLCVFeed | DataPackage | Any
    params: dict[str, Any] = field(default_factory=dict)
    strategies: Optional[Sequence[Tuple[type[bt.Strategy] | str, dict[str, Any]]]] = None
    analyzers: Optional[Sequence[Tuple[Any, dict[str, Any]]]] = None
    name: Optional[str] = None
    risk: Optional[RiskEstimator] = None
    cash: float = 100_000
    commission: float = 0.0
    leverage: float | None = None
    contract_size: float | None = None         # per-symbol contract size (e.g., 100_000 for FX lots)


class TradeRunner:
    """
    Wraps a Backtrader Cerebro instance for a single strategy + instrument.
    Handles data normalization, sizing, and threaded execution if needed.
    """

    def __init__(
        self,
        spec: StrategySpec,
        *,
        config: Optional[RunnerConfig] = None,
        normalizer: Optional[DataNormalizer] = None,
        data_handler: Optional[DataHandler] = None,
    ):
        self.spec = spec
        self.config = config or RunnerConfig()
        if self.config.contract_sizes is None:
            self.config.contract_sizes = self._load_contract_sizes(self.config.contracts_config_path)
        self.normalizer = normalizer or DataNormalizer()
        self.data_handler = data_handler or DataHandler(self.normalizer)
        self.risk = spec.risk or RiskEstimator()
        self._thread: Optional[threading.Thread] = None
        self._results: Any = None
        self._cerebro: Optional[bt.Cerebro] = None

    # ---- build helpers ----
    def _resolve_strategy(self) -> type[bt.Strategy]:
        strat = self.spec.strategy
        if isinstance(strat, str):
            module_name, cls_name = strat.rsplit(".", 1)
            module = importlib.import_module(module_name)
            strat_cls = getattr(module, cls_name)
        else:
            strat_cls = strat
        if not issubclass(strat_cls, bt.Strategy):
            raise TypeError(f"{strat_cls} is not a Backtrader Strategy")
        return strat_cls

    def _resolve_strategy_ref(self, strat_ref: Any) -> type[bt.Strategy]:
        if isinstance(strat_ref, str):
            module_name, cls_name = strat_ref.rsplit(".", 1)
            module = importlib.import_module(module_name)
            strat_cls = getattr(module, cls_name)
        else:
            strat_cls = strat_ref
        if not issubclass(strat_cls, bt.Strategy):
            raise TypeError(f"{strat_cls} is not a Backtrader Strategy")
        return strat_cls

    def _resolve_analyzer(self, analyzer: Any):
        if isinstance(analyzer, str):
            module_name, cls_name = analyzer.rsplit(".", 1)
            module = importlib.import_module(module_name)
            return getattr(module, cls_name)
        return analyzer

    @staticmethod
    def _is_fx_symbol(sym: str) -> bool:
        s = sym.upper().replace(":", "").replace(".", "")
        return len(s) == 6 and s.isalpha()

    @staticmethod
    def _fx_base_quote(sym: str) -> Optional[Tuple[str, str]]:
        s = sym.upper().replace(":", "").replace(".", "")
        if len(s) != 6 or not s.isalpha():
            return None
        return s[:3], s[3:]

    @staticmethod
    def _load_contract_sizes(path: Optional[str]) -> Dict[str, float]:
        if not path:
            return {}
        p = Path(path)
        if not p.exists():
            return {}
        if p.suffix.lower() not in {".json", ".jsn"}:
            raise ValueError(f"Unsupported contract size config format: {p}")
        data = json.loads(p.read_text())
        # normalize keys as uppercase no separators
        return {k.upper().replace(".", "").replace(":", ""): float(v) for k, v in data.items()}

    def _resolve_contract_size(self) -> float | None:
        if self.spec.contract_size:
            return self.spec.contract_size
        if self.config.contract_sizes:
            key = self.spec.symbol.upper().replace(".", "").replace(":", "")
            if key in self.config.contract_sizes:
                return self.config.contract_sizes[key]
        if self._is_fx_symbol(self.spec.symbol) and self.config.default_contract_size_fx:
            return self.config.default_contract_size_fx
        return None

    def _should_invert_fx(self) -> bool:
        if not self.config.invert_fx_to_base:
            return False
        pair = self._fx_base_quote(self.spec.symbol)
        if not pair:
            return False
        base, quote = pair
        if not self.config.base_currency:
            return False
        return quote != self.config.base_currency.upper()

    @staticmethod
    def _invert_ohlc(df: pd.DataFrame) -> pd.DataFrame:
        inv = df.copy()
        inv["open"] = 1.0 / df["open"]
        inv["high"] = 1.0 / df["low"]
        inv["low"] = 1.0 / df["high"]
        inv["close"] = 1.0 / df["close"]
        # keep volume as-is (tick volume)
        return inv

    def _with_contract_size(self, params: dict[str, Any]) -> dict[str, Any]:
        if not params or "trade_size" not in params:
            return params
        enriched = dict(params)

        # Flip sign if we inverted the FX pair so economics align (long USDJPY == short JPYUSD)
        if self._should_invert_fx():
            enriched["trade_size"] = -enriched["trade_size"]

        contract_size = self._resolve_contract_size()
        if not contract_size:
            return enriched
        enriched["trade_size"] = enriched["trade_size"] * contract_size
        return enriched

    def _add_strategies(self, cerebro: bt.Cerebro) -> None:
        entries: Sequence[Tuple[Any, dict[str, Any]]]
        if self.spec.strategies:
            entries = self.spec.strategies
        else:
            entries = [(self.spec.strategy, self.spec.params or {})]

        for strat_ref, params in entries:
            strat_cls = self._resolve_strategy_ref(strat_ref)
            enriched = self._with_contract_size(params or {})
            cerebro.addstrategy(strat_cls, **enriched)

    def _add_analyzers(self, cerebro: bt.Cerebro) -> None:
        if not self.spec.analyzers:
            return
        for analyzer_ref, params in self.spec.analyzers:
            analyzer_cls = self._resolve_analyzer(analyzer_ref)
            cerebro.addanalyzer(analyzer_cls, **(params or {}))

    def _build_feed(self) -> bt.feeds.DataBase:
        src = self.spec.data
        name = self.spec.name or self.spec.symbol

        if isinstance(src, DataPackage):
            df = src.dataframe
        elif isinstance(src, pd.DataFrame):
            df = src
        else:
            df = None

        if df is not None:
            normalized = self.normalizer.to_ohlcv(df, tz=self.config.tz)
            if self._should_invert_fx():
                normalized = self._invert_ohlc(normalized)
            feed = bt.feeds.PandasData(dataname=normalized, name=name)
            if self.config.resample:
                # Resample using pandas rule then feed to Cerebro
                resampled = self.data_handler.resample(normalized, rule=self.config.resample)
                feed = bt.feeds.PandasData(dataname=resampled, name=name)
            return feed

        if isinstance(src, StreamingOHLCVFeed):
            return src

        if hasattr(src, "get"):  # Queue-like for live streaming bars
            return StreamingOHLCVFeed(src, name=name)

        if isinstance(src, bt.feeds.DataBase):
            return src

        raise TypeError(f"Unsupported data source type for {name}: {type(src)}")

    def _build_cerebro(self) -> bt.Cerebro:
        cerebro = self.config.cerebro_factory() if self.config.cerebro_factory else bt.Cerebro()
        cerebro.broker.setcash(self.spec.cash)
        if self.spec.leverage is not None:
            cerebro.broker.setcommission(commission=self.spec.commission, leverage=self.spec.leverage)
        else:
            cerebro.broker.setcommission(commission=self.spec.commission)
        if self.config.cheat_on_open:
            cerebro.broker.set_coc(True)

        data_feed = self._build_feed()
        cerebro.adddata(data_feed, name=self.spec.name or self.spec.symbol)

        self._add_strategies(cerebro)
        self._add_analyzers(cerebro)

        sizer_cls, sizer_kwargs = self.risk.to_sizer(self.spec.cash)
        cerebro.addsizer(sizer_cls, **sizer_kwargs)
        return cerebro

    # ---- lifecycle ----
    def run(self):
        self._cerebro = self._build_cerebro()
        self._results = self._cerebro.run()
        return self._results

    def start_async(self) -> threading.Thread:
        if self._thread and self._thread.is_alive():
            return self._thread
        self._thread = threading.Thread(target=self.run, name=f"TradeRunner-{self.spec.symbol}", daemon=True)
        self._thread.start()
        return self._thread

    def stop(self):
        if hasattr(self.spec.data, "put_nowait"):
            try:
                self.spec.data.put_nowait(None)
            except Exception:
                pass

    # ---- inspection ----
    @property
    def cerebro(self) -> Optional[bt.Cerebro]:
        return self._cerebro

    @property
    def results(self):
        return self._results


class TradeRunnerPool:
    """
    Collection manager for spawned TradeRunners.
    """

    def __init__(self, runners: Iterable[TradeRunner]):
        self.runners = list(runners)
        self._threads: list[threading.Thread] = []

    def start_all(self):
        self._threads = [r.start_async() for r in self.runners]
        return self._threads

    def join(self):
        for t in self._threads:
            if t:
                t.join()

    def stop_all(self):
        for r in self.runners:
            r.stop()


class TradeRunnerBuilder:
    """
    Builder that wires selected strategies + symbols into a pool of TradeRunners.
    """

    def __init__(self, *, normalizer: Optional[DataNormalizer] = None, data_handler: Optional[DataHandler] = None):
        self.normalizer = normalizer or DataNormalizer()
        self.data_handler = data_handler or DataHandler(self.normalizer)

    def build(
        self,
        specs: Sequence[StrategySpec],
        *,
        config: Optional[RunnerConfig] = None,
    ) -> TradeRunnerPool:
        cfg = config or RunnerConfig()
        runners = [
            TradeRunner(spec, config=cfg, normalizer=self.normalizer, data_handler=self.data_handler)
            for spec in specs
        ]
        return TradeRunnerPool(runners)
