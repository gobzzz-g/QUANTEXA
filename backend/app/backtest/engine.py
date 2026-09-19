import pandas as pd
import numpy as np
from ..indicators.metrics import calc_sharpe, calc_annualized_volatility, calc_drawdown
import math

class BacktestEngine:
    def __init__(self, df: pd.DataFrame, signal: pd.Series, ann_factor: int,
                 initial_capital: float = 10000.0, commission_pct: float = 0.001,
                 slippage_bps: float = 5.0, position_sizing: float = 1.0,
                 risk_free_rate: float = 0.0):
        self.df = df
        self.signal = signal
        self.ann_factor = ann_factor
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_bps / 10000.0
        self.position_sizing = position_sizing
        self.risk_free_rate = risk_free_rate
        
        self.dates = df.index
        n = len(self.dates)
        
        # State arrays
        self.cash_curve = np.zeros(n)
        self.position_curve = np.zeros(n)
        self.equity_curve = np.zeros(n)
        self.trades = []
        
    def run(self):
        if self.df.empty or len(self.df) < 2:
            return {"verdict": "Data too short for backtest.", "trades": []}

        # Benchmark
        # Buy and hold entering at open of first bar
        b_entry_price = self.df['Open'].iloc[0] * (1 + self.commission_pct + self.slippage_pct)
        b_units = self.initial_capital / b_entry_price
        b_cash = self.initial_capital - (b_units * b_entry_price)
        b_equity_series = pd.Series(index=self.dates, data=[b_cash + b_units * self.df['Close'].iloc[i] for i in range(len(self.dates))])
        
        # Strategy
        cash = self.initial_capital
        units = 0.0
        
        current_trade = None
        
        for i in range(len(self.dates)):
            date = self.dates[i]
            open_price = self.df['Open'].iloc[i]
            close_price = self.df['Close'].iloc[i]
            
            # 1. Execute orders from yesterday (i-1)
            if i > 0:
                target_position = self.signal.iloc[i-1]
                
                # If target is valid and differs from current position
                if not np.isnan(target_position):
                    # Enter long
                    if target_position == 1 and units == 0:
                        # We use open_price of day i
                        fill_price = open_price * (1 + self.slippage_pct)
                        equity = cash + (units * open_price)
                        invest_amount = equity * self.position_sizing
                        
                        can_buy = invest_amount / (fill_price * (1 + self.commission_pct))
                        if can_buy > 0:
                            cost = can_buy * fill_price * (1 + self.commission_pct)
                            cash -= cost
                            units += can_buy
                            
                            current_trade = {
                                "entry_date": date.strftime("%Y-%m-%d"),
                                "entry_price": fill_price,
                                "units": can_buy,
                                "fees": cost - (can_buy * fill_price)
                            }
                            
                    # Exit long
                    elif target_position == 0 and units > 0:
                        fill_price = open_price * (1 - self.slippage_pct)
                        revenue = units * fill_price * (1 - self.commission_pct)
                        fee = (units * fill_price) - revenue
                        cash += revenue
                        
                        if current_trade:
                            current_trade["exit_date"] = date.strftime("%Y-%m-%d")
                            current_trade["exit_price"] = fill_price
                            current_trade["fees"] += fee
                            current_trade["pnl"] = revenue - (current_trade["units"] * current_trade["entry_price"]) - current_trade["fees"]
                            self.trades.append(current_trade)
                            current_trade = None
                            
                        units = 0.0
                        
            # 2. Mark to market at close
            equity = cash + (units * close_price)
            self.cash_curve[i] = cash
            self.position_curve[i] = units
            self.equity_curve[i] = equity
            
        strat_equity_series = pd.Series(self.equity_curve, index=self.dates)
        
        # Calculate metrics
        # Calculate metrics
        def metrics(equity_series, trades_list, position_series):
            if len(equity_series) < 2:
                return {"return": 0, "cagr": 0, "sharpe": 0, "sortino": 0, "volatility": 0, "max_drawdown": 0, "calmar": 0, "win_rate": 0, "profit_factor": 0, "trade_count": 0, "exposure": 0, "total_fees": 0}
            
            rets = equity_series.pct_change().dropna()
            total_return = (equity_series.iloc[-1] / equity_series.iloc[0]) - 1
            cagr = (equity_series.iloc[-1] / equity_series.iloc[0]) ** (1 / (len(equity_series) / self.ann_factor)) - 1
            vol = calc_annualized_volatility(rets, self.ann_factor)
            sharpe = calc_sharpe(rets, self.ann_factor, self.risk_free_rate)
            from ..indicators.metrics import calc_sortino, calc_calmar
            sortino = calc_sortino(rets, self.ann_factor, self.risk_free_rate)
            calmar = calc_calmar(equity_series, rets, self.ann_factor)
            _, max_dd = calc_drawdown(equity_series)
            
            wins = sum(1 for t in trades_list if t.get("pnl", 0) > 0)
            trade_count = len([t for t in trades_list if "exit_date" in t])
            win_rate = wins / trade_count if trade_count > 0 else 0
            
            gross_profit = sum(t.get("pnl", 0) for t in trades_list if t.get("pnl", 0) > 0)
            gross_loss = abs(sum(t.get("pnl", 0) for t in trades_list if t.get("pnl", 0) < 0))
            profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.99 if gross_profit > 0 else 0.0)
            
            exposure = (position_series > 0).sum() / len(position_series)
            total_fees = sum(t.get("fees", 0) for t in trades_list)
            
            return {
                "return": float(total_return),
                "cagr": float(cagr),
                "sharpe": float(sharpe),
                "sortino": float(sortino),
                "volatility": float(vol),
                "max_drawdown": float(max_dd),
                "calmar": float(calmar),
                "win_rate": float(win_rate),
                "profit_factor": float(profit_factor),
                "trade_count": int(trade_count),
                "exposure": float(exposure),
                "total_fees": float(total_fees)
            }
            
        s_metrics = metrics(strat_equity_series, self.trades, pd.Series(self.position_curve))
        b_metrics = metrics(b_equity_series, [{"pnl": (b_cash + b_units * self.df['Close'].iloc[-1]) - self.initial_capital, "exit_date": self.dates[-1]}], pd.Series([1]*len(self.dates)))
        
        verdict = f"The strategy returned {(s_metrics['cagr'] - b_metrics['cagr'])*100:.1f} pp compared to Buy-and-Hold, with a max drawdown {(abs(s_metrics['max_drawdown']) - abs(b_metrics['max_drawdown']))*100:.1f} pp different."
            
        return {
            "strategy": s_metrics,
            "benchmark": b_metrics,
            "trades": self.trades,
            "equity_curve": strat_equity_series.to_dict(),
            "benchmark_curve": b_equity_series.to_dict(),
            "verdict": verdict
        }
