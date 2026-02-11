def fetch_polygon_bars(*args, **kwargs):
    from .polygon_data_fetch import fetch_polygon_bars as _fetch_polygon_bars

    return _fetch_polygon_bars(*args, **kwargs)


def fetch_polygon_bars_chunked(*args, **kwargs):
    from .polygon_data_fetch import (
        fetch_polygon_bars_chunked as _fetch_polygon_bars_chunked,
    )

    return _fetch_polygon_bars_chunked(*args, **kwargs)


def fetch_ibkr_bars(*args, **kwargs):
    from .ibkr_data_fetch import fetch_ibkr_bars as _fetch_ibkr_bars

    return _fetch_ibkr_bars(*args, **kwargs)


__all__ = [
    "fetch_polygon_bars",
    "fetch_polygon_bars_chunked",
    "fetch_ibkr_bars",
]
