import pandas as pd
import numpy as np
import yfinance as yf
import os
from .config import Config

def load_market_data():
    print("📊 [Data] Loading & Processing...")
    
    # 确保数据目录存在
    os.makedirs(Config.DATA_FOLDER, exist_ok=True)
    
    # 1. DVOL
    dvol_path = os.path.join(Config.DATA_FOLDER, 'DERIBIT_DVOL_1D.csv')
    if not os.path.exists(dvol_path):
        raise FileNotFoundError(f"找不到 DVOL 数据: {dvol_path}")
        
    dvol = pd.read_csv(dvol_path)
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
    
    # 时区处理
    if btc.index.tz is not None: btc.index = btc.index.tz_localize(None)
    if irx.index.tz is not None: irx.index = irx.index.tz_localize(None)
    
    btc = btc.reset_index().rename(columns={'index':'date', 'Date':'date'})
    irx = irx.reset_index().rename(columns={'index':'date', 'Date':'date'})
    
    # Merge
    df = pd.merge(btc, irx, on='date', how='inner')
    df = pd.merge(df, dvol, on='date', how='inner')
    df = df.sort_values('date').reset_index(drop=True)

    # --- 计算 RV 和 Gap ---
    df['log_ret'] = np.log(df['price'] / df['price'].shift(1))
    df['rv_30'] = df['log_ret'].rolling(window=30).std() * np.sqrt(365)
    df['vol_gap'] = df['sigma'] - df['rv_30']
    
    df.dropna(inplace=True)
    df.reset_index(drop=True, inplace=True)
    
    print(f"✅ 数据处理完成: {len(df)} 行。Avg Gap: {df['vol_gap'].mean():.2%}")
    return df