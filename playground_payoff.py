import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os

# -----------------------------------------------------------
# 配置与风格
# -----------------------------------------------------------
# 使用更现代、专业的配色风格
sns.set_theme(style="whitegrid")
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans', 'Liberation Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 300

OUTPUT_DIR = 'pic'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 定义颜色常量
COLOR_BNH = '#34495e'    # 深灰 (基准)
COLOR_CSP = '#3498db'    # 蓝色 (CSP)
COLOR_WHEEL = '#2ecc71'  # 绿色 (Wheel)
COLOR_HIGH = '#e74c3c'   # 红色 (High Vol)
COLOR_LOW = '#27ae60'    # 绿色 (Low Vol)
COLOR_FILL = '#2ecc71'   # 填充色

def plot_csp_vs_buy_hold():
    """
    图一：CSP vs Buy & Hold (The Cushion / 安全气囊)
    展示 CSP 如何在下跌时提供保护，但在大涨时封顶。
    """
    print("🎨 Drawing Chart 1: CSP Safety Cushion...")
    
    # 模拟数据
    price_change = np.linspace(-30, 30, 500) # 价格变化百分比
    
    # Buy & Hold: 1:1 线性盈亏
    pnl_bnh = price_change
    
    # CSP: 
    # 假设卖出 OTM Put，权利金 yield = 3%，Strike 在当前价格 -5% 处
    # 如果跌幅 < 5%: 赚 3%
    # 如果跌幅 > 5%: 开始亏损，但比 B&H 少亏 (3% + 5% = 8% 的缓冲)
    premium = 3.0
    strike_dist = 5.0
    
    pnl_csp = []
    for x in price_change:
        if x >= -strike_dist:
            pnl_csp.append(premium)
        else:
            # 跌穿行权价：(当前跌幅 - 行权价跌幅) + 权利金
            # 比如跌 10% (x=-10): (-10 - (-5)) + 3 = -2%
            loss = (x + strike_dist) + premium
            pnl_csp.append(loss)
            
    pnl_csp = np.array(pnl_csp)

    # 绘图
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # 画线
    ax.plot(price_change, pnl_bnh, label='Buy & Hold (BTC)', color=COLOR_BNH, linestyle='--', linewidth=2, alpha=0.7)
    ax.plot(price_change, pnl_csp, label='CSP Strategy', color=COLOR_CSP, linewidth=3)
    
    # 填充“安全气囊”区域 (仅在下跌区域填充)
    mask = price_change < 0
    ax.fill_between(price_change[mask], pnl_csp[mask], pnl_bnh[mask], 
                    color=COLOR_FILL, alpha=0.2, label='Safety Buffer (Premium)')
    
    # 关键点标注
    ax.axhline(0, color='black', linewidth=0.8, alpha=0.5)
    ax.axvline(0, color='black', linewidth=0.8, alpha=0.5)
    
    # 文字说明
    ax.text(-20, -10, "CSP Loses Less\n(Downside Protection)", color=COLOR_CSP, fontsize=10, fontweight='bold')
    ax.text(15, 5, "Upside Capped\n(Yield Only)", color=COLOR_CSP, fontsize=10, fontweight='bold', ha='center')
    
    # 装饰
    ax.set_title("Concept 1: The 'Safety Airbag' (CSP vs. Buy & Hold)", fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel("Bitcoin Price Change (%)", fontsize=11)
    ax.set_ylabel("Strategy Return (%)", fontsize=11)
    ax.legend(loc='upper left', frameon=True, shadow=True)
    ax.set_xlim(-30, 30)
    ax.set_ylim(-30, 30)
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'payoff_1_csp_safety.png'))
    plt.close()


