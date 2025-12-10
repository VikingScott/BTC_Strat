import glob
import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# 路径处理
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

# ===========================
# 工具函数
# ===========================
def format_performance_df(df):
    """
    将数值型的 DataFrame 格式化为易读的字符串型 DataFrame。
    """
    formatted_df = df.copy()
    
    # 百分比格式化列
    pct_cols = ['Total Return', 'CAGR', 'Max Drawdown', 'VaR 95%', 'CVaR 95%', 'Worst Day']
    for col in pct_cols:
        if col in formatted_df.columns:
            formatted_df[col] = pd.to_numeric(formatted_df[col], errors='coerce')
            formatted_df[col] = formatted_df[col].apply(lambda x: f"{x:.1%}" if pd.notnull(x) else "N/A")

    # 小数格式化列
    float_cols = ['Sharpe', 'Sortino', 'Calmar', 'Skewness', 'Kurtosis']
    for col in float_cols:
        if col in formatted_df.columns:
            formatted_df[col] = pd.to_numeric(formatted_df[col], errors='coerce')
            formatted_df[col] = formatted_df[col].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "N/A")
            
    return formatted_df

def transpose_for_display(df, index_col='Strategy', new_index_name='Metric'):
    """
    将 DataFrame 转置：索引列变为表头，列变为行。
    例如：从 (策略 x 指标) 变为 (指标 x 策略)
    """
    if df.empty: return df
    if index_col in df.columns:
        # 1. 设置索引
        temp_df = df.set_index(index_col)
        # 2. 转置
        transposed_df = temp_df.T
        # 3. 重置索引，把原来的列名变成第一列
        transposed_df = transposed_df.reset_index()
        # 4. 重命名第一列
        transposed_df.rename(columns={'index': new_index_name}, inplace=True)
        return transposed_df
    return df

# ===========================
# 报告生成逻辑
# ===========================
def generate_regime_report(master_df, viz: Visualizer, output_dir='tbl'):
    """生成分 Regime 的报告 (CSV + 转置后的图片)"""
    print("   📊 Generating Regime Performance Analysis...")
    if 'regime_signal' not in master_df.columns:
        print("   ⚠️ Warning: 'regime_signal' missing. Skipping.")
        return

    report_data = []
    strategy_cols = [c for c in master_df.columns if c not in ['regime_signal', 'date']]

    for strat in strategy_cols:
        full_sharpe = PerformanceMetrics.get_sharpe_ratio(master_df[strat])
        
        row = {'Strategy': strat, 'Full Sharpe': full_sharpe}

        for reg in ['Low', 'Normal', 'High']:
            mask = master_df['regime_signal'] == reg
            subset = master_df.loc[mask, strat]
            
            if len(subset) > 30:
                reg_sharpe = PerformanceMetrics.get_sharpe_ratio(subset)
                reg_ret = subset.pct_change().mean() * 252 
            else:
                reg_sharpe = np.nan
                reg_ret = np.nan
            
            row[f'{reg} Sharpe'] = reg_sharpe
            row[f'{reg} Ann.Ret'] = reg_ret
        
        report_data.append(row)

    # 1. 保存原始 CSV (保持 策略=行，方便机器读取)
    os.makedirs(output_dir, exist_ok=True)
    raw_regime_df = pd.DataFrame(report_data)
    
    # 格式化
    fmt_regime_df = raw_regime_df.copy()
    for col in fmt_regime_df.columns:
        if 'Sharpe' in col:
            fmt_regime_df[col] = fmt_regime_df[col].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "-")
        elif 'Ann.Ret' in col:
            fmt_regime_df[col] = fmt_regime_df[col].apply(lambda x: f"{x:.1%}" if pd.notnull(x) else "-")

    csv_path = os.path.join(output_dir, 'regime_performance.csv')
    fmt_regime_df.to_csv(csv_path, index=False)
    print(f"   ✅ Regime CSV Saved: {csv_path}")

    # 2. 保存为图片 (转置！策略=列，指标=行)
    # 转置逻辑：Strategy列变成表头
    img_df = transpose_for_display(fmt_regime_df, index_col='Strategy')
    viz.save_dataframe_as_image(img_df, 'regime_performance.png')


