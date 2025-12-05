import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import yfinance as yf
import os
import sys
from scipy.stats import norm
from matplotlib.ticker import FuncFormatter

# ==========================================
# 1. 配置区域 (Config)
# ==========================================
class Config:
    INITIAL_CAPITAL = 100000.0
    DATA_FOLDER = 'data'
    TBL_FOLDER = 'tbl'
    PIC_FOLDER = 'pic'

# ==========================================
# 2. 动态 Skew 计算引擎
# ==========================================
def get_dynamic_skew(dvol):
    """
    根据当前的 DVOL 值，动态计算 Skew (偏斜值)。
    逻辑：市场越恐慌(DVOL高)，OTM Put 相比 ATM 就越贵。
    """
    base_skew = 0.02
    panic_threshold = 0.60
    panic_factor = 0.20
    panic_premium = max(0.0, (dvol - panic_threshold) * panic_factor)
    return base_skew + panic_premium

# ==========================================
# 3. 数学工具 (BSM Pricing)
# ==========================================
def bsm_price(S, K, T_days, r, sigma, option_type='call'):
    if T_days <= 0:
        return max(0.0, S - K) if option_type == 'call' else max(0.0, K - S)

    T = T_days / 365.0
    if sigma <= 0: return max(0.0, S - K) if option_type == 'call' else max(0.0, K - S)

    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if option_type == 'call':
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    elif option_type == 'put':
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return 0.0

# ==========================================
# 4. 数据加载 (含 RV 和 Gap 计算)
# ==========================================
def get_data_path(filename):
    base_dirs = [os.getcwd(), os.path.dirname(os.path.abspath(__file__))]
    for d in base_dirs:
        path = os.path.join(d, Config.DATA_FOLDER, filename)
        if os.path.exists(path): return path
    os.makedirs(os.path.join(os.getcwd(), Config.DATA_FOLDER), exist_ok=True)
    raise FileNotFoundError(f"找不到 {filename}，请确保它在 {Config.DATA_FOLDER} 文件夹里")

def load_market_data():
    print("📊 [Data] Loading & Processing...")
    # 1. DVOL
    dvol = pd.read_csv(get_data_path('DERIBIT_DVOL_1D.csv'))
    dvol['date'] = pd.to_datetime(dvol['time'], unit='s').dt.normalize()
    dvol['sigma'] = dvol['close'] / 100.0
    dvol = dvol[['date', 'sigma']]

    # 2. BTC & Rates
    cache_btc = os.path.join(Config.DATA_FOLDER, 'BTC_USD_CACHE.csv')
    cache_irx = os.path.join(Config.DATA_FOLDER, 'IRX_CACHE.csv')
    
    if os.path.exists(cache_btc) and os.path.exists(cache_irx):
        print("   Reading local cache...")
        btc = pd.read_csv(cache_btc, index_col=0, parse_dates=True)
        irx = pd.read_csv(cache_irx, index_col=0, parse_dates=True)
    else:
        print("   Downloading from Yahoo...")
        start = dvol['date'].min().strftime('%Y-%m-%d')
        end = pd.Timestamp.now().strftime('%Y-%m-%d')
        try:
            btc = yf.download("BTC-USD", start=start, end=end, progress=False)
            if isinstance(btc.columns, pd.MultiIndex): btc = btc['Close']
            else: btc = btc[['Close']]
            btc.columns = ['price']
            
            irx = yf.download("^IRX", start=start, end=end, progress=False)
            if isinstance(irx.columns, pd.MultiIndex): irx = irx['Close']
            else: irx = irx[['Close']]
            irx.columns = ['r']
            
            btc.to_csv(cache_btc)
            irx.to_csv(cache_irx)
        except Exception as e:
            print(f"Error downloading: {e}")
            raise

    irx['r'] = irx['r'] / 100.0
    irx = irx.asfreq('D').ffill()
    if btc.index.tz is not None: btc.index = btc.index.tz_localize(None)
    if irx.index.tz is not None: irx.index = irx.index.tz_localize(None)
    
    btc = btc.reset_index().rename(columns={'index':'date', 'Date':'date'})
    irx = irx.reset_index().rename(columns={'index':'date', 'Date':'date'})
    
    df = pd.merge(btc, irx, on='date', how='inner')
    df = pd.merge(df, dvol, on='date', how='inner')
    df = df.sort_values('date').reset_index(drop=True)

    # --- [关键升级] 计算历史波动率 (RV) 和 溢价 (Gap) ---
    # RV = 过去30天对数收益率的标准差 * sqrt(365)
    df['log_ret'] = np.log(df['price'] / df['price'].shift(1))
    df['rv_30'] = df['log_ret'].rolling(window=30).std() * np.sqrt(365)
    
    # Gap = DVOL (Implied) - RV (Realized)
    # Gap > 0: IV贵 (卖方有利)
    # Gap < 0: IV便宜 (买方有利)
    df['vol_gap'] = df['sigma'] - df['rv_30']
    
    df.dropna(inplace=True)
    df.reset_index(drop=True, inplace=True)
    
    print(f"✅ 数据处理完成: {len(df)} 行。Avg Gap: {df['vol_gap'].mean():.2%}")
    return df