def plot_wheel_repair():
    """
    图二：The Wheel (The Repair / 被套自救)
    展示在高位接货后，如何通过卖 Call 降低回本点。
    """
    print("🎨 Drawing Chart 2: Wheel Repair Mechanism...")
    
    # 场景：成本价 60000
    cost_basis = 60000
    # 价格范围：50k - 70k
    prices = np.linspace(50000, 70000, 500)
    
    # 1. 死拿回本线 (Bag Holding)
    pnl_hold = prices - cost_basis
    
    # 2. Wheel (Covered Call)
    # 假设卖出 Strike=62000 的 Call，权利金=1500
    call_strike = 62000
    call_premium = 1500
    
    pnl_wheel = []
    for p in prices:
        # 股票盈亏 + 权利金
        stock_pnl = p - cost_basis
        
        # 期权盈亏 (卖方)
        if p <= call_strike:
            opt_pnl = call_premium # 全收
        else:
            # 被行权，赔付差价
            opt_pnl = call_premium - (p - call_strike)
            
        pnl_wheel.append(stock_pnl + opt_pnl)
    
    pnl_wheel = np.array(pnl_wheel)
    
    # 绘图
    fig, ax = plt.subplots(figsize=(10, 6))
    
    ax.plot(prices, pnl_hold, label='Just Holding (Waiting)', color=COLOR_BNH, linestyle='--', linewidth=2, alpha=0.6)
    ax.plot(prices, pnl_wheel, label='Wheel (Selling Calls)', color=COLOR_WHEEL, linewidth=3)
    
    # 零轴
    ax.axhline(0, color='black', linewidth=1)
    
    # 标注回本点 (Break-even)
    be_hold = cost_basis
    be_wheel = cost_basis - call_premium
    
    # 画回本点垂直线
    ax.axvline(be_hold, color=COLOR_BNH, linestyle=':', alpha=0.5)
    ax.axvline(be_wheel, color=COLOR_WHEEL, linestyle=':', alpha=0.5)
    
    # 标注文字
    ax.annotate(f'Original Break-even\n${be_hold:,}', xy=(be_hold, 0), xytext=(be_hold+2000, -2000),
                arrowprops=dict(facecolor=COLOR_BNH, shrink=0.05, width=1, headwidth=6),
                fontsize=9, color=COLOR_BNH)
    
    ax.annotate(f'Lowered Break-even\n${be_wheel:,}', xy=(be_wheel, 0), xytext=(be_wheel-6000, 2000),
                arrowprops=dict(facecolor=COLOR_WHEEL, shrink=0.05, width=1, headwidth=6),
                fontsize=10, fontweight='bold', color=COLOR_WHEEL)
    
    # 填充优势区域
    ax.fill_between(prices, pnl_wheel, pnl_hold, where=(prices < call_strike),
                    color=COLOR_WHEEL, alpha=0.15, label='Income Generated')

    ax.set_title("Concept 2: The 'Repair' (Lowering Cost Basis)", fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel("Bitcoin Price ($)", fontsize=11)
    ax.set_ylabel("Profit / Loss ($)", fontsize=11)
    
    # 格式化 X 轴
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x/1000:.0f}k'))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    
    ax.legend(loc='upper left', frameon=True, shadow=True)
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'payoff_2_wheel_repair.png'))
    plt.close()


def plot_smart_wheel_morphing():
    """
    图三：Smart Wheel (Morphing / 变色龙形态)
    展示策略在三种不同 Regime 下的形态变化。
    """
    print("🎨 Drawing Chart 3: Smart Wheel Morphing...")
    
    x = np.linspace(-20, 20, 500)
    
    # 1. Low Vol (Bull Mode) -> Long Spot
    # 纯现货，无封顶
    y_bull = x 
    
    # 2. Normal Vol (Balance Mode) -> Standard CSP
    # 卖 ATM/OTM Put，赚取适中权利金，有一定缓冲
    premium_norm = 2.0
    strike_norm_dist = 2.0
    y_norm = np.where(x > -strike_norm_dist, premium_norm, x + strike_norm_dist + premium_norm)
    
    # 3. High Vol (Panic Mode) -> Deep OTM Put
    # 极度保守，权利金较低(相对)，但安全垫极厚
    premium_high = 1.0 # 假设为了安全卖的很远，权利金其实不如 ATM 高
    strike_high_dist = 10.0 # 巨大的安全垫
    y_high = np.where(x > -strike_high_dist, premium_high, x + strike_high_dist + premium_high)
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # 绘图
    ax.plot(x, y_bull, label='Low Vol (Bull Mode): Uncapped Upside', color=COLOR_LOW, linewidth=3)
    ax.plot(x, y_norm, label='Normal Vol: Stable Yield', color=COLOR_CSP, linewidth=2.5, linestyle='--')
    ax.plot(x, y_high, label='High Vol (Panic Mode): Max Protection', color=COLOR_HIGH, linewidth=2.5, linestyle='-.')
    
    # 零轴
    ax.axhline(0, color='black', linewidth=0.8, alpha=0.3)
    ax.axvline(0, color='black', linewidth=0.8, alpha=0.3)
    
    # 添加标注箭头
    ax.annotate('Participate in Rally', xy=(15, 15), xytext=(10, 2),
                arrowprops=dict(facecolor=COLOR_LOW, arrowstyle='->', lw=2),
                color=COLOR_LOW, fontweight='bold')
    
    ax.annotate('Deep Safety Buffer', xy=(-8, 1), xytext=(-15, 5),
                arrowprops=dict(facecolor=COLOR_HIGH, arrowstyle='->', lw=2),
                color=COLOR_HIGH, fontweight='bold')
    
    ax.set_title("Concept 3: The 'Chameleon' (Adapting to Regimes)", fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel("Market Move (%)", fontsize=11)
    ax.set_ylabel("Strategy Return (%)", fontsize=11)
    
    ax.legend(loc='lower right', frameon=True, shadow=True, fontsize=10)
    ax.set_xlim(-20, 20)
    ax.set_ylim(-15, 20)
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'payoff_3_smart_wheel_regime.png'))
    plt.close()

if __name__ == "__main__":
    print("🚀 Generating Strategy Payoff Diagrams...")
    plot_csp_vs_buy_hold()
    plot_wheel_repair()
    plot_smart_wheel_morphing()
    print(f"✅ All diagrams saved to {os.path.abspath(OUTPUT_DIR)}")