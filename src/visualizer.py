import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import os
import numpy as np
from .config import Config

# 设置专业金融图表风格
sns.set_theme(style="whitegrid") # 改用白底网格，做表更干净
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['axes.unicode_minus'] = False # 解决负号显示问题

class Visualizer:
    def __init__(self, output_dir='pic'):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        # 专用于存放表格图片的目录
        self.tbl_img_dir = 'tbl'
        os.makedirs(self.tbl_img_dir, exist_ok=True)

    # ===========================
    # 新增功能：表格转图片
    # ===========================
    def save_dataframe_as_image(self, df, filename):
        """
        将 Pandas DataFrame 渲染为干净的图片表格并保存到 tbl/ 目录。
        无标题，纯表格。
        """
        if df.empty:
            print(f"⚠️ Warning: DataFrame is empty, skipping table image generation for {filename}")
            return

        # 计算画布大小：根据行数和列数动态调整
        num_rows, num_cols = df.shape
        figsize = (num_cols * 1.5 + 1, num_rows * 0.4 + 0.5)
        
        fig, ax = plt.subplots(figsize=figsize)
        ax.axis('tight')
        ax.axis('off') # 关闭坐标轴

        # 绘制表格
        table = ax.table(cellText=df.values,
                         colLabels=df.columns,
                         loc='center',
                         cellLoc='center')

        # 美化表格样式
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.2, 1.5) # 调整行列高度和宽度

        # 设置表头颜色和字体加粗
        for (row, col), cell in table.get_celld().items():
            if row == 0:
                cell.set_text_props(weight='bold', color='white')
                cell.set_facecolor('#40466e') # 深蓝灰表头
            else:
                # 斑马纹行首
                if row % 2 == 0:
                    cell.set_facecolor('#f2f2f2') # 浅灰
                else:
                    cell.set_facecolor('white')

        save_path = os.path.join(self.tbl_img_dir, filename)
        # bbox_inches='tight', pad_inches=0.05 确保去掉多余白边
        plt.savefig(save_path, dpi=300, bbox_inches='tight', pad_inches=0.05)
        plt.close()
        print(f"   🖼️ Table Image Saved: {save_path}")

    # ===========================
    # 新增功能：风险指标可视化
    # ===========================
    def plot_risk_comparison(self, risk_df):
        """
        可视化 VaR, CVaR, Skewness, Kurtosis 对比图。
        接收原始数值型的 DataFrame。
        """
        if risk_df.empty: return

        # 创建一个 2x2 的画布
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('Strategy Risk Profile Comparison', fontsize=16, fontweight='bold')
        
        strategies = risk_df.index
        colors = sns.color_palette("viridis", len(strategies))

        # --- 1. Tail Risk (VaR & CVaR) ---
        ax_tail = axes[0, 0]
        # 准备数据：将 VaR/CVaR 转为正数方便画柱状图比较幅度
        var_data = pd.DataFrame({
            'VaR 95%': -risk_df['VaR 95%'],
            'CVaR 95%': -risk_df['CVaR 95%']
        })
        
        var_data.plot(kind='bar', ax=ax_tail, width=0.8, color=['#ff9999', '#cc0000'], edgecolor='black')
        ax_tail.set_title('Left-Tail Risk Magnitude (Lower is Better)', fontweight='bold')
        ax_tail.set_ylabel('Loss Magnitude (Positive representation of %)')
        ax_tail.set_xticklabels(strategies, rotation=45, ha='right')
        ax_tail.legend(['VaR 95% (Probable Loss)', 'CVaR 95% (Extreme Loss)'])
        ax_tail.grid(axis='y', linestyle='--', alpha=0.7)

        # --- 2. Skewness (偏度) ---
        ax_skew = axes[0, 1]
        sns.barplot(x=strategies, y=risk_df['Skewness'], ax=ax_skew, palette=colors)
        ax_skew.set_title('Skewness (Negative = Fat Left Tail)', fontweight='bold')
        ax_skew.axhline(0, color='black', linewidth=1)
        ax_skew.set_ylabel('Skewness Value')
        ax_skew.set_xticklabels(strategies, rotation=45, ha='right')
        # 添加参考区域
        ax_skew.axhspan(-0.5, 0.5, color='gray', alpha=0.1, label='Normal Range')

        # --- 3. Kurtosis (峰度) ---
        ax_kurt = axes[1, 0]
        sns.barplot(x=strategies, y=risk_df['Kurtosis'], ax=ax_kurt, palette=colors)
        ax_kurt.set_title('Kurtosis (Higher = More Extreme Events)', fontweight='bold')
        ax_kurt.axhline(3.0, color='red', linestyle='--', label='Normal Dist. (3.0)')
        ax_kurt.set_ylabel('Kurtosis Value')
        ax_kurt.set_xticklabels(strategies, rotation=45, ha='right')
        ax_kurt.legend()

        # --- 4. Risk-Reward Scatter (Sharpe vs Max DD) ---
        # 这是一个非常经典的机构分析图
        ax_scatter = axes[1, 1]
        sns.scatterplot(data=risk_df, x='Max Drawdown', y='Sharpe', hue=strategies, s=200, palette=colors, ax=ax_scatter)
        
        # 添加标签
        for i, txt in enumerate(strategies):
            ax_scatter.annotate(txt, (risk_df['Max Drawdown'].iloc[i], risk_df['Sharpe'].iloc[i]), 
                                xytext=(5, 5), textcoords='offset points')

        ax_scatter.set_title('Risk-Reward Landscape (Higher & Left is Better)', fontweight='bold')
        ax_scatter.set_xlabel('Max Drawdown (Negative %)')
        ax_scatter.set_ylabel('Sharpe Ratio')
        ax_scatter.grid(True, linestyle='--')
        # 反转 X 轴，让回撤小的在左边
        ax_scatter.invert_xaxis()

        plt.tight_layout(rect=[0, 0.03, 1, 0.95]) # 调整布局以适应总标题
        
        save_path = os.path.join(self.output_dir, 'compare_risk_profile.png')
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   🖼️ Saved Risk Chart: {save_path}")

    # ===========================
    # 原有绘图功能 (保持不变或微调)
    # ===========================
    def plot_equity_comparison(self, combined_df):
        """画出所有策略的净值曲线对比 (Log Scale)"""
        plt.figure(figsize=(14, 7))
        palette = sns.color_palette("husl", len(combined_df.columns))
        
        for i, col in enumerate(combined_df.columns):
            if 'Buy & Hold' in col:
                plt.plot(combined_df.index, combined_df[col], 
                         label=col, color='black', linewidth=2.5, linestyle='--', alpha=0.7)
            else:
                plt.plot(combined_df.index, combined_df[col], label=col, linewidth=2, color=palette[i], alpha=0.9)

        plt.yscale('log')
        plt.title('Strategy Equity Curves Comparison (Log Scale)', fontsize=14, fontweight='bold')
        plt.ylabel('Portfolio Value ($)', fontsize=12)
        plt.legend(loc='upper left', frameon=True, shadow=True)
        plt.grid(True, which='both', linestyle=':', alpha=0.5)
        
        save_path = os.path.join(self.output_dir, 'compare_equity_curves.png')
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   🖼️ Saved Equity Chart: {save_path}")

    def plot_drawdown_comparison(self, combined_df):
        """画出所有策略的水下回撤图"""
        plt.figure(figsize=(14, 6))
        palette = sns.color_palette("husl", len(combined_df.columns))

        for i, col in enumerate(combined_df.columns):
            roll_max = combined_df[col].expanding().max()
            dd = (combined_df[col] - roll_max) / roll_max
            
            plt.plot(combined_df.index, dd, label=col, linewidth=1.5, color=palette[i])
            plt.fill_between(combined_df.index, dd, 0, color=palette[i], alpha=0.1)

        plt.title('Drawdown Comparison (Underwater Plot)', fontsize=14, fontweight='bold')
        plt.ylabel('Drawdown %', fontsize=12)
        plt.ylim(bottom=dd.min()*1.1, top=0.01)
        plt.legend(loc='lower left', frameon=True)
        
        save_path = os.path.join(self.output_dir, 'compare_drawdowns.png')
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"   🖼️ Saved Drawdown Chart: {save_path}")

    def plot_rolling_sharpe(self, combined_df):
        """对比滚动夏普比率"""
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