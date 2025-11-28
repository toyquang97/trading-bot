# engine.py (patched - robust column access, slippage, risk_pct to size conversion)
from init import *   # giữ imports chung (pandas/numpy if defined). Nếu không, uncomment imports below.
# import pandas as pd
# import numpy as np
 
"""
BacktestEngine (patched)
- Robust column access: accepts 'Close' / 'close' / 'CLOSE' etc.
- Helper _val to read series values safely (case-insensitive)
- Slippage support: slippage_pct, slippage_ticks, tick_size
- Accepts signals_df where signals can specify 'size' or 'risk_pct' (engine computes size from capital)
- Keeps original semantics for trades/equity output.
"""
 
def _val(series: pd.Series, *names, default=np.nan):
    """
    Return first existing key value from names in series (case-insensitive attempts).
    names: candidate keys like 'Close', 'close', 'Close'
    If none found, return default.
    """
    for n in names:
        if n in series.index:
            return series[n]
        # try lowercase
        nl = n.lower()
        if nl in series.index:
            return series[nl]
        nc = n.capitalize()
        if nc in series.index:
            return series[nc]
        nu = n.upper()
        if nu in series.index:
            return series[nu]
    return default
 
def _to_float_safe(x, default=np.nan):
    try:
        return float(x)
    except Exception:
        return default
 
