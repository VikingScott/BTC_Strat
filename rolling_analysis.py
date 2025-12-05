import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
import sys

# 确保能找到 src 包
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.config import Config
from src.data_loader import load_market_data
from src.strategy import (
    BuyHoldStrategy, CashSecuredPutStrategy, 
    CollarStrategy, ChameleonStrategy, WheelStrategy
)

# ==========================================
# 配置区域
# ==========================================
WINDOW_DAYS = 365       # 每次测试的时间窗口长度 (1年)
STEP_DAYS = 30          # 每次向后滑动的步长 (1个月)
MIN_DATA_POINTS = 200   # 窗口内最少要有几天数据才计算

# ==========================================
# 辅助函数
# ==========================================
def get_fresh_strategies():
    return {
        "Buy & Hold": BuyHoldStrategy(Config.INITIAL_CAPITAL),

        "CSP (15% OTM)": CashSecuredPutStrategy(
            Config.INITIAL_CAPITAL, 
            days=30, 
            otm=0.85
        ),

        "Wheel (15% OTM)": WheelStrategy(
            Config.INITIAL_CAPITAL, 
            days=30, 
            put_otm=0.85, 
            call_otm=1.15,
            slip=0.0
        ),

        "Collar (15%/20%)": CollarStrategy(
            Config.INITIAL_CAPITAL, 
            days=30, 
            protect=0.85, 
            cap=1.20
        ),
        
        "Chameleon": ChameleonStrategy(Config.INITIAL_CAPITAL)
    }

def calculate_metrics(history):
    if not history: return None
    df = pd.DataFrame(history).set_index('date')
    series = df['equity']
    
    # 1. Total Return (Approximates Annual Return since window is 365 days)
    init_eq = series.iloc[0]
    final_eq = series.iloc[-1]
    total_ret = (final_eq / init_eq) - 1
    
    # 2. Max Drawdown
    roll_max = series.cummax()
    dd = (series - roll_max) / roll_max
    max_dd = dd.min()
    
    # 3. Sharpe Ratio
    daily_ret = series.pct_change().fillna(0)
    vol = daily_ret.std() * np.sqrt(365)
    sharpe = (daily_ret.mean() * 365) / vol if vol != 0 else 0
    
    return {
        "Total Return": total_ret,
        "Max Drawdown": max_dd,
        "Sharpe": sharpe
    }

def generate_summary_table(df_res):
    """
    生成稳定性统计表格，并保存为图片
    """
    print("\n📊 Generating Stability Summary Table...")
    
    # 1. 聚合统计
    # 我们关心：平均收益、胜率（正收益占比）、平均夏普、最差回撤
    summary_list = []
    
    for strat_name, group in df_res.groupby('Strategy'):
        # 基础统计量
        avg_ret = group['Total Return'].mean()
        win_rate = (group['Total Return'] > 0).mean()
        avg_sharpe = group['Sharpe'].mean()
        min_sharpe = group['Sharpe'].min() # 最差情况
        avg_dd = group['Max Drawdown'].mean()
        worst_dd = group['Max Drawdown'].min() # 最深的回撤 (Drawdown of Drawdowns)
        
        summary_list.append({
            "Strategy": strat_name,
            "Avg Ann. Return": f"{avg_ret*100:.2f}%",
            "Win Rate (1Y)": f"{win_rate*100:.1f}%",
            "Avg Sharpe": f"{avg_sharpe:.2f}",
            "Min Sharpe": f"{min_sharpe:.2f}", # 压力测试指标
            "Avg MaxDD": f"{avg_dd*100:.2f}%",
            "Worst MaxDD": f"{worst_dd*100:.2f}%" # 极端风险指标
        })
        
    df_table = pd.DataFrame(summary_list)
    
    # 2. 打印到终端
    print("\n" + "="*80)
    print(f"{'ROLLING WINDOW STABILITY REPORT':^80}")
    print("="*80)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(df_table.to_string(index=False))
    print("="*80 + "\n")

    # 3. 保存为图片 (模仿 analytics.py 的风格)
    plt.figure(figsize=(14, len(df_table)*0.8 + 2))
    ax = plt.gca()
    ax.axis('off')
    
    # 绘制表格
    table = ax.table(
        cellText=df_table.values, 
        colLabels=df_table.columns, 
        cellLoc='center', 
        loc='center'
    )
    
    # 美化表格
    table.auto_set_column_width(col=list(range(len(df_table.columns))))
    table.scale(1, 1.5)
    
    for (i, j), cell in table.get_celld().items():
        if i == 0: # 表头
            cell.set_text_props(weight='bold', color='white')
            cell.set_facecolor('#2c3e50') # 深蓝色表头
        elif i > 0 and i % 2 == 0: # 隔行变色
            cell.set_facecolor('#ecf0f1')

    plt.title(f"Stability Analysis ({WINDOW_DAYS}-Day Rolling Windows)", pad=20, fontsize=14, fontweight='bold')
    
    save_path = os.path.join(Config.PIC_FOLDER, 'rolling_stability_table.png')
    plt.savefig(save_path, bbox_inches='tight', dpi=300)
    print(f"✅ Table saved to: {save_path}")

