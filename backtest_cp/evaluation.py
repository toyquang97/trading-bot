# evaluation.py (patched - robust to missing or differently-named pnl columns)
from init import *
import numpy as np
import pandas as pd
 
def _get_net_pnl_series(trades: pd.DataFrame) -> pd.Series:
    """
    Try to extract a numeric series representing net PnL from trades DataFrame.
    Supports multiple possible column names. If nothing found, returns empty Series.
    """
    if trades is None or len(trades) == 0:
        return pd.Series(dtype=float)
 
    candidates = ['net_pnl', 'pnl', 'profit', 'profit_usd', 'pl']
    for c in candidates:
        if c in trades.columns:
            # coerce to numeric, dropna
            try:
                s = pd.to_numeric(trades[c], errors='coerce').dropna()
                return s
            except Exception:
                continue
 
    # If none of the common columns exist, but DataFrame has any numeric column, try the first numeric column
    numeric_cols = trades.select_dtypes(include=[np.number]).columns.tolist()
    if numeric_cols:
        s = pd.to_numeric(trades[numeric_cols[0]], errors='coerce').dropna()
        return s
 
    # fallback: empty series
    return pd.Series(dtype=float)
 
def calculate_performance_metrics(equity_curve: pd.Series, trades: pd.DataFrame, annual_days=365):
    """
    Tính toán các chỉ số hiệu suất giao dịch (robust).
    - equity_curve: Series vốn theo thời gian (index DatetimeIndex).
    - trades: DataFrame chứa các giao dịch đã đóng (có thể rỗng hoặc thiếu cột 'net_pnl').
    - annual_days: số ngày 1 năm (crypto thường dùng 365).
    """
    # SAFE checks
    if equity_curve is None or equity_curve.empty:
        return {}
 
    # ensure index is DatetimeIndex for accurate timing
    if not isinstance(equity_curve.index, pd.DatetimeIndex):
        try:
            equity_curve.index = pd.to_datetime(equity_curve.index)
        except Exception:
            raise TypeError("equity_curve index must be DatetimeIndex or convertible to datetime for CAGR/Volatility calc.")
 
    # Basic returns
    initial_capital = float(equity_curve.iloc[0])
    final_equity = float(equity_curve.iloc[-1])
    total_return = (final_equity / initial_capital) - 1 if initial_capital != 0 else np.nan
 
    # Time span in days and num_years
    time_span_days = (equity_curve.index[-1] - equity_curve.index[0]).total_seconds() / (3600 * 24)
    num_years = time_span_days / annual_days if annual_days > 0 else 0
    cagr = (final_equity / initial_capital) ** (1 / num_years) - 1 if (num_years > 0 and initial_capital > 0) else 0.0
 
    # Max Drawdown
    peak = equity_curve.expanding(min_periods=1).max()
    drawdown = (equity_curve / peak) - 1
    mdd = drawdown.min() if not drawdown.empty else 0.0
 
    # Returns series for volatility etc.
    returns = equity_curve.pct_change().dropna()
    # Compute bars_per_year using first two timestamps if possible (robust)
    if len(equity_curve.index) >= 2:
        time_diff = (equity_curve.index[1] - equity_curve.index[0])
        seconds_in_year = annual_days * 24 * 60 * 60
        try:
            bars_per_year = seconds_in_year / time_diff.total_seconds()
            annualization_factor = np.sqrt(bars_per_year)
        except Exception:
            annualization_factor = np.sqrt(252)  # fallback
    else:
        annualization_factor = np.sqrt(252)
 
    annual_volatility = returns.std() * annualization_factor if not returns.empty else 0.0
    sharpe_ratio = (cagr - 0) / annual_volatility if annual_volatility != 0 else np.nan
 
    # Sortino
    downside_returns = returns[returns < 0] if not returns.empty else returns
    downside_deviation = downside_returns.std() * annualization_factor if not downside_returns.empty else 0.0
    sortino_ratio = (cagr - 0) / downside_deviation if downside_deviation != 0 else np.nan
 
    # Trades analysis (robust to missing net_pnl)
    net_pnl_series = _get_net_pnl_series(trades)
    total_trades = len(net_pnl_series) if net_pnl_series is not None else 0
 
    if total_trades > 0:
        winning_trades = net_pnl_series[net_pnl_series > 0]
        losing_trades = net_pnl_series[net_pnl_series < 0]
        num_winning_trades = len(winning_trades)
        num_losing_trades = len(losing_trades)
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0.0
        avg_profit_per_trade = net_pnl_series.mean()
        avg_win_profit = winning_trades.mean() if len(winning_trades) > 0 else 0.0
        avg_loss_profit = losing_trades.mean() if len(losing_trades) > 0 else 0.0
        profit_factor = (winning_trades.sum() / abs(losing_trades.sum())) if (len(losing_trades) > 0 and abs(losing_trades.sum()) > 0) else np.nan
    else:
        # fallback values when no trade PnL data exists
        win_rate = 0.0
        avg_profit_per_trade = 0.0
        avg_win_profit = 0.0
        avg_loss_profit = 0.0
        profit_factor = np.nan
 
    metrics = {
        'Tổng Lợi Nhuận Gộp (USD)': f"{final_equity - initial_capital:.2f}",
        'Lợi nhuận Hàng năm (CAGR)': f"{cagr * 100:.2f}%",
        'Max Drawdown (MDD)': f"{mdd * 100:.2f}%",
        '--- Chỉ số Rủi ro & Lợi nhuận ---': '---',
        'Sharpe Ratio': f"{sharpe_ratio:.2f}" if not np.isnan(sharpe_ratio) else 'nan',
        'Sortino Ratio': f"{sortino_ratio:.2f}" if not np.isnan(sortino_ratio) else 'nan',
        'Độ Biến động Hàng năm': f"{annual_volatility * 100:.2f}%",
        '--- Phân tích Giao dịch ---': '---',
        'Tổng số Giao dịch': total_trades,
        'Tỷ lệ Thắng (Win Rate)': f"{win_rate * 100:.2f}%",
        'Số lệnh Thắng (Win)': num_winning_trades,
        'Số lệnh Thua (Loss)': num_losing_trades,
        'Lợi nhuận TB mỗi Giao dịch': f"{avg_profit_per_trade:.2f} USD",
        'Lợi nhuận TB Lệnh Thắng': f"{avg_win_profit:.2f} USD",
        'Thua Lỗ TB Lệnh Thua': f"{avg_loss_profit:.2f} USD",
        'Profit Factor': f"{profit_factor:.2f}" if not pd.isna(profit_factor) else 'nan',
    }
 
    return metrics