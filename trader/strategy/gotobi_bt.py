import backtrader as bt
from datetime import datetime, time, timedelta, date
from trader.exec.router import OrderRequest

class GotobiBT(bt.Strategy):
    """
    A simple strategy that enters +1 unit in the single FX ticker on each "gotobi" day
    at entry_time, and exits at exit_time the same day. No leverage/hedging.

    Gotobi definition:
      - Calendar day with day-of-month in {5,10,15,20,25,30} (some use 31 as well; adjust if needed)
      - If fell on weekend, shift to previous Friday.
      - Apply holiday filter: if shifted day is a holiday/non-settlement day, roll backward day-by-day until a business day.

    Assumptions:
      - You add ONE data feed (data0) for the FX pair to trade.
      - All bars share the same timezone; entry/exit compare against bar timestamp as-is.
      - Bar size should be fine enough to hit the specified times exactly.

    Parameters:
      entry_time (HH:MM:SS)
      exit_time  (HH:MM:SS)
      use_holidays: try to use the `holidays` package for JP. If not installed, falls back to p.notrade_days set.
      notrade_days: optional set of date objects to treat as holidays/non-settlement days (e.g., custom JPY settlement holidays).
      gotobi_days: which DOM values to treat as gotobi (default {5,10,15,20,25,30})
    """

    params = dict(
        entry_time="01:30:00",
        exit_time="08:30:00",
        use_holidays=True,
        notrade_days=None,          # set({date(2024,1,1), ...}) if you have your own list
        gotobi_days=(5, 10, 15, 20, 25, 30),
        trade_size=1.0,             # +1 unit by default
        router=None,                # optional OrderRouter for live dispatch
    )

    def __init__(self):
        # Parse times
        self.t_entry = self._parse_time(self.p.entry_time)
        self.t_exit  = self._parse_time(self.p.exit_time)

        # Day state
        self.current_day = None
        self.entered_today = False
        self.target_trade_date = None  # today's gotobi trading date after adjustments
        self.holiday_checker = self._build_holiday_checker()

    # ---------------- Helpers ----------------
    @staticmethod
    def _parse_time(tstr: str) -> time:
        hh, mm, ss = map(int, tstr.split(":"))
        return time(hh, mm, ss)

    def _cur_dt(self):
        return self.data.datetime.datetime(0)

    def _cur_date(self) -> date:
        dt = self._cur_dt()
        return date(dt.year, dt.month, dt.day)

    def _is_weekend(self, d: date) -> bool:
        return d.weekday() >= 5  # 5=Sat, 6=Sun

    def _prev_business_day(self, d: date) -> date:
        """ Roll backward to previous non-weekend, non-holiday date. """
        cur = d
        while self._is_weekend(cur) or self.holiday_checker(cur):
            cur = cur - timedelta(days=1)
        return cur

    def _weekend_to_prev_friday(self, d: date) -> date:
        """ If weekend, move to previous Friday; else return same date. """
        if d.weekday() == 5:      # Saturday -> Friday
            return d - timedelta(days=1)
        if d.weekday() == 6:      # Sunday -> Friday
            return d - timedelta(days=2)
        return d

    def _gotobi_base(self, d: date) -> bool:
        """ Is day-of-month in configured gotobi set? """
        return d.day in set(self.p.gotobi_days)

    def _resolve_gotobi_trading_date(self, d: date) -> date | None:
        """
        From a calendar date d, if it's a gotobi day:
          - shift if weekend to previous Friday,
          - then roll backward across holidays until business day.
        Returns the trading date for gotobi, else None if d isn't a gotobi base date.
        """
        if not self._gotobi_base(d):
            return None
        shifted = self._weekend_to_prev_friday(d)
        resolved = self._prev_business_day(shifted)
        return resolved

    def _build_holiday_checker(self):
        """
        Returns a callable h(d: date) -> bool that says if d is holiday/notrade.
        Priority:
          1) If use_holidays and `holidays` pkg available => use JP holidays.
          2) Else use self.p.notrade_days set if given.
          3) Else no holidays.
        NOTE: Official FX settlement holidays can differ from national holidays. If you have
        a canonical list (e.g., CLS/JPY settlement holidays), pass via `notrade_days`.
        """
        # User-provided set wins if use_holidays=False or import fails
        if not self.p.use_holidays and self.p.notrade_days is not None:
            notrade = set(self.p.notrade_days)
            return lambda d: d in notrade

        try:
            import holidays  # type: ignore
            jp_holidays = holidays.country_holidays("JP")
            # If user also provided extra non-settlement days, union them
            extra = set(self.p.notrade_days) if self.p.notrade_days else set()
            return lambda d: (d in jp_holidays) or (d in extra)
        except Exception:
            # Fallback: just use the provided set, or no holidays
            notrade = set(self.p.notrade_days) if self.p.notrade_days else set()
            return lambda d: d in notrade

    def _send_router_order(self, side: str, size: float, *, order_type: str = "market", price: float | None = None):
        """
        Mirror the simulated order to a live router if provided.
        """
        router = getattr(self.p, "router", None)
        if router is None or size == 0:
            return
        try:
            router.send(
                OrderRequest(
                    symbol=self.data._name,
                    side=side,
                    size=float(abs(size)),
                    order_type=order_type,
                    price=price,
                ),
                last_price=float(self.data.close[0]) if price is None else None,
            )
        except Exception as exc:
            print(f"[{self._cur_dt()}] ROUTER ERROR {exc}")

    # ---------------- Strategy loop ----------------
    def next(self):
        now_dt = self._cur_dt()
        now_d  = self._cur_date()
        now_t  = now_dt.time()

        # New trading day on this data feed
        if self.current_day is None or now_d != self.current_day:
            self.current_day = now_d
            self.entered_today = False
            # Compute today's "gotobi trading date" (if any) using calendar rules
            self.target_trade_date = self._resolve_gotobi_trading_date(now_d)

        # If today isn't a gotobi trading date, do nothing
        if self.target_trade_date != now_d:
            # But ensure we exit if holding from any edge case (shouldn't happen with same-day exit)
            if now_t == self.t_exit and self.position.size != 0:
                qty = self.position.size
                self.close()
                side = "SELL" if qty > 0 else "BUY"
                self._send_router_order(side, qty)
            return

        # Entry at entry_time (only once)
        if (not self.entered_today) and (now_t == self.t_entry):
            # Enter +1 unit
            if self.p.trade_size > 0:
                self.buy(size=self.p.trade_size)
                self._send_router_order("BUY", self.p.trade_size)
            else:
                self.sell(size=-self.p.trade_size)
                self._send_router_order("SELL", -self.p.trade_size)
            self.entered_today = True

        # Exit at exit_time (same day)
        if self.entered_today and now_t == self.t_exit and self.position.size != 0:
            qty = self.position.size
            self.close()
            side = "SELL" if qty > 0 else "BUY"
            self._send_router_order(side, qty)

    # ---------------- Notifications (optional logs) ----------------
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        dt = self._cur_dt()
        if order.status in [order.Completed]:
            side = "BUY" if order.isbuy() else "SELL"
            print(f"[{dt}] ORDER {side} {order.data._name} size={order.size} px={order.executed.price}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            print(f"[{dt}] ORDER {order.getstatusname()} {order.data._name}")

    def notify_trade(self, trade):
        if trade.isclosed:
            dt = self._cur_dt()
            print(f"[{dt}] TRADE {trade.data._name} PnL gross={trade.pnl:.2f} net={trade.pnlcomm:.2f}")

class GotobiBTWithSL(bt.Strategy):
    params = dict(
        entry_time="01:30:00",
        exit_time="08:30:00",
        use_holidays=True,
        notrade_days=None,                 # set({date(YYYY, M, D), ...}) if you have a custom list
        gotobi_days=(5, 10, 15, 20, 25, 30),
        trade_size=1.0,                    # sign matters: >0 long, <0 short
        stop_loss_pct=None,                # e.g. 0.003 for 0.3% stop; None disables
        router=None,                       # optional OrderRouter for live dispatch
    )

    def __init__(self):
        self.t_entry = self._t(self.p.entry_time)
        self.t_exit  = self._t(self.p.exit_time)
        self.current_day = None
        self.target_trade_date = None
        self.entered_today = False

        self.entry_order = None
        self.stop_order  = None

        self._stop_filled_flag = False
        self._stop_fill_px = None

        self.holiday = self._build_holiday_checker()

    # -------- utils --------
    @staticmethod
    def _t(s):
        h, m, sec = map(int, s.split(":"))
        return (h, m, sec)  # tuple compare is fine

    def _time_tuple(self):
        dt = self.data.datetime.datetime(0)
        return (dt.hour, dt.minute, dt.second)

    def _today(self):
        dt = self.data.datetime.datetime(0)
        return date(dt.year, dt.month, dt.day)

    def _is_weekend(self, d): return d.weekday() >= 5
    def _weekend_to_prev_friday(self, d):
        return d - timedelta(days=1) if d.weekday()==5 else (d - timedelta(days=2) if d.weekday()==6 else d)

    def _prev_business_day(self, d):
        cur = d
        while self._is_weekend(cur) or self.holiday(cur):
            cur -= timedelta(days=1)
        return cur

    def _resolve_gotobi_trading_date(self, d):
        if d.day not in set(self.p.gotobi_days):
            return None
        return self._prev_business_day(self._weekend_to_prev_friday(d))

    def _build_holiday_checker(self):
        if not self.p.use_holidays and self.p.notrade_days is not None:
            s = set(self.p.notrade_days)
            return lambda d: d in s
        try:
            import holidays # type: ignore
            jp = holidays.country_holidays("JP")
            extra = set(self.p.notrade_days) if self.p.notrade_days else set()
            return lambda d: (d in jp) or (d in extra)
        except Exception:
            s = set(self.p.notrade_days) if self.p.notrade_days else set()
            return lambda d: d in s

    def _send_router_order(self, side: str, size: float, *, order_type: str = "market", price: float | None = None):
        router = getattr(self.p, "router", None)
        if router is None or size == 0:
            return
        try:
            router.send(
                OrderRequest(
                    symbol=self.data._name,
                    side=side,
                    size=float(abs(size)),
                    order_type=order_type,
                    price=price,
                ),
                last_price=float(self.data.close[0]) if price is None else None,
            )
        except Exception as exc:
            dt = self.data.datetime.datetime(0)
            print(f"[{dt}] ROUTER ERROR {exc}")

    # -------- core --------
    def next(self):
        now_d = self._today()
        now_t = self._time_tuple()

        if self.current_day is None or now_d != self.current_day:
            self.current_day = now_d
            self.entered_today = False
            self.entry_order = None
            self.stop_order  = None
            self.target_trade_date = self._resolve_gotobi_trading_date(now_d)

        # not a gotobi trading date → only make sure we’re flat at exit (defensive)
        if self.target_trade_date != now_d:
            if now_t == self.t_exit and self.position.size != 0:
                self._cancel_stop()
                self.close()
            return

        # entry once
        if (not self.entered_today) and now_t == self.t_entry and self.entry_order is None:
            sz = float(self.p.trade_size)
            if sz == 0:
                return
            if sz > 0:
                self.entry_order = self.buy(size=abs(sz))
                self._send_router_order("BUY", abs(sz))
            else:
                self.entry_order = self.sell(size=abs(sz))
                self._send_router_order("SELL", abs(sz))

        # scheduled time exit (if still in position)
        if now_t == self.t_exit:
            self._cancel_stop()
            if self.position.size != 0:
                qty = self.position.size
                side = "SELL" if qty > 0 else "BUY"
                self.close()
                self._send_router_order(side, abs(qty))
            self.entry_order = None
            self.entered_today = False  # allow next day

    def _cancel_stop(self):
        if self.stop_order and self.stop_order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            try:
                self.cancel(self.stop_order)
            except Exception:
                pass
        self.stop_order = None

    # -------- order/trade notifications --------
    def notify_order(self, order):
        dt = self.data.datetime.datetime(0)

        # Ignore just-submitted
        if order.status in [order.Submitted, order.Accepted]:
            return

        # --- ENTRY handling ---
        if order is self.entry_order:
            if order.status == bt.Order.Completed:
                self.entered_today = True
                side = "BUY" if order.isbuy() else "SELL"
                print(f"[{dt}] ENTRY {side} {order.data._name} size={order.size} px={order.executed.price}")

                # place stop if enabled
                if self.p.stop_loss_pct and self.p.stop_loss_pct > 0 and self.position.size != 0:
                    px = order.executed.price
                    if self.position.size > 0:
                        stop_px = px * (1.0 - self.p.stop_loss_pct)
                        self.stop_order = self.sell(exectype=bt.Order.Stop, price=stop_px, size=abs(self.position.size))
                        print(f"[{dt}] STOP SELL placed at {stop_px:.5f}")
                        self._send_router_order("SELL", abs(self.position.size), order_type="stop", price=stop_px)
                    else:
                        stop_px = px * (1.0 + self.p.stop_loss_pct)
                        self.stop_order = self.buy(exectype=bt.Order.Stop, price=stop_px, size=abs(self.position.size))
                        print(f"[{dt}] STOP BUY placed at {stop_px:.5f}")
                        self._send_router_order("BUY", abs(self.position.size), order_type="stop", price=stop_px)
            elif order.status in [bt.Order.Canceled, bt.Order.Margin, bt.Order.Rejected]:
                print(f"[{dt}] ENTRY {order.getstatusname()} {order.data._name}")
                self.entry_order = None

        # --- STOP handling ---
        if order is self.stop_order:
            if order.status == bt.Order.Completed:
                side = "STOP BUY" if order.isbuy() else "STOP SELL"
                self._stop_filled_flag = True
                self._stop_fill_px = order.executed.price
                print(f"[{dt}] STOP FILLED {side} {order.data._name} px={order.executed.price}")
                # clear refs
                self.entry_order = None
                self.stop_order = None
            elif order.status in [bt.Order.Canceled, bt.Order.Margin, bt.Order.Rejected]:
                print(f"[{dt}] STOP {order.getstatusname()} {order.data._name}")
                self.stop_order = None

    def notify_trade(self, trade):
        # Fires when a TRADE closes (position back to 0)
        if trade.isclosed:
            dt = self.data.datetime.datetime(0)
            tag = "STOP-OUT" if self._stop_filled_flag else "TIME-EXIT"
            print(
                f"[{dt}] TRADE {tag} {trade.data._name} "
                f"entry_px={trade.price} "
                f"closed_px={self._stop_fill_px if self._stop_filled_flag else 'N/A'} "
                f"size={trade.size} "
                f"PnL gross={trade.pnl:.5f} net={trade.pnlcomm:.5f}"
            )
            # reset for next trade
            self._stop_filled_flag = False
            self._stop_fill_px = None