# ==========================================
# 主程序
# ==========================================
def run_rolling_analysis():
    print("🚀 [Rolling Analysis] Starting stability test...")
    
    try:
        df_full = load_market_data()
    except Exception as e:
        print(f"Error loading data: {e}")
        return

    start_date = df_full['date'].min()
    end_date = df_full['date'].max()
    results = []
    current_start = start_date
    
    print(f"   Data Range: {start_date.date()} to {end_date.date()}")
    
    # --- 滚动循环 ---
    while True:
        current_end = current_start + pd.Timedelta(days=WINDOW_DAYS)
        if current_end > end_date:
            break
            
        mask = (df_full['date'] >= current_start) & (df_full['date'] < current_end)
        df_slice = df_full.loc[mask].copy()
        
        if len(df_slice) < MIN_DATA_POINTS:
            current_start += pd.Timedelta(days=STEP_DAYS)
            continue
            
        print(f"   Running Window: {current_start.date()} -> {current_end.date()} ...", end='\r')
        
        strats = get_fresh_strategies()
        for name, strat in strats.items():
            strat.run(df_slice)
            metrics = calculate_metrics(strat.history)
            if metrics:
                results.append({
                    "Window End": current_end,
                    "Strategy": name,
                    "Sharpe": metrics['Sharpe'],
                    "Max Drawdown": metrics['Max Drawdown'],
                    "Total Return": metrics['Total Return']
                })
        
        current_start += pd.Timedelta(days=STEP_DAYS)

    print("\n✅ Analysis Complete.")
    
    if not results:
        print("❌ No results generated.")
        return

    df_res = pd.DataFrame(results)

    # --- Step 4: 生成曲线图 ---
    sns.set_theme(style="whitegrid")
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Arial']
    plt.rcParams['axes.unicode_minus'] = False
    
    fig, axes = plt.subplots(3, 1, figsize=(14, 18), sharex=True)
    
    sns.lineplot(data=df_res, x='Window End', y='Total Return', hue='Strategy', ax=axes[0], linewidth=2)
    axes[0].set_title(f'Rolling {WINDOW_DAYS}-Day Total Return', fontsize=12, fontweight='bold')
    axes[0].axhline(0, color='black', linestyle='--', alpha=0.3)
    
    sns.lineplot(data=df_res, x='Window End', y='Sharpe', hue='Strategy', ax=axes[1], linewidth=2)
    axes[1].set_title(f'Rolling {WINDOW_DAYS}-Day Sharpe Ratio (Consistency)', fontsize=12, fontweight='bold')
    axes[1].axhline(1.0, color='green', linestyle='--', alpha=0.5)
    axes[1].axhline(0, color='red', linestyle='--', alpha=0.3)

    sns.lineplot(data=df_res, x='Window End', y='Max Drawdown', hue='Strategy', ax=axes[2], linewidth=2)
    axes[2].set_title(f'Rolling {WINDOW_DAYS}-Day Max Drawdown (Risk)', fontsize=12, fontweight='bold')
    
    chart_path = os.path.join(Config.PIC_FOLDER, 'rolling_stability_charts.png')
    plt.tight_layout()
    plt.savefig(chart_path)
    print(f"📊 Charts saved to: {chart_path}")
    
    # --- Step 5: 生成表格 (新增功能) ---
    generate_summary_table(df_res)

if __name__ == "__main__":
    run_rolling_analysis()