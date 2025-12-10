import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import os
from .config import Config

# 设置专业金融图表风格
sns.set_theme(style="darkgrid")
plt.rcParams['font.family'] = 'sans-serif' 

class Visualizer:
    def __init__(self, output_dir='pic'):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def _paint_regime_background(self, ax, regime_series):
        """内部工具：给图表画上 Regime 背景色"""
        # 简单处理：High=红色背景，Low=绿色背景
        # 这里需要更复杂的逻辑把 series 转换成 span，暂略，模拟效果
        pass 

    def plot_equity_comparison(self, combined_df):
        """
        画出所有策略的净值曲线对比 (Log Scale)
        """
        plt.figure(figsize=(14, 7))
        
        # 自动遍历所有列进行绘图
        for col in combined_df.columns:
            # 突出显示 Buy & Hold 作为基准
            if 'Buy & Hold' in col:
                plt.plot(combined_df.index, combined_df[col], 
                         label=col, color='black', linewidth=2, linestyle='--')
            else:
                plt.plot(combined_df.index, combined_df[col], label=col, linewidth=1.5)

        plt.yscale('log') # 对数坐标看长期
        plt.title('Strategy Equity Curves Comparison (Log Scale)', fontsize=16)
        plt.ylabel('Portfolio Value ($)', fontsize=12)
        plt.legend(loc='upper left')
        
        save_path = os.path.join(self.output_dir, 'compare_equity_curves.png')
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   🖼️ Saved: {save_path}")

    def plot_drawdown_comparison(self, combined_df):
        """
        画出所有策略的水下回撤图 (Underwater Plot)
        """
        plt.figure(figsize=(14, 6))
        
        for col in combined_df.columns:
            # 计算回撤序列
            roll_max = combined_df[col].expanding().max()
            dd = (combined_df[col] - roll_max) / roll_max
            
            plt.plot(combined_df.index, dd, label=col, linewidth=1)
            # 填充颜色让痛苦更直观
            plt.fill_between(combined_df.index, dd, 0, alpha=0.1)

        plt.title('Drawdown Comparison (Underwater Plot)', fontsize=16)
        plt.ylabel('Drawdown %', fontsize=12)
        plt.legend(loc='lower left')
        
        save_path = os.path.join(self.output_dir, 'compare_drawdowns.png')
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   🖼️ Saved: {save_path}")

    def plot_rolling_sharpe(self, combined_df):
        """
        对比滚动夏普比率（稳定性分析）
        """
        from .metrics import PerformanceMetrics
        
        plt.figure(figsize=(14, 6))
        
        for col in combined_df.columns:
            rolling_s = PerformanceMetrics.get_rolling_sharpe(combined_df[col], window=180)
            plt.plot(rolling_s.index, rolling_s, label=col, linewidth=1.5)

        plt.axhline(0, color='red', linestyle=':', alpha=0.5)
        plt.title('180-Day Rolling Sharpe Ratio', fontsize=16)
        plt.ylabel('Sharpe', fontsize=12)
        plt.legend(loc='lower left')
        
        save_path = os.path.join(self.output_dir, 'compare_rolling_sharpe.png')
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   🖼️ Saved: {save_path}")