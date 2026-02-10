"""
MetaTrader 5 instrument provider.
Loads FX instrument specs from MT5 symbol_info.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.model.currencies import Currency
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Money, Price, Quantity

from trader.adapters.metatrader.common import MetaTrader5Connection
from trader.core.constants import MT5


class MetaTrader5InstrumentProvider(InstrumentProvider):
    """
    Provides instrument definitions by querying MetaTrader 5 symbol_info.
    """

    def __init__(
        self,
        connection: MetaTrader5Connection,
        symbols: Sequence[str] | None = None,
        venue: Venue | None = None,
    ):
        super().__init__()
        self._connection = connection
        self._symbols = list(symbols) if symbols else []
        self._venue = venue or MT5

    async def load_all_async(self, filters: dict | None = None) -> None:
        self._connection.ensure_connected()
        mt5 = self._connection.mt5

        symbols = self._symbols
        if not symbols:
            all_syms = mt5.symbols_get()
            if all_syms:
                symbols = [s.name for s in all_syms if s.visible]

        for sym_name in symbols:
            info = mt5.symbol_info(sym_name)
            if info is None:
                continue

            instrument = self._build_instrument(sym_name, info)
            if instrument:
                self.add(instrument)

    def _build_instrument(self, sym_name: str, info: Any) -> CurrencyPair | None:
        try:
            base_str = info.currency_base.upper()
            quote_str = info.currency_profit.upper()
        except AttributeError:
            return None

        if not base_str or not quote_str:
            return None

        base_ccy = Currency.from_str(base_str)
        quote_ccy = Currency.from_str(quote_str)

        price_precision = info.digits
        size_precision = 2
        price_increment = Price(10 ** -price_precision, price_precision)
        size_increment = Quantity.from_str("0.01")
        lot_size = Quantity(info.trade_contract_size, size_precision)

        instrument_id = InstrumentId(Symbol(sym_name), self._venue)

        return CurrencyPair(
            instrument_id=instrument_id,
            raw_symbol=Symbol(sym_name),
            base_currency=base_ccy,
            quote_currency=quote_ccy,
            price_precision=price_precision,
            size_precision=size_precision,
            price_increment=price_increment,
            size_increment=size_increment,
            lot_size=lot_size,
            max_quantity=None,
            min_quantity=Quantity.from_str("0.01"),
            max_price=None,
            min_price=None,
            margin_init=Money(0, quote_ccy),
            margin_maint=Money(0, quote_ccy),
            maker_fee=Money(0, quote_ccy),
            taker_fee=Money(0, quote_ccy),
            ts_event=0,
            ts_init=0,
        )
