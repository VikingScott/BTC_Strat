import pandas as pd
import numpy as np

class BuyAndHoldStrategy:
    """
    基准策略：第一天全仓买入 IBIT (或 BTC)，之后一直持有。
    忽略任何 Regime 信号。
    """
    def __init__(self, initial_capital=100_000):
        self.initial_capital = initial_capital
        self.name = "Buy & Hold"

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        执行策略。
        
        Args:
            df: 包含 'date' 和 'price' (IBIT Spot) 的 DataFrame
            
        Returns:
            包含每日净值和持仓细节的 DataFrame
        """
        print(f"   🏃 Running Strategy: {self.name}...")
        
        # 1. 初始化结果表
        results = df[['date', 'price', 'regime_signal']].copy()
        
        # 2. 计算持仓 (Day 1 买入)
        # 假设第一天以收盘价全仓买入 (不考虑滑点，作为纯基准)
        initial_price = results.iloc[0]['price']
        shares = self.initial_capital / initial_price
        
        # 3. 生成每日序列
        results['holdings'] = shares
        results['cash'] = 0.0 # 全仓买入，现金为0
        
        # 4. 计算每日净值 (Mark to Market)
        results['portfolio_value'] = results['price'] * results['holdings'] + results['cash']
        results['strategy'] = self.name
        
        # 计算一些辅助指标
        results['daily_pnl'] = results['portfolio_value'].diff().fillna(0)
        results['return_pct'] = results['portfolio_value'].pct_change().fillna(0)
        
        return results