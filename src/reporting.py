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
    from src.data_loader import load_market_data  # ✅ 新增：引入数据加载器
    from src.metrics import PerformanceMetrics
    from src.visualizer import Visualizer
else:
    from .config import Config
    from .data_loader import load_market_data     # ✅ 新增
    from .metrics import PerformanceMetrics
    from .visualizer import Visualizer

# ===========================
# 工具函数
# ===========================
def format_performance_df(df):
    """格式化数值为易读字符串"""
    formatted_df = df.copy()
    
    pct_cols = ['Total Return', 'CAGR', 'Max Drawdown', 'VaR 95%', 'CVaR 95%', 'Worst Day']
    for col in pct_cols:
        if col in formatted_df.columns:
            formatted_df[col] = pd.to_numeric(formatted_df[col], errors='coerce')
            formatted_df[col] = formatted_df[col].apply(lambda x: f"{x:.1%}" if pd.notnull(x) else "N/A")

    float_cols = ['Sharpe', 'Sortino', 'Calmar', 'Skewness', 'Kurtosis']
    for col in float_cols:
        if col in formatted_df.columns:
            formatted_df[col] = pd.to_numeric(formatted_df[col], errors='coerce')
            formatted_df[col] = formatted_df[col].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "N/A")
            
    return formatted_df

def transpose_for_display(df, index_col='Strategy', new_index_name='Metric'):
    """表格转置函数"""
    if df.empty: return df
    if index_col in df.columns:
        temp_df = df.set_index(index_col)
        transposed_df = temp_df.T
        transposed_df = transposed_df.reset_index()
        transposed_df.rename(columns={'index': new_index_name}, inplace=True)
        return transposed_df
    return df

# ===========================
# 报告生成逻辑
# ===========================
def generate_regime_report(master_df, market_data, viz: Visualizer, output_dir='tbl'):
    """
    生成分 Regime 报告。
    ✅ 修改：使用 market_data 中的权威 regime_signal，而不是策略结果里的
    """
    print("   📊 Generating Regime Performance Analysis...")
    
    # 确保 market_data 和 master_df 在时间上对齐
    # 我们以 master_df 的时间索引为准
    common_idx = master_df.index.intersection(market_data.index)
    if common_idx.empty:
        print("   ⚠️ Warning: No overlapping dates between strategies and market data.")
        return

    # 提取对齐后的数据
    aligned_strategies = master_df.loc[common_idx]
    aligned_regime = market_data.loc[common_idx, 'regime_signal']
    aligned_r = market_data.loc[common_idx, 'r']

    report_data = []
    # 排除非策略列 (如果有的话)
    strategy_cols = [c for c in aligned_strategies.columns if c not in ['regime_signal', 'date']]

    for strat in strategy_cols:
        # 1. 全周期 Sharpe (使用动态无风险利率)
        full_sharpe = PerformanceMetrics.get_sharpe_ratio(
            aligned_strategies[strat], 
            risk_free_rate=aligned_r
        )
        
        row = {'Strategy': strat, 'Full Sharpe': full_sharpe}

        # 2. 分 Regime 表现
        for reg in ['Low', 'Normal', 'High']:
            mask = aligned_regime == reg
            subset_strat = aligned_strategies.loc[mask, strat]
            subset_r = aligned_r.loc[mask]
            
            if len(subset_strat) > 30:
                reg_sharpe = PerformanceMetrics.get_sharpe_ratio(
                    subset_strat, 
                    risk_free_rate=subset_r
                )
                # 简单年化回报
                reg_ret = subset_strat.pct_change().mean() * 252 
            else:
                reg_sharpe = np.nan
                reg_ret = np.nan
            
            row[f'{reg} Sharpe'] = reg_sharpe
            row[f'{reg} Ann.Ret'] = reg_ret
        
        report_data.append(row)

    # 保存与可视化
    os.makedirs(output_dir, exist_ok=True)
    raw_regime_df = pd.DataFrame(report_data)
    
    fmt_regime_df = raw_regime_df.copy()
    for col in fmt_regime_df.columns:
        if 'Sharpe' in col:
            fmt_regime_df[col] = fmt_regime_df[col].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "-")
        elif 'Ann.Ret' in col:
            fmt_regime_df[col] = fmt_regime_df[col].apply(lambda x: f"{x:.1%}" if pd.notnull(x) else "-")

    csv_path = os.path.join(output_dir, 'regime_performance.csv')
    fmt_regime_df.to_csv(csv_path, index=False)
    print(f"   ✅ Regime CSV Saved: {csv_path}")

    # 转置绘图
    img_df = transpose_for_display(fmt_regime_df, index_col='Strategy')
    viz.save_dataframe_as_image(img_df, 'regime_performance.png')