class BacktestEngine:
    def __init__(self, initial_capital=100000.0, fee_rate=0.00075,
                 slippage_pct=0.0, slippage_ticks=0.0, tick_size=0.0,
                 leverage: float = 1.0):                # <-- added
        self.initial_capital = float(initial_capital)
        self.capital = float(initial_capital)
        self.fee_rate = float(fee_rate)
        self.position = 0.0
        self.entry_price = 0.0
        self.trades = []
        self.equity_curve = pd.Series(dtype=float)
        self.pending_exit = {}
        self.output_data = None

        # slippage params
        self.slippage_pct = float(slippage_pct)
        self.slippage_ticks = float(slippage_ticks)
        self.tick_size = float(tick_size)

        # leverage (new)
        self.leverage = float(leverage) if leverage and leverage > 0 else 1.0
 
    def _update_output_row(self, current_bar, entry_price=np.nan, tp_price=np.nan, sl_price=np.nan, pnl_pct=np.nan):
        """
        Write entry/tp/sl/pnl_pct into self.output_data at the timestamp of current_bar.
        - This will ONLY write non-NaN values so it won't erase previously written values.
        """
        ts = current_bar.name
        try:
            if not pd.isna(entry_price):
                self.output_data.at[ts, 'entry_price'] = float(entry_price)
            # Only write tp/sl if value is provided and not NaN (do not overwrite)
            if not pd.isna(tp_price):
                self.output_data.at[ts, 'tp_price'] = float(tp_price)
            if not pd.isna(sl_price):
                self.output_data.at[ts, 'sl_price'] = float(sl_price)
            if not pd.isna(pnl_pct):
                self.output_data.at[ts, 'pnl_pct'] = float(pnl_pct)
        except Exception:
            # silent fail (avoid breaking backtest)
            pass
 
 
 
    def _apply_slippage(self, price: float, side: str) -> float:
        """
        Apply slippage against the trader:
        - slippage_pct increases BUY price, decreases SELL price.
        - slippage_ticks moves price by tick_size against trader.
        """
        p = price
        if p is None or np.isnan(p):
            return p
        # percent slippage
        if self.slippage_pct:
            if side == 'BUY':
                p = p * (1.0 + abs(self.slippage_pct))
            else:
                p = p * (1.0 - abs(self.slippage_pct))
        # tick slippage
        if self.slippage_ticks and self.tick_size:
            move = abs(self.slippage_ticks) * abs(self.tick_size)
            if side == 'BUY':
                p = p + move
            else:
                p = p - move
        return p
 
    def _execute_order(self, current_bar, order, exit_type='TRADE'):
        # get execution price robustly
        execution_price = _to_float_safe(_val(current_bar, 'Close', 'close'))
        if np.isnan(execution_price):
            return
 
        # apply slippage
        execution_price = self._apply_slippage(execution_price, order.get('side','BUY'))
 
        trade_size = order.get('size', None)
        if trade_size is None:
            return
        trade_size = float(trade_size)
        fee = trade_size * execution_price * self.fee_rate
 
        side = order.get('side','').upper()
 
        # ----- BUY: open long or close short -----
        if side == 'BUY':
            if self.position == 0:
                self.entry_timestamp = current_bar.name
                # Open Long
                self.position = trade_size
                self.entry_price = execution_price
                # pay cash to buy
                self.capital -= trade_size * execution_price + fee
                # write entry + tp/sl
                tp_val = self.pending_exit.get('tp', np.nan) if isinstance(self.pending_exit, dict) else np.nan
                sl_val = self.pending_exit.get('sl', np.nan) if isinstance(self.pending_exit, dict) else np.nan
                self._update_output_row(current_bar, entry_price=execution_price, tp_price=tp_val, sl_price=sl_val)
                # record entry in output
                # self._update_output_row(current_bar, entry_price=execution_price)
                # pending_exit maybe set by signal
            elif self.position < 0:
                # Close Short (buy to cover)
                size_to_close = min(abs(self.position), trade_size)
                # pay to buy back
                self.capital -= size_to_close * execution_price + fee
                #     # write entry + tp/sl
                # realized pnl for logging: entry - exit
                pnl = (self.entry_price - execution_price) * size_to_close
                pnl_net = pnl - fee
                self.trades.append({
                'entry_time': self.entry_timestamp,            # timestamp entry
                'exit_time': current_bar.name,                 # timestamp exit
                'entry_price': float(self.entry_price),
                'exit_price': float(execution_price),
                'size': float(size_to_close),
                'gross_pnl': float(pnl),                       # BEFORE fee
                'net_pnl': float(pnl_net),                     # AFTER fee
                'direction': 'LONG' if self.position > 0 else 'SHORT'
                })
                # reduce position magnitude
                self.position += size_to_close
                if abs(self.position) < 1e-9:
                    self.position = 0.0
                    self.entry_price = 0.0
                    self.pending_exit = {}
                # update output row (tp / pnl pct)
                self._update_output_row(current_bar, tp_price=execution_price, pnl_pct=(pnl/execution_price*100 if execution_price!=0 else np.nan))
 
    # ----- SELL: open short or close long -----
        elif side == 'SELL':
            if self.position == 0:
                self.entry_timestamp = current_bar.name
                # Open Short
                self.position = -trade_size
                self.entry_price = execution_price
                self.capital += trade_size * execution_price - fee
 
                # pending_exit expected to be set from signal before execution; collect tp/sl
                tp_val = self.pending_exit.get('tp', np.nan) if isinstance(self.pending_exit, dict) else np.nan
                sl_val = self.pending_exit.get('sl', np.nan) if isinstance(self.pending_exit, dict) else np.nan
                # write entry row with tp/sl (do not overwrite later unless explicit)
                self._update_output_row(current_bar, entry_price=execution_price, tp_price=tp_val, sl_price=sl_val)
 
            elif self.position > 0:
                # Close Long
                size_to_close = min(self.position, trade_size)
                # receive proceeds from selling
                self.capital += size_to_close * execution_price - fee
                pnl = (execution_price - self.entry_price) * size_to_close
                pnl_net = pnl - fee
                self.trades.append({
                'entry_time': self.entry_timestamp,            # timestamp entry
                'exit_time': current_bar.name,                 # timestamp exit
                'entry_price': float(self.entry_price),
                'exit_price': float(execution_price),
                'size': float(size_to_close),
                'gross_pnl': float(pnl),                       # BEFORE fee
                'net_pnl': float(pnl_net),                     # AFTER fee
                'direction': 'LONG' if self.position > 0 else 'SHORT'
                })
                self.position -= size_to_close
                if abs(self.position) < 1e-9:
                    self.position = 0.0
                    self.entry_price = 0.0
                    self.pending_exit = {}
                self._update_output_row(current_bar, tp_price=execution_price, pnl_pct=(pnl/self.entry_price*100 if self.entry_price else np.nan))
 
        else:
            # unknown side
            return
 
    def run_backtest(self, data_1m, signals_df=None, prefer_risk_pct=True, progress=True):
        """
        Replay 1m bars and execute precomputed signals.
 
        - data_1m: DataFrame indexed by DatetimeIndex (1-minute)
        - signals_df: DataFrame indexed by timestamps (subset of data_1m.index) with columns:
            'signal_side' (BUY/SELL), optional 'size', optional 'risk_pct', optional 'tp_price', 'sl_price'
        - prefer_risk_pct: if True and a signal provides 'risk_pct', engine converts to absolute size using current capital
        - progress: whether to print progress updates
 
        Returns:
        (output_data DataFrame, trades_df DataFrame)
        """
        # Prepare output_data copy and ensure expected columns exist
        self.output_data = data_1m.copy()
        # new_cols = ['entry_price', 'tp_price', 'pnl_pct', 'equity', 'position_side']
        new_cols = ['entry_price', 'tp_price', 'sl_price', 'pnl_pct', 'equity', 'position_side']
        for col in new_cols:
            if col not in self.output_data.columns:
                self.output_data[col] = np.nan
        # ensure position_side is object dtype so we can write strings
        try:
            self.output_data['position_side'] = self.output_data['position_side'].astype(object)
        except Exception:
            self.output_data['position_side'] = pd.Series(index=self.output_data.index, dtype=object)
 
        total_bars = len(data_1m)
        progress_increment = max(total_bars // 10, 1)
        next_progress_mark = progress_increment
        current_bar_count = 0
 
        # Main loop
        for index, bar in data_1m.iterrows():
            # ---------- 1) Compute equity = capital + position * price ----------
            current_price = _to_float_safe(_val(bar, 'Close', 'close'))
            position_value = 0.0
            if not np.isnan(current_price):
                position_value = float(self.position) * current_price  # negative if short
 
            try:
                current_equity = float(self.capital) + position_value
            except Exception:
                current_equity = np.nan
 
            # write equity and position_side
            try:
                self.equity_curve.at[index] = current_equity
                self.output_data.at[index, 'equity'] = current_equity
            except Exception:
                pass
 
            side_label = np.nan
            if self.position > 0:
                side_label = 'Long'
            elif self.position < 0:
                side_label = 'Short'
            try:
                self.output_data.at[index, 'position_side'] = side_label
            except Exception:
                pass
 
            # optional: unrealized pnl pct for display
            try:
                if self.position != 0 and not np.isnan(current_price) and self.entry_price:
                    if self.position > 0:
                        unrealized_pnl_pct = (current_price / self.entry_price - 1) * 100
                    else:
                        unrealized_pnl_pct = (self.entry_price / current_price - 1) * 100
                    self.output_data.at[index, 'pnl_pct'] = round(unrealized_pnl_pct, 2)
            except Exception:
                pass
 
            # ---------- 2) Check engine-level TP/SL ----------
            position_closed_by_exit = False
            low = _to_float_safe(_val(bar, 'Low', 'low'))
            high = _to_float_safe(_val(bar, 'High', 'high'))
 
            if self.position > 0 and self.pending_exit:
                sl = self.pending_exit.get('sl', np.nan)
                tp = self.pending_exit.get('tp', np.nan)
                if not np.isnan(sl) and not np.isnan(low) and low < sl:
                    self._execute_order(bar, {'side': 'SELL', 'size': abs(self.position)}, exit_type='SL')
                    position_closed_by_exit = True
                elif not np.isnan(tp) and not np.isnan(high) and high > tp:
                    self._execute_order(bar, {'side': 'SELL', 'size': abs(self.position)}, exit_type='TP')
                    position_closed_by_exit = True
 
            elif self.position < 0 and self.pending_exit:
                sl = self.pending_exit.get('sl', np.nan)
                tp = self.pending_exit.get('tp', np.nan)
                if not np.isnan(sl) and not np.isnan(high) and high > sl:
                    self._execute_order(bar, {'side': 'BUY', 'size': abs(self.position)}, exit_type='SL')
                    position_closed_by_exit = True
                elif not np.isnan(tp) and not np.isnan(low) and low < tp:
                    self._execute_order(bar, {'side': 'BUY', 'size': abs(self.position)}, exit_type='TP')
                    position_closed_by_exit = True
 
            # ---------- 3) Execute signal at this timestamp (if any) ----------
            if (not position_closed_by_exit) and (signals_df is not None) and (index in signals_df.index):
                sig = signals_df.loc[index]
                side_sig = sig.get('signal_side', np.nan)
                if pd.notna(side_sig):
                    # determine execution size: prefer risk_pct -> size -> fallback 1.0
                    size = None
                    exec_price_est = current_price if not np.isnan(current_price) else _to_float_safe(_val(bar, 'Open', 'open'))
                    # --- HANDLE risk_pct properly ---
                    if prefer_risk_pct and (not pd.isna(sig.get('risk_pct'))):
                        try:
                            risk_pct_raw = float(sig.get('risk_pct'))
                            # Normalize exec price
                            if exec_price_est is None or np.isnan(exec_price_est) or exec_price_est == 0:
                                # cannot compute size without price, fallback later
                                size = None
                            else:
                                # If signal provides SL, treat risk_pct as fraction of capital to RISK (money to lose)
                                sl_sig = sig.get('sl_price', None)
                                if sl_sig is not None and not pd.isna(sl_sig):
                                    try:
                                        sl_price = float(sl_sig)
                                        entry_est = exec_price_est
                                        sl_distance = abs(entry_est - sl_price)
                                        if sl_distance > 0:
                                            # risk_pct interpreted as fraction of capital to risk (0.01 = 1% of capital)
                                            # If risk_pct_raw > 1, interpret as absolute fraction (e.g., 3 -> 300%) -> clamp or accept per user
                                            risk_money = self.capital * (risk_pct_raw if risk_pct_raw <= 1 else (risk_pct_raw))
                                            size = risk_money / sl_distance
                                        else:
                                            size = None
                                    except Exception:
                                        size = None
                                else:
                                    # No SL provided: interpret risk_pct as exposure fraction (fraction of capital)
                                    # If risk_pct_raw > 1, treat as exposure multiplier (e.g., 3 -> 3x capital exposure)
                                    if risk_pct_raw > 1.0:
                                        desired_exposure = self.capital * float(risk_pct_raw)
                                    else:
                                        desired_exposure = self.capital * float(risk_pct_raw) * self.leverage
                                    size = desired_exposure / exec_price_est

                        except Exception:
                            size = None

                    # If risk_pct path didn't give a size, try explicit size field
                    if size is None and (not pd.isna(sig.get('size'))):
                        try:
                            size = float(sig.get('size'))
                        except Exception:
                            size = None

                    # Fallback default size
                    if size is None:
                        size = 1.0

                    # Enforce a maximum size based on available capital * leverage (safety cap)
                    try:
                        max_exposure = (self.capital * self.leverage)
                        max_size = max_exposure / exec_price_est if exec_price_est and exec_price_est > 0 else None
                        if max_size is not None and size > max_size:
                            size = max_size
                    except Exception:
                        pass

 
                    order = {'side': str(side_sig).upper(), 'size': size}
 
                    # set pending TP/SL from signal if provided (override engine defaults)
                    tp_sig = sig.get('tp_price', None)
                    sl_sig = sig.get('sl_price', None)
                    if not pd.isna(tp_sig):
                        try:
                            self.pending_exit['tp'] = float(tp_sig)
                        except Exception:
                            pass
                    if not pd.isna(sl_sig):
                        try:
                            self.pending_exit['sl'] = float(sl_sig)
                        except Exception:
                            pass
 
                    # execute order (this should update self.position and self.capital via _execute_order)
                    self._execute_order(bar, order)
 
            # ---------- 4) Progress print ----------
            current_bar_count += 1
            if progress and current_bar_count >= next_progress_mark:
                percent_complete = (current_bar_count / total_bars) * 100
                print(f"⌛ Tiến độ Backtest: {percent_complete:.0f}% hoàn thành ({current_bar_count}/{total_bars} bars)")
                next_progress_mark += progress_increment
 
        # done loop
        print(f"✅ Tiến độ Backtest: 100% hoàn thành ({total_bars}/{total_bars} bars)")
 
        # convert trades log to DataFrame and return
        try:
            cols = ['entry_time','exit_time','entry_price','exit_price','size','gross_pnl','net_pnl','direction']
            trades_df = trades_df.reindex(columns=cols)
            trades_df = pd.DataFrame(self.trades)
        except Exception:
            trades_df = pd.DataFrame(self.trades if isinstance(self.trades, list) else [])
        return self.output_data, trades_df
 
 
 
 