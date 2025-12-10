import sys
import os
import pandas as pd

# 确保能找到 src 包
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.config import Config
from src.data_loader import load_market_data

from src.strategy_buy_and_hold import BuyAndHoldStrategy
from src.strategy_csp import CashSecuredPutStrategy
from src.strategy_wheel import WheelStrategy
from src.strategy_chamelon import SmartWheelStrategy
from src.backtest_engine import BacktestEngine
from src.pricing import OptionPricing

def main():
    print("="*60)
    print(" 🔥 BTC STRAT - RAPID BACKTEST LAUNCHER")
    print("="*60)

    # 1. 准备数据 (Data Layer + Regime Layer)
    # load_market_data 现在会自动调用 regime.py 计算信号
    try:
        df = load_market_data()
        OptionPricing.setup_market_data('synthetic_ibit_options.csv')
        
    except Exception as e:
        print(f"❌ Critical Error: Data loading failed. {e}")
        return

    # 2. 初始化引擎 (Engine Layer)
    engine = BacktestEngine(df)

    # 3. 准备策略池 (Strategy Layer)
    # 这里可以放多个策略，目前先跑基准
    strategies = [
    BuyAndHoldStrategy(initial_capital=100_000),
    # CashSecuredPutStrategy(initial_capital=100_000, target_delta=-0.30),
    # WheelStrategy(initial_capital=100_000, target_delta=0.30),

    SmartWheelStrategy(initial_capital=100_000, regime_window=90),
    
    # 选手2：中线平衡型 (180天窗口)
    SmartWheelStrategy(initial_capital=100_000, regime_window=180),
    
    # 选手3：长线迟钝型 (365天窗口) - 可能在趋势反转时反应慢
    SmartWheelStrategy(initial_capital=100_000, regime_window=365),
    ]

    # 4. 开火！
    engine.run_strategies(strategies)
    
    print("\n✅ Execution Complete.")

if __name__ == "__main__":
    main()