def generate_reports():
    print("\n📊 [Reporting] Aggregating results & generating reports...")
    
    # ------------------------------------------------------
    # 1. ✅ 新增：加载全量宏观数据 (Market Data Context)
    # ------------------------------------------------------
    try:
        # load_market_data 会返回包含 date, r, regime_signal, price 的 DataFrame
        market_data = load_market_data()
        market_data.set_index('date', inplace=True)
        print(f"   🌍 Market Context Loaded: {len(market_data)} days")
    except Exception as e:
        print(f"   ❌ Failed to load market data: {e}")
        return

    # ------------------------------------------------------
    # 2. 扫描与聚合策略结果
    # ------------------------------------------------------
    results_dir = os.path.join(Config.DATA_FOLDER, 'backtest_results')
    all_files = glob.glob(os.path.join(results_dir, "*_details.csv"))
    if not all_files:
        print("❌ No strategy results found!")
        return

    master_df = pd.DataFrame()
    
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
            
    master_df.sort_index(inplace=True)
    master_df.ffill(inplace=True)
    
    # ✅ 关键步骤：对齐 Market Data 和 Strategy Data
    # 我们只关心策略存续期间的数据
    common_index = master_df.index.intersection(market_data.index)
    master_df = master_df.loc[common_index]
    market_subset = market_data.loc[common_index] # 对应的宏观数据片段

    viz = Visualizer(output_dir='pic')

    # ------------------------------------------------------
    # 3. 计算汇总指标 (使用真实利率)
    # ------------------------------------------------------
    raw_stats = []
    
    for strat_name in master_df.columns:
        s = master_df[strat_name]
        # 获取对应的无风险利率序列
        r_series = market_subset['r']
        
        tail_metrics = PerformanceMetrics.get_tail_risk_metrics(s)
        
        stats_row = {
            'Strategy': strat_name,
            'Total Return': (s.iloc[-1]/s.iloc[0] - 1),
            'CAGR': PerformanceMetrics.get_cagr(s),
            # ✅ 修改：传入真实利率序列
            'Sharpe': PerformanceMetrics.get_sharpe_ratio(s, risk_free_rate=r_series),
            'Sortino': PerformanceMetrics.get_sortino_ratio(s, risk_free_rate=r_series),
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

    # ------------------------------------------------------
    # 4. 保存与可视化
    # ------------------------------------------------------
    os.makedirs('tbl', exist_ok=True)
    
    # A. 保存 CSV
    tbl_path = os.path.join('tbl', 'performance_summary.csv')
    formatted_stats_df.to_csv(tbl_path, index=False)
    print(f"   📝 Summary CSV Saved: {tbl_path}")
    
    # B. 保存图片 (转置)
    img_df = transpose_for_display(formatted_stats_df, index_col='Strategy')
    viz.save_dataframe_as_image(img_df, 'performance_summary.png')

    # C. Regime 报告 (传入全量 market_data)
    generate_regime_report(master_df, market_data, viz, output_dir='tbl')

    # D. 绘制图表 (传入 market_data 用于画背景)
    # ✅ 修改：所有绘图函数都增加 market_data 参数
    viz.plot_equity_comparison(master_df, market_data=market_data)
    viz.plot_drawdown_comparison(master_df, market_data=market_data)
    viz.plot_rolling_sharpe(master_df) # 滚动夏普暂时只看自身稳定性，可选是否加背景
    
    # E. 风险图表
    viz.plot_risk_comparison(raw_stats_df)

if __name__ == "__main__":
    generate_reports()