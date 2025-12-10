import pandas as pd
import os
from datetime import datetime
from .config import Config

class BacktestEngine:
    """
    回测引擎：负责运行策略列表，并将结果标准化输出到 CSV。
    """
    def __init__(self, data_feed):
        self.data = data_feed
        # 结果保存路径: data/backtest_results/
        self.results_dir = os.path.join(Config.DATA_FOLDER, 'backtest_results')
        os.makedirs(self.results_dir, exist_ok=True)

    def run_strategies(self, strategies: list):
        """
        批量运行策略并保存结果。
        """
        print(f"\n🚀 [Engine] Starting Backtest on {len(strategies)} strategies...")
        print(f"   Output Directory: {self.results_dir}")
        
        all_equity_curves = []
        
        for strat in strategies:
            # 1. 运行策略
            try:
                res_df = strat.run(self.data)
                
                # 2. 保存单策略详细结果 (Daily logs)
                # 文件名: strategy_name_timestamp.csv
                safe_name = strat.name.replace(" ", "_").lower()
                filename = f"{safe_name}_details.csv"
                save_path = os.path.join(self.results_dir, filename)
                res_df.to_csv(save_path, index=False)
                
                # 3. 收集净值曲线用于汇总
                equity_curve = res_df[['date', 'portfolio_value']].copy()
                equity_curve.columns = ['date', strat.name]
                equity_curve.set_index('date', inplace=True)
                all_equity_curves.append(equity_curve)
                
                final_val = res_df.iloc[-1]['portfolio_value']
                print(f"   ✅ {strat.name:<20} Finished. Final Value: ${final_val:,.2f}")
                
            except Exception as e:
                print(f"   ❌ {strat.name:<20} Failed: {e}")

        # 4. 生成汇总对比表 (Master Table)
        if all_equity_curves:
            master_df = pd.concat(all_equity_curves, axis=1)
            master_df.reset_index(inplace=True)
            
            master_path = os.path.join(self.results_dir, 'all_strategies_pnl.csv')
            master_df.to_csv(master_path, index=False)
            print(f"\n📊 [Engine] Master PnL file saved: {master_path}")
            return master_df
        
        return None