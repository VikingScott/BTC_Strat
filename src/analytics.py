import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
from matplotlib.ticker import FuncFormatter
from .config import Config

# 绘图风格
sns.set_theme(style="whitegrid")
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Heiti TC', 'Arial', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 300

def run_analytics(strategies):
    print("\n📊 [Analytics] 生成报告...")
    os.makedirs(Config.TBL_FOLDER, exist_ok=True)
    os.makedirs(Config.PIC_FOLDER, exist_ok=True)
    
    metrics_list = []
    data_eq = {}
    data_dd = {} # 存储回撤数据

    for name, strat in strategies.items():
        if not strat.history: continue
        df = pd.DataFrame(strat.history).set_index('date')
        data_eq[name] = df['equity']
        
        # 指标计算
        series = df['equity']
        init_eq = series.iloc[0]
        final_eq = series.iloc[-1]
        
        total_ret = (final_eq / init_eq) - 1
        days = (series.index[-1] - series.index[0]).days
        if final_eq <= 0: ann_ret = -1.0
        elif days > 0: ann_ret = (final_eq / init_eq) ** (365 / days) - 1
        else: ann_ret = 0
        
        daily_ret = series.pct_change().fillna(0)
        vol = daily_ret.std() * np.sqrt(365)
        sharpe = (daily_ret.mean() * 365) / vol if vol != 0 else 0
        
        # 计算回撤序列
        roll_max = series.cummax()
        dd = (series - roll_max) / roll_max
        data_dd[name] = dd # 存起来画图
        max_dd = dd.min()
        
        calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0
        win_rate = len(daily_ret[daily_ret > 0]) / len(daily_ret) if len(daily_ret) > 0 else 0
        
        metrics_list.append({
            "Strategy": name,
            "Total Return": f"{total_ret*100:.2f}%",
            "Ann. Return": f"{ann_ret*100:.2f}%",
            "Sharpe": f"{sharpe:.2f}",
            "Max Drawdown": f"{max_dd*100:.2f}%",
            "Volatility": f"{vol*100:.2f}%",
            "Calmar": f"{calmar:.2f}",
            "Win Rate": f"{win_rate*100:.1f}%"
        })

    # 1. 终端表格
    df_metrics = pd.DataFrame(metrics_list)
    if not df_metrics.empty:
        print("\n" + "="*100)
        print(f"{'PERFORMANCE SUMMARY':^100}")
        print("="*100)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        print(df_metrics.to_string(index=False))
        print("="*100 + "\n")
        
        # 2. 表格图片
        fig, ax = plt.subplots(figsize=(16, len(df_metrics)*0.8 + 2))
        ax.axis('off')
        table = ax.table(cellText=df_metrics.values, colLabels=df_metrics.columns, cellLoc='center', loc='center')
        table.auto_set_column_width(col=list(range(len(df_metrics.columns))))
        table.scale(1, 1.5)
        for (i, j), cell in table.get_celld().items():
            if i == 0:
                cell.set_text_props(weight='bold', color='white')
                cell.set_facecolor('#4a69bd')
            elif i > 0 and i % 2 == 0:
                cell.set_facecolor('#f1f2f6')
        plt.title("Performance Summary", pad=20)
        plt.savefig(os.path.join(Config.TBL_FOLDER, 'skew_summary_table.png'), bbox_inches='tight')
        plt.close()

    # 3. 净值曲线 (Equity Curve)
    df_res = pd.DataFrame(data_eq).fillna(method='ffill').dropna()
    if not df_res.empty:
        plt.figure(figsize=(12, 6))
        for col in df_res.columns:
            ls = '--' if 'Hold' in col else '-'
            lw = 2.0 if 'Chameleon' in col else 1.5
            plt.plot(df_res.index, df_res[col], label=col, linestyle=ls, linewidth=lw)
        plt.title("Account Equity Comparison")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda x, p: f'${x:,.0f}'))
        plt.savefig(os.path.join(Config.PIC_FOLDER, 'skew_equity_curve.png'))
        plt.close()

    # 4. 回撤曲线 (Drawdown Curve) - 【新增】
    df_dd = pd.DataFrame(data_dd).fillna(0)
    if not df_dd.empty:
        plt.figure(figsize=(12, 6))
        for col in df_dd.columns:
            ls = '--' if 'Hold' in col else '-'
            plt.plot(df_dd.index, df_dd[col], label=col, linestyle=ls, linewidth=1.5, alpha=0.8)
            # 填充颜色，让视觉效果更好
            plt.fill_between(df_dd.index, df_dd[col], 0, alpha=0.05)
            
        plt.title("Max Drawdown Comparison")
        plt.legend(loc='lower left')
        plt.grid(True, alpha=0.3)
        plt.ylabel('Drawdown (%)')
        # Y轴转百分比
        plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda y, _: '{:.0%}'.format(y)))
        plt.savefig(os.path.join(Config.PIC_FOLDER, 'skew_drawdown_comparison.png'))
        plt.close()
        
    print(f"✅ Reports saved to {Config.PIC_FOLDER} and {Config.TBL_FOLDER}")