# ==========================================
# 5. 策略基类
# ==========================================
class BaseStrategy:
    def __init__(self, initial_capital):
        self.cash = initial_capital
        self.btc = 0.0
        self.positions = [] 
        self.history = []

    def run(self, df):
        for _, row in df.iterrows():
            for i in range(len(self.positions)-1, -1, -1):
                pos = self.positions[i]
                pos['days_left'] -= 1
                if pos['days_left'] <= 0:
                    self._settle(pos, row['price'])
                    self.positions.pop(i)
            self.next_signal(row)
            self._record(row)

    def _settle(self, pos, spot):
        payoff = 0
        if pos['type'] == 'call': payoff = max(0, spot - pos['strike'])
        elif pos['type'] == 'put': payoff = max(0, pos['strike'] - spot)
        
        if payoff > 0:
            if pos['side'] == 'short': self.cash -= payoff * pos['size']
            else: self.cash += payoff * pos['size']

    def _record(self, row):
        spot, r, sigma = row['price'], row['r'], row['sigma']
        opt_val = 0
        for pos in self.positions:
            p = bsm_price(spot, pos['strike'], pos['days_left'], r, sigma, pos['type'])
            if pos['side'] == 'short': opt_val -= p * pos['size']
            else: opt_val += p * pos['size']
        equity = self.cash + (self.btc * spot) + opt_val
        
        # 记录 Gap 方便 debug
        gap = row.get('vol_gap', 0)
        self.history.append({'date': row['date'], 'equity': equity, 'spot': spot, 'gap': gap})

    def buy_spot(self, price, pct=1.0):
        if self.cash > 10:
            amt = self.cash * pct
            self.btc += amt / price
            self.cash -= amt

    def sell_option(self, strike, days, size, premium, opt_type):
        net = (premium * size) * 0.98
        self.cash += net
        self.positions.append({'type': opt_type, 'side':'short', 'strike': strike, 'days_left': days, 'size': size})

    def buy_option(self, strike, days, size, premium, opt_type):
        cost = (premium * size) * 1.02
        self.cash -= cost
        self.positions.append({'type': opt_type, 'side':'long', 'strike': strike, 'days_left': days, 'size': size})
    
    def next_signal(self, row): pass

# ==========================================
# 6. 策略集合 (含变色龙)
# ==========================================

class BuyHoldStrategy(BaseStrategy):
    def next_signal(self, row):
        if self.btc == 0 and self.cash > 0: self.buy_spot(row['price'])

class CoveredCallStrategy(BaseStrategy):
    def __init__(self, capital, days=30, otm=1.10):
        super().__init__(capital)
        self.days = days
        self.otm = otm
    def next_signal(self, row):
        if self.btc == 0: self.buy_spot(row['price'])
        if self.btc > 0 and not self.positions:
            strike = row['price'] * self.otm
            vol = row['sigma'] 
            prem = bsm_price(row['price'], strike, self.days, row['r'], vol, 'call')
            self.sell_option(strike, self.days, self.btc, prem, 'call')

