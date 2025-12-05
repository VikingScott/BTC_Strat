import sys
import os

# 确保能找到 src 包
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.config import Config
from src.data_loader import load_market_data
from src.strategy import (
    BuyHoldStrategy, CoveredCallStrategy, CashSecuredPutStrategy, 
    CollarStrategy, ChameleonStrategy, WheelStrategy, RegimeCollarStrategy
)
from src.analytics import run_analytics

def main():
    try:
        df = load_market_data()
    except Exception as e:
        print(f"Error loading data: {e}")
        return

    # 策略池配置
    strategies = {
         "Buy & Hold": BuyHoldStrategy(Config.INITIAL_CAPITAL),
        
        # "Covered Call (30D, 10%)": CoveredCallStrategy(
        #     Config.INITIAL_CAPITAL, days=30, otm=1.10
        # ),
        
        "Cash-Secured Put (30D, 10%)": CashSecuredPutStrategy(
            Config.INITIAL_CAPITAL, days=30, otm=0.90
        ),
        
        # "Collar (30D, -15%/+10%)": CollarStrategy(
        #     Config.INITIAL_CAPITAL, days=30, protect=0.85, cap=1.1
        # ),

        # "Regime Collar (Timed, -15%/+10%)": RegimeCollarStrategy(
        #     Config.INITIAL_CAPITAL, days=30, protect=0.85, cap=1.1
        # ),
        
        "Chameleon (Smart Switch)": ChameleonStrategy(Config.INITIAL_CAPITAL),

        "The Wheel": WheelStrategy(
            Config.INITIAL_CAPITAL, days=30, put_otm=0.90, call_otm=1.10,slip=0.02
        )
        
    }

    print("\n🚀 Running Strategies...")
    for name, strat in strategies.items():
        print(f"   Running: {name}...")
        strat.run(df)
    
    run_analytics(strategies)

if __name__ == "__main__":
    main()