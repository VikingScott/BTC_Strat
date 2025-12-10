import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import os
import numpy as np
from .config import Config

# 设置专业金融图表风格
sns.set_theme(style="whitegrid")
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['axes.unicode_minus'] = False 

class Visualizer:
    def __init__(self, output_dir='pic'):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.tbl_img_dir = 'tbl'
        os.makedirs(self.tbl_img_dir, exist_ok=True)

    # ===========================
    # 核心升级：画背景色 (Regime Background)
    # ===========================
    def _paint_regime_background(self, ax, market_data):
        """
        根据 market_data['regime_signal'] 给图表加上背景色。
        Low=绿色(安全), High=红色(危险), Normal=白色
        """
        if market_data is None or 'regime_signal' not in market_data.columns:
            return

        # 确保我们有数据，并且索引是日期
        df = market_data.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
            else:
                return 

        # 找出状态变化的区块
        # 逻辑：创建一个新列 'group'，每当 regime 变化时，group ID +1
        df['group'] = (df['regime_signal'] != df['regime_signal'].shift()).cumsum()
        
        # 按块遍历画图
        for _, block in df.groupby('group'):
            regime = block['regime_signal'].iloc[0]
            start_date = block.index[0]
            end_date = block.index[-1]
            
            color = None
            if regime == 'High':
                color = '#ff9999' # 浅红 (High Vol / Panic)
            elif regime == 'Low':
                color = '#99ff99' # 浅绿 (Low Vol / Safe)
            
            # Normal 不画色，保持白底
            if color:
                # alpha=0.15 保证背景色淡淡的，不喧宾夺主
                ax.axvspan(start_date, end_date, color=color, alpha=0.15, lw=0)

    # ===========================
    # 表格转图片 (保持不变)
    # ===========================
    def save_dataframe_as_image(self, df, filename):
        if df.empty: return

        num_rows, num_cols = df.shape
        figsize = (num_cols * 1.5 + 1, num_rows * 0.4 + 0.5)
        
        fig, ax = plt.subplots(figsize=figsize)
        ax.axis('tight')
        ax.axis('off')

        table = ax.table(cellText=df.values,
                         colLabels=df.columns,
                         loc='center',
                         cellLoc='center')

        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.2, 1.5)

        for (row, col), cell in table.get_celld().items():
            if row == 0:
                cell.set_text_props(weight='bold', color='white')
                cell.set_facecolor('#40466e')
            else:
                if row % 2 == 0:
                    cell.set_facecolor('#f2f2f2')
                else:
                    cell.set_facecolor('white')

        save_path = os.path.join(self.tbl_img_dir, filename)
        plt.savefig(save_path, dpi=300, bbox_inches='tight', pad_inches=0.05)
        plt.close()
        print(f"   🖼️ Table Image Saved: {save_path}")

    # ===========================
    # 绘图函数升级：接收 market_data
    # ===========================
    def plot_equity_comparison(self, combined_df, market_data=None):
        """画出所有策略的净值曲线对比 (Log Scale)"""
        plt.figure(figsize=(14, 7))
        ax = plt.gca() # 获取当前轴
        
        # 1. 先画背景 (如果有数据)
        if market_data is not None:
            # 截取与策略相同的时间段，避免画出多余的背景
            common_idx = market_data.index.intersection(combined_df.index)
            if not common_idx.empty:
                # 稍微扩大一点范围，让背景连贯
                start, end = combined_df.index[0], combined_df.index[-1]
                subset = market_data.loc[start:end]
                self._paint_regime_background(ax, subset)

        # 2. 再画曲线
        palette = sns.color_palette("husl", len(combined_df.columns))
        
        for i, col in enumerate(combined_df.columns):
            if 'Buy & Hold' in col:
                plt.plot(combined_df.index, combined_df[col], 
                         label=col, color='black', linewidth=2.5, linestyle='--', alpha=0.8)
            else:
                plt.plot(combined_df.index, combined_df[col], label=col, linewidth=2, color=palette[i], alpha=0.9)

        plt.yscale('log')
        plt.title('Strategy Equity Curves Comparison (with Regime Background)', fontsize=14, fontweight='bold')
        plt.ylabel('Portfolio Value ($) - Log Scale', fontsize=12)
        
        # 添加自定义图例
        # 创建背景色图例
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='#ff9999', edgecolor='none', alpha=0.3, label='High Vol Regime'),
            Patch(facecolor='#99ff99', edgecolor='none', alpha=0.3, label='Low Vol Regime')
        ]
        # 获取原有图例
        handles, labels = ax.get_legend_handles_labels()
        # 合并
        ax.legend(handles=handles + legend_elements, loc='upper left', frameon=True, shadow=True)
        
        plt.grid(True, which='both', linestyle=':', alpha=0.5)
        
        save_path = os.path.join(self.output_dir, 'compare_equity_curves.png')
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   🖼️ Saved Equity Chart: {save_path}")

    def plot_drawdown_comparison(self, combined_df, market_data=None):
        """画出所有策略的水下回撤图"""
        plt.figure(figsize=(14, 6))
        ax = plt.gca()

        # 1. 画背景
        if market_data is not None:
            start, end = combined_df.index[0], combined_df.index[-1]
            subset = market_data.loc[start:end]
            self._paint_regime_background(ax, subset)

        palette = sns.color_palette("husl", len(combined_df.columns))

        for i, col in enumerate(combined_df.columns):
            roll_max = combined_df[col].expanding().max()
            dd = (combined_df[col] - roll_max) / roll_max
            
            plt.plot(combined_df.index, dd, label=col, linewidth=1.5, color=palette[i])
            plt.fill_between(combined_df.index, dd, 0, color=palette[i], alpha=0.1)

        plt.title('Drawdown Comparison (with Regime Background)', fontsize=14, fontweight='bold')
        plt.ylabel('Drawdown %', fontsize=12)
        plt.ylim(bottom=dd.min()*1.1, top=0.01)
        plt.legend(loc='lower left', frameon=True)
        
        save_path = os.path.join(self.output_dir, 'compare_drawdowns.png')
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   🖼️ Saved Drawdown Chart: {save_path}")

    def plot_rolling_sharpe(self, combined_df):
        """对比滚动夏普比率 (不加背景，保持清晰)"""
        from .metrics import PerformanceMetrics
        plt.figure(figsize=(14, 6))
        palette = sns.color_palette("husl", len(combined_df.columns))
        
        for i, col in enumerate(combined_df.columns):
            rolling_s = PerformanceMetrics.get_rolling_sharpe(combined_df[col], window=180)
            plt.plot(rolling_s.index, rolling_s, label=col, linewidth=1.5, color=palette[i])

        plt.axhline(0, color='red', linestyle='-', linewidth=1, alpha=0.5)
        plt.axhline(1, color='gray', linestyle=':', linewidth=1, alpha=0.5)
        plt.title('180-Day Rolling Sharpe Ratio (Stability Check)', fontsize=14, fontweight='bold')
        plt.ylabel('Sharpe Ratio', fontsize=12)
        plt.legend(loc='lower left', frameon=True)
        
        save_path = os.path.join(self.output_dir, 'compare_rolling_sharpe.png')
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   🖼️ Saved Rolling Sharpe Chart: {save_path}")

    def plot_risk_comparison(self, risk_df):
        """可视化风险指标"""
        if risk_df.empty: return

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('Strategy Risk Profile Comparison', fontsize=16, fontweight='bold')
        
        strategies = risk_df.index
        colors = sns.color_palette("viridis", len(strategies))

        # --- 1. Tail Risk ---
        ax_tail = axes[0, 0]
        # 确保是数值类型
        var_data = pd.DataFrame({
            'VaR 95%': pd.to_numeric(risk_df['VaR 95%'], errors='coerce').abs(),
            'CVaR 95%': pd.to_numeric(risk_df['CVaR 95%'], errors='coerce').abs()
        })
        
        var_data.plot(kind='bar', ax=ax_tail, width=0.8, color=['#ff9999', '#cc0000'], edgecolor='black')
        ax_tail.set_title('Left-Tail Risk Magnitude (Loss %)', fontweight='bold')
        ax_tail.set_xticklabels(strategies, rotation=45, ha='right')
        ax_tail.legend(['VaR 95%', 'CVaR 95%'])
        ax_tail.grid(axis='y', linestyle='--', alpha=0.7)

        # --- 2. Skewness ---
        ax_skew = axes[0, 1]
        sns.barplot(x=strategies, y=pd.to_numeric(risk_df['Skewness']), ax=ax_skew, palette=colors)
        ax_skew.set_title('Skewness (Negative = Crash Risk)', fontweight='bold')
        ax_skew.axhline(0, color='black', linewidth=1)
        ax_skew.set_xticklabels(strategies, rotation=45, ha='right')

        # --- 3. Kurtosis ---
        ax_kurt = axes[1, 0]
        sns.barplot(x=strategies, y=pd.to_numeric(risk_df['Kurtosis']), ax=ax_kurt, palette=colors)
        ax_kurt.set_title('Kurtosis (Fat Tails)', fontweight='bold')
        ax_kurt.axhline(3.0, color='red', linestyle='--')
        ax_kurt.set_xticklabels(strategies, rotation=45, ha='right')

        # --- 4. Scatter ---
        ax_scatter = axes[1, 1]
        x_val = pd.to_numeric(risk_df['Max Drawdown'], errors='coerce')
        y_val = pd.to_numeric(risk_df['Sharpe'], errors='coerce')
        
        sns.scatterplot(x=x_val, y=y_val, hue=strategies, s=200, palette=colors, ax=ax_scatter)
        
        for i, txt in enumerate(strategies):
            if pd.notnull(x_val.iloc[i]) and pd.notnull(y_val.iloc[i]):
                ax_scatter.annotate(txt, (x_val.iloc[i], y_val.iloc[i]), xytext=(5, 5), textcoords='offset points')

        ax_scatter.set_title('Risk-Reward Landscape', fontweight='bold')
        ax_scatter.set_xlabel('Max Drawdown')
        ax_scatter.set_ylabel('Sharpe Ratio')
        ax_scatter.invert_xaxis() # 回撤越小越好，所以在右边

        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        
        save_path = os.path.join(self.output_dir, 'compare_risk_profile.png')
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   🖼️ Saved Risk Chart: {save_path}")