class CashSecuredPutStrategy(BaseStrategy):
    def __init__(self, capital, days=30, otm=0.90):
        super().__init__(capital)
        self.days = days
        self.otm = otm
    def next_signal(self, row):
        if not self.positions:
            strike = row['price'] * self.otm
            current_skew = get_dynamic_skew(row['sigma'])
            vol = row['sigma'] + current_skew
            prem = bsm_price(row['price'], strike, self.days, row['r'], vol, 'put')
            if self.cash > 0:
                size = self.cash / strike
                if size > 0.001: self.sell_option(strike, self.days, size, prem, 'put')

class CollarStrategy(BaseStrategy):
    def __init__(self, capital, days=30, protect=0.90, cap=1.10):
        super().__init__(capital)
        self.days = days
        self.protect = protect
        self.cap = cap
    def next_signal(self, row):
        price = row['price']
        # 现金再平衡
        total_equity = self.cash + self.btc * price
        target_cash = total_equity * 0.05
        if self.cash < target_cash:
            shortfall = target_cash - self.cash
            if self.btc * price > shortfall:
                self.btc -= shortfall / price
                self.cash += shortfall

        if self.btc == 0 and self.cash > 0:
            self.buy_spot(price, pct=0.95)
            
        if self.btc > 0 and not self.positions:
            k_put = price * self.protect
            k_call = price * self.cap
            skew_put = get_dynamic_skew(row['sigma'])
            vol_put = row['sigma'] + skew_put
            p_put = bsm_price(price, k_put, self.days, row['r'], vol_put, 'put')
            vol_call = row['sigma']
            p_call = bsm_price(price, k_call, self.days, row['r'], vol_call, 'call')
            cost = (p_put * 1.02 - p_call * 0.98) * self.btc
            if self.cash > cost:
                self.buy_option(k_put, self.days, self.btc, p_put, 'put')
                self.sell_option(k_call, self.days, self.btc, p_call, 'call')
# ==========================================
# Wheel Strategy (滚雪球)
# ==========================================
class WheelStrategy(BaseStrategy):
    def __init__(self, initial_capital, days=30, put_otm=0.90, call_otm=1.10):
        super().__init__(initial_capital)
        self.days = days
        self.put_otm = put_otm
        self.call_otm = call_otm
        self.stage = "CSP" # 初始状态: 卖Put

    def _settle(self, pos, spot):
        """
        【核心重写】实物交割逻辑 (Physical Settlement)
        """
        strike = pos['strike']
        size = pos['size']
        otype = pos['type']
        
        # 1. Put 被行权 -> 被迫买入 BTC
        if otype == 'put' and spot < strike:
            cost = strike * size
            # 确保现金足够 (虽然开仓时算过，但为了安全再检查)
            if self.cash >= cost: 
                self.cash -= cost
                self.btc += size
                # 状态切换：拿到货了，下次改卖 Call
                self.stage = "CC" 
            else:
                # 及其罕见情况：钱不够接盘 (理论上CSP不该发生)，只能现金强平
                loss = (strike - spot) * size
                self.cash -= loss

        # 2. Call 被行权 -> 被迫卖出 BTC
        elif otype == 'call' and spot > strike:
            revenue = strike * size
            # 确保有货可卖
            if self.btc >= size:
                self.btc -= size
                self.cash += revenue
                # 状态切换：货卖了，下次改卖 Put
                self.stage = "CSP"
            else:
                # 及其罕见情况：没货被行权 (裸卖空)，现金赔付
                loss = (spot - strike) * size
                self.cash -= loss
        
        # 3. 没被行权 -> 什么都不做，白赚权利金 (权利金在开仓时已经进了 self.cash)
        else:
            pass 
            # 状态维持不变：
            # 如果是 CSP 没跌破，继续持有现金，下次继续卖 Put
            # 如果是 CC 没涨破，继续持有 BTC，下次继续卖 Call

    def next_signal(self, row):
        # 只有空仓时才开新仓
        if len(self.positions) > 0:
            return

        price = row['price']
        
        # --- 阶段 A: 手里有钱 (或者处于 CSP 阶段) ---
        # 逻辑：持有现金 -> 卖 Put
        if self.stage == "CSP":
            # 确保现金归位 (如果因为某些原因持有少量碎币，卖掉换钱，保证全额现金担保)
            # (可选优化：如果你想保留碎币也可以，这里为了纯粹性，建议全转现金)
            if self.btc > 0.001: 
                self.cash += self.btc * price
                self.btc = 0
                
            strike = price * self.put_otm
            
            # 动态 Skew
            skew = get_dynamic_skew(row['sigma'])
            vol = row['sigma'] + skew
            prem = bsm_price(price, strike, self.days, row['r'], vol, 'put')
            
            if self.cash > 0:
                size = self.cash / strike # 全额担保
                if size > 0.001:
                    self.sell_option(strike, self.days, size, prem, 'put')

        # --- 阶段 B: 手里有币 (或者处于 CC 阶段) ---
        # 逻辑：持有现货 -> 卖 Call
        elif self.stage == "CC":
            # 确保有币 (如果没有币，可能是刚刚被行权了，状态机逻辑出错，强制切回 CSP)
            if self.btc < 0.001:
                self.stage = "CSP"
                return

            strike = price * self.call_otm
            
            # Call 用原始波动率
            vol = row['sigma']
            prem = bsm_price(price, strike, self.days, row['r'], vol, 'call')
            
            self.sell_option(strike, self.days, self.btc, prem, 'call')

