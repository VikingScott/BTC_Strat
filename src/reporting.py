import glob
import os
import sys
from pathlib import Path

import pandas as pd

# 支持两种运行方式:
# 1) 包内调用: python -m src.reporting
# 2) 直接脚本: python src/reporting.py
if __package__ in (None, ""):
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.append(str(repo_root))
    from src.config import Config
    from src.metrics import PerformanceMetrics
    from src.visualizer import Visualizer
else:
    from .config import Config
    from .metrics import PerformanceMetrics
    from .visualizer import Visualizer

def generate_reports():
    print("\n📊 [Reporting] Aggregating results & generating reports...")
    
    # 1. 扫描结果文件夹
    results_dir = os.path.join(Config.DATA_FOLDER, 'backtest_results')
    all_files = glob.glob(os.path.join(results_dir, "*_details.csv"))
    
    if not all_files:
        print("❌ No strategy results found!")
        return

    # 2. 聚合净值曲线 (Merge by Date)
    master_df = pd.DataFrame()
    
    for f in all_files:
        # 读取每个策略文件
        df = pd.read_csv(f, parse_dates=['date'])
        strategy_name = df['strategy'].iloc[0] # 获取策略名
        
        # 提取净值列，并重命名为策略名
        series = df.set_index('date')['portfolio_value']
        series.name = strategy_name
        
        if master_df.empty:
            master_df = pd.DataFrame(series)
        else:
            master_df = master_df.join(series, how='outer')
            
    master_df.sort_index(inplace=True)
    master_df.fillna(method='ffill', inplace=True) # 填充空缺
    
    # 3. 计算汇总指标表格 (Summary Table)
    stats = []
    for strat_name in master_df.columns:
        s = master_df[strat_name]
        stats.append({
            'Strategy': strat_name,
            'Total Return': f"{(s.iloc[-1]/s.iloc[0] - 1):.1%}",
            'CAGR': f"{PerformanceMetrics.get_cagr(s):.1%}",
            'Sharpe': f"{PerformanceMetrics.get_sharpe_ratio(s):.2f}",
            'Sortino': f"{PerformanceMetrics.get_sortino_ratio(s):.2f}",
            'Max Drawdown': f"{PerformanceMetrics.get_max_drawdown(s):.1%}",
            'Calmar': f"{PerformanceMetrics.get_calmar_ratio(s):.2f}"
        })
        
    stats_df = pd.DataFrame(stats)
    
    # 保存表格
    tbl_path = os.path.join('tbl', 'performance_summary.csv')
    os.makedirs('tbl', exist_ok=True)
    stats_df.to_csv(tbl_path, index=False)
    print(f"   📝 Table Saved: {tbl_path}")
    print(stats_df) # 在控制台打印出来看看

    # 4. 调用绘图师画对比图
    viz = Visualizer(output_dir='pic')
    
    # 传入宽表，直接画对比
    viz.plot_equity_comparison(master_df)
    viz.plot_drawdown_comparison(master_df)
    viz.plot_rolling_sharpe(master_df)

if __name__ == "__main__":
    generate_reports()
