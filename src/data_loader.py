import pandas as pd
import numpy as np
import yfinance as yf
import os
from config import Config
from regime import RollingPercentileRegime  # ✅ 新增：引入军师

def load_market_data(force_download=False):
    """
    1. 加载 Opus 核心数据
    2. 补充无风险利率
    3. 调用 Regime Engine 计算市场状态 (Low/Normal/High)
    4. 保存清洗后的数据供策略使用
    """
    print("📊 [Data] Pipeline Started...")
    
    # -----------------------------------------------------------
    # 1. 路径检查与目录创建
    # -----------------------------------------------------------
    os.makedirs(Config.DATA_FOLDER, exist_ok=True)
    opus_path = os.path.join(Config.DATA_FOLDER, 'volatility_index.csv')
    
    if not os.path.exists(opus_path):
        raise FileNotFoundError(f"❌ 错误: 找不到 {opus_path}。请确保已将 Opus 项目的 volatility_index.csv 放入 data 文件夹。")

    # -----------------------------------------------------------
    # 2. 加载核心数据 (Opus Volatility Index)
    # -----------------------------------------------------------
    df = pd.read_csv(opus_path)
    df['date'] = pd.to_datetime(df['Date'])
    
    # 关键映射: 适配 BTC_Strat 现有变量名
    df['price'] = df['ibit_spot']       # 策略交易的是 IBIT ETF
    df['sigma'] = df['vol_index']       # 策略使用的隐含波动率 (IV)
    df['btc_price'] = df['btc_close']   # 参考用的 BTC 原价
    
    # -----------------------------------------------------------
    # 3. 补充无风险利率 (Yahoo Finance ^IRX)
    # -----------------------------------------------------------
    cache_irx = os.path.join(Config.DATA_FOLDER, 'IRX_CACHE.csv')
    
    if os.path.exists(cache_irx) and not force_download:
        print("   Loading rates from cache...")
        irx = pd.read_csv(cache_irx, index_col=0, parse_dates=True)
    else:
        print("   Downloading rates from Yahoo...")
        try:
            irx = yf.download("^IRX", start="2018-12-01", progress=False)
            if isinstance(irx.columns, pd.MultiIndex): irx = irx['Close']
            else: irx = irx[['Close']]
            irx.to_csv(cache_irx)
        except Exception:
            print("⚠️ Rate download failed, utilizing flat 4.5% rate.")
            dates = pd.date_range(start='2019-01-01', end=pd.Timestamp.now())
            irx = pd.DataFrame(data={'Close': 4.5}, index=dates)

    irx = irx.reset_index()
    irx.columns = ['date', 'rate_raw']
    if irx['date'].dt.tz is not None: irx['date'] = irx['date'].dt.tz_localize(None)
    
    # 合并利率
    df = pd.merge(df, irx, on='date', how='left')
    df['r'] = df['rate_raw'].ffill().fillna(2.0) / 100.0
    
    # -----------------------------------------------------------
    # 4. 🔥 核心接通：调用 Regime Engine
    # -----------------------------------------------------------
    print("   Calculating Regimes (External Engine)...")
    
    # 实例化引擎：使用 365 天滚动窗口，带迟滞缓冲 (Hysteresis)
    # 进场 High 门槛是 67%，出场是 60%，防止信号在临界点反复横跳
    engine = RollingPercentileRegime(
        window=365, 
        min_periods=90,
        high_enter=0.67, high_exit=0.60,
        low_enter=0.33, low_exit=0.40
    )
    
    # 注入灵魂：生成 regime_signal 列
    df = engine.add_signals(df)
    
    # -----------------------------------------------------------
    # 5. 清理与保存
    # -----------------------------------------------------------
    # 保留 debug 用的中间变量 (如 q_high_enter) 方便画图检查
    cols_to_keep = [
        'date', 'price', 'sigma', 'r', 'regime_signal', 
        'btc_price', 'q_high_enter', 'q_low_enter'
    ]
    
    # 确保列存在再筛选
    available_cols = [c for c in cols_to_keep if c in df.columns]
    final_df = df[available_cols].sort_values('date').reset_index(drop=True)
    
    save_path = os.path.join(Config.DATA_FOLDER, 'BTC_Strat_Data_Ready.csv')
    final_df.to_csv(save_path, index=False)
    
    print(f"✅ Data Ready: {len(final_df)} rows. Saved to {save_path}")
    print("   Regime Distribution:")
    print(final_df['regime_signal'].value_counts())
    
    return final_df

if __name__ == "__main__":
    # 测试代码
    df = load_market_data()
    print("\nSample Data (Tail):")
    print(df[['date', 'sigma', 'regime_signal']].tail(10))