# ==========================================
# --- [新增] 变色龙策略 ---
# ==========================================
class ChameleonStrategy(BaseStrategy):
    def __init__(self, capital, days=30):
        super().__init__(capital)
        self.days = days

    def next_signal(self, row):
        # 如果有持仓，躺平
        if len(self.positions) > 0:
            return

        # 现金再平衡
        price = row['price']
        total_equity = self.cash + self.btc * price
        target_cash = total_equity * 0.05
        if self.cash < target_cash:
            shortfall = target_cash - self.cash
            if self.btc * price > shortfall:
                self.btc -= shortfall / price
                self.cash += shortfall

        # 核心判断
        gap = row['vol_gap']
        
        # 1. 恐慌溢价区 (Gap > 15%): 全力卖 Put
        if gap > 0.15:
            # 清空现货转现金
            if self.btc > 0: 
                self.cash += self.btc * price
                self.btc = 0
            
            strike = price * 0.90
            skew = get_dynamic_skew(row['sigma'])
            vol = row['sigma'] + skew
            prem = bsm_price(price, strike, self.days, row['r'], vol, 'put')
            
            if self.cash > 0:
                size = self.cash / strike
                if size > 0.001: self.sell_option(strike, self.days, size, prem, 'put')

        # 2. 波动率低估区 (Gap < 0%): 买保护 (Collar)
        elif gap < 0:
            if self.btc == 0 and self.cash > 0:
                self.buy_spot(price, pct=0.95)
            
            if self.btc > 0:
                k_put = price * 0.95
                k_call = price * 1.10
                skew_put = get_dynamic_skew(row['sigma'])
                p_put = bsm_price(price, k_put, self.days, row['r'], row['sigma']+skew_put, 'put')
                p_call = bsm_price(price, k_call, self.days, row['r'], row['sigma'], 'call')
                
                cost = (p_put * 1.02 - p_call * 0.98) * self.btc
                if self.cash > cost:
                    self.buy_option(k_put, self.days, self.btc, p_put, 'put')
                    self.sell_option(k_call, self.days, self.btc, p_call, 'call')

        # 3. 正常区: 备兑 (Covered Call)
        else:
            if self.btc == 0 and self.cash > 0:
                self.buy_spot(price, pct=0.95)
            
            if self.btc > 0:
                strike = price * 1.10
                prem = bsm_price(price, strike, self.days, row['r'], row['sigma'], 'call')
                self.sell_option(strike, self.days, self.btc, prem, 'call')

