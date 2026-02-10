"""
FX instrument factory: builds NautilusTrader CurrencyPair objects
from config/contracts.json definitions.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from nautilus_trader.model.currencies import Currency
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Money, Price, Quantity


def make_fx_pair(
    symbol: str,
    venue: Venue,
    *,
    lot_size: float = 100_000,
    price_precision: int | None = None,
    size_precision: int = 0,
) -> CurrencyPair:
    """
    Build a NautilusTrader CurrencyPair from a 6-char FX symbol like "USDJPY".

    Parameters
    ----------
    symbol : str
        6-character FX pair (e.g. "USDJPY", "EURUSD").
    venue : Venue
        The trading venue.
    lot_size : float
        Contract/lot size (e.g. 100_000 for standard FX lot).
    price_precision : int or None
        Number of decimal places for prices. Auto-detected if None
        (5 for JPY pairs, 5 for others).
    size_precision : int
        Number of decimal places for quantities.
    """
    sym = symbol.upper().replace(".", "").replace(":", "").replace("/", "")
    if len(sym) != 6 or not sym.isalpha():
        raise ValueError(f"Invalid FX symbol: {symbol}")

    base_str = sym[:3]
    quote_str = sym[3:]

    base_ccy = Currency.from_str(base_str)
    quote_ccy = Currency.from_str(quote_str)

    if price_precision is None:
        price_precision = 3 if quote_str == "JPY" else 5

    price_increment = Price(10 ** -price_precision, price_precision)
    size_increment = Quantity(10 ** -size_precision, size_precision)

    instrument_id = InstrumentId(
        Symbol(f"{base_str}/{quote_str}"),
        venue,
    )

    return CurrencyPair(
        instrument_id=instrument_id,
        raw_symbol=Symbol(sym),
        base_currency=base_ccy,
        quote_currency=quote_ccy,
        price_precision=price_precision,
        size_precision=size_precision,
        price_increment=price_increment,
        size_increment=size_increment,
        lot_size=Quantity(lot_size, size_precision),
        max_quantity=None,
        min_quantity=Quantity(1, size_precision),
        max_price=None,
        min_price=None,
        margin_init=Money(0, quote_ccy),
        margin_maint=Money(0, quote_ccy),
        maker_fee=Money(0, quote_ccy),
        taker_fee=Money(0, quote_ccy),
        ts_event=0,
        ts_init=0,
    )


def load_fx_instruments(
    contracts_path: str | Path,
    venue: Venue,
    *,
    price_precision: int | None = None,
    size_precision: int = 0,
) -> Dict[str, CurrencyPair]:
    """
    Load FX instruments from a contracts.json file.

    Returns a dict mapping raw symbol (e.g. "USDJPY") to CurrencyPair.
    """
    path = Path(contracts_path)
    if not path.exists():
        raise FileNotFoundError(f"Contracts config not found: {path}")

    data = json.loads(path.read_text())
    instruments: Dict[str, CurrencyPair] = {}
    for sym, lot_size in data.items():
        key = sym.upper().replace(".", "").replace(":", "")
        instruments[key] = make_fx_pair(
            key,
            venue,
            lot_size=float(lot_size),
            price_precision=price_precision,
            size_precision=size_precision,
        )
    return instruments