def generate_reports():
    print("\n📊 [Reporting] Aggregating results & generating reports...")
    
    # 1. 扫描与聚合数据
    results_dir = os.path.join(Config.DATA_FOLDER, 'backtest_results')
    all_files = glob.glob(os.path.join(results_dir, "*_details.csv"))
    if not all_files:
        print("❌ No strategy results found!")
        return

    master_df = pd.DataFrame()
    regime_series = None
    
    for f in all_files:
        df = pd.read_csv(f, parse_dates=['date'])
        if df.empty: continue
        df.set_index('date', inplace=True)
        strategy_name = df['strategy'].iloc[0]
        series = df['portfolio_value']
        series.name = strategy_name
        
        if master_df.empty:
            master_df = pd.DataFrame(series)
        else:
            master_df = master_df.join(series, how='outer')
            
        if regime_series is None and 'regime_signal' in df.columns:
            regime_series = df['regime_signal']
            
    master_df.sort_index(inplace=True)
    master_df.fillna(method='ffill', inplace=True)
    if regime_series is not None:
        master_df['regime_signal'] = regime_series.reindex(master_df.index).fillna(method='ffill')
    
    viz = Visualizer(output_dir='pic')

    # 2. 计算汇总指标
    raw_stats = []
    strategy_cols = [c for c in master_df.columns if c != 'regime_signal']
    
    for strat_name in strategy_cols:
        s = master_df[strat_name]
        tail_metrics = PerformanceMetrics.get_tail_risk_metrics(s)
        
        stats_row = {
            'Strategy': strat_name,
            'Total Return': (s.iloc[-1]/s.iloc[0] - 1),
            'CAGR': PerformanceMetrics.get_cagr(s),
            'Sharpe': PerformanceMetrics.get_sharpe_ratio(s),
            'Sortino': PerformanceMetrics.get_sortino_ratio(s),
            'Max Drawdown': PerformanceMetrics.get_max_drawdown(s),
            'Calmar': PerformanceMetrics.get_calmar_ratio(s),
            'VaR 95%': tail_metrics.get('VaR 95%'),
            'CVaR 95%': tail_metrics.get('CVaR 95%'),
            'Skewness': tail_metrics.get('Skewness'),
            'Kurtosis': tail_metrics.get('Kurtosis'),
            'Worst Day': tail_metrics.get('Worst Day')
        }
        raw_stats.append(stats_row)
        
    raw_stats_df = pd.DataFrame(raw_stats).set_index('Strategy')
    formatted_stats_df = format_performance_df(raw_stats_df.reset_index())

    # 3. 保存与可视化
    os.makedirs('tbl', exist_ok=True)
    
    # A. 保存 CSV (保持原样：行=策略)
    tbl_path = os.path.join('tbl', 'performance_summary.csv')
    formatted_stats_df.to_csv(tbl_path, index=False)
    print(f"   📝 Summary CSV Saved: {tbl_path}")
    
    # B. 保存图片 (转置！行=指标，列=策略)
    # 这样生成的图片表格，每列是一个策略，便于横向对比
    img_df = transpose_for_display(formatted_stats_df, index_col='Strategy')
    viz.save_dataframe_as_image(img_df, 'performance_summary.png')

    # C. 其他报告
    generate_regime_report(master_df, viz, output_dir='tbl')

    viz_df = master_df[strategy_cols].copy()
    viz.plot_equity_comparison(viz_df)
    viz.plot_drawdown_comparison(viz_df)
    viz.plot_rolling_sharpe(viz_df)
    
    # D. 风险图表 (使用原始数值)
    viz.plot_risk_comparison(raw_stats_df)

if __name__ == "__main__":
    generate_reports()