# ==========================================
# 7. 分析与画图
# ==========================================
def run_analytics(strategies):
    print("\n📊 [Analytics] 生成报告...")
    os.makedirs(Config.TBL_FOLDER, exist_ok=True)
    os.makedirs(Config.PIC_FOLDER, exist_ok=True)
    
    metrics_list = []
    data_eq = {}

    for name, strat in strategies.items():
        if not strat.history: continue
        df = pd.DataFrame(strat.history).set_index('date')
        data_eq[name] = df['equity']
        
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
        
        dd = (series - series.cummax()) / series.cummax()
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

    # 打印表格
    df_metrics = pd.DataFrame(metrics_list)
    if not df_metrics.empty:
        print("\n" + "="*100)
        print(f"{'PERFORMANCE SUMMARY (Chameleon Included)':^100}")
        print("="*100)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        print(df_metrics.to_string(index=False))
        print("="*100 + "\n")
        
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
        plt.savefig(os.path.join(Config.TBL_FOLDER, 'summary_table.png'), bbox_inches='tight')
        plt.close()

    # 净值曲线
    df_res = pd.DataFrame(data_eq).fillna(method='ffill').dropna()
    if not df_res.empty:
        plt.figure(figsize=(12, 6))
        for col in df_res.columns:
            ls = '--' if 'Hold' in col else '-'
            lw = 2.5 if 'Chameleon' in col else 1.5
            plt.plot(df_res.index, df_res[col], label=col, linestyle=ls, linewidth=lw)
        plt.title("Equity Curve (Including Chameleon)")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda x, p: f'${x:,.0f}'))
        plt.savefig(os.path.join(Config.PIC_FOLDER, 'equity_curve.png'))
        
        # 画 Gap 历史图
        first_strat = list(strategies.values())[0]
        if first_strat.history:
            df_gap = pd.DataFrame(first_strat.history).set_index('date')['gap']
            plt.figure(figsize=(12, 4))
            plt.plot(df_gap.index, df_gap, color='orange', label='Vol Gap (DVOL - RV)')
            plt.axhline(0.15, color='red', linestyle='--', label='Panic Threshold (0.15)')
            plt.axhline(0.0, color='green', linestyle='--', label='Cheap Vol Threshold (0.0)')
            plt.fill_between(df_gap.index, df_gap, 0.15, where=(df_gap>0.15), color='red', alpha=0.3)
            plt.fill_between(df_gap.index, df_gap, 0, where=(df_gap<0), color='green', alpha=0.3)
            plt.title("Market Regime: Volatility Gap")
            plt.legend()
            plt.savefig(os.path.join(Config.PIC_FOLDER, 'regime_gap.png'))
            
        print(f"✅ Reports saved to {Config.PIC_FOLDER} and {Config.TBL_FOLDER}")

# ==========================================
# 8. 主程序
# ==========================================
def main():
    try:
        df = load_market_data()
    except Exception as e:
        print(f"Error: {e}")
        return

    strategies = {
        "Buy & Hold": BuyHoldStrategy(Config.INITIAL_CAPITAL),
        
        "Covered Call (30D, 10%)": CoveredCallStrategy(
            Config.INITIAL_CAPITAL, days=30, otm=1.10
        ),
        
        "Cash-Secured Put (30D, 10%)": CashSecuredPutStrategy(
            Config.INITIAL_CAPITAL, days=30, otm=0.90
        ),
        
        "Collar (30D, -5%/+2%)": CollarStrategy(
            Config.INITIAL_CAPITAL, days=30, protect=0.95, cap=1.02
        ),
        
        # 我们的主角：变色龙
        "Chameleon (Smart Switch)": ChameleonStrategy(Config.INITIAL_CAPITAL),

        "The Wheel (0.9 Put / 1.1 Call)": WheelStrategy(
            Config.INITIAL_CAPITAL, days=30, put_otm=0.90, call_otm=1.10
        )
    }

    print("\n🚀 Running Strategies...")
    for name, strat in strategies.items():
        print(f"   Running: {name}...")
        strat.run(df)
    
    run_analytics(strategies)

if __name__ == "__main__":
    main()