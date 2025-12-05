import pandas as pd
import numpy as np
import os
from scipy import stats

# ==========================================
# 1. 配置路径
# ==========================================
BASE_DATA_DIR = os.path.join(os.getcwd(), 'data') 

FILE_PATHS = {
    'options': os.path.join(BASE_DATA_DIR, 'IBIT_Active_Options.csv'),
    'spot': os.path.join(BASE_DATA_DIR, 'IBIT_Spot_Data.csv'),
    'dvol': os.path.join(BASE_DATA_DIR, 'DERIBIT_DVOL_1D.csv'),
    'rates': os.path.join(BASE_DATA_DIR, 'IRX_CACHE.csv')
}

def load_spot_data():
    try:
        print(f"   正在读取现货数据: {FILE_PATHS['spot']}")
        df = pd.read_csv(FILE_PATHS['spot'])
        df['Date'] = pd.to_datetime(df['Date']).dt.normalize()
        df = df.sort_values('Date')
        col_name = 'Spot_Close' if 'Spot_Close' in df.columns else 'Close'
        return df.set_index('Date')[col_name]
    except Exception as e:
        print(f"❌ 无法加载现货数据: {e}")
        return None

def load_dvol_data():
    """加载并清洗 DVOL 数据"""
    try:
        df = pd.read_csv(FILE_PATHS['dvol'])
        # 处理时间戳
        df['Date'] = pd.to_datetime(df['time'], unit='s').dt.normalize()
        # DVOL 原数据通常是 50 代表 50%，转为小数 0.50
        df['DVOL'] = df['close'] / 100.0
        return df.set_index('Date')['DVOL']
    except Exception as e:
        print(f"❌ 无法加载 DVOL 数据: {e}")
        return None

def process_chunk(chunk, spot_series, dvol_series):
    """处理单个数据块，增加 DVOL 匹配"""
    chunk['Date'] = pd.to_datetime(chunk['Date']).dt.normalize()
    valid_liquidity = (chunk['BidSize'] > 0) & (chunk['AskSize'] > 0)
    chunk = chunk[valid_liquidity].copy()
    # 1. 匹配 Spot
    if spot_series is not None:
        chunk['Spot'] = chunk['Date'].map(spot_series)
    else:
        chunk['Spot'] = np.nan

    # 2. 匹配 DVOL
    if dvol_series is not None:
        chunk['DVOL_Level'] = chunk['Date'].map(dvol_series)
    else:
        chunk['DVOL_Level'] = np.nan

    # 3. 过滤
    # 解析 Expiration
    chunk['ExpirationStr'] = chunk['Symbol'].apply(lambda x: x.split('|')[1])
    chunk['Expiration'] = pd.to_datetime(chunk['ExpirationStr'], format='%Y%m%d')
    chunk['DTE'] = (chunk['Expiration'] - chunk['Date']).dt.days
    
    valid_rows = chunk.dropna(subset=['Bid', 'Ask', 'ImpliedVolatility', 'Spot', 'Strike', 'DVOL_Level']).copy()
    valid_rows = valid_rows[(valid_rows['DTE'] >= 20) & (valid_rows['DTE'] <= 40)]
    
    if valid_rows.empty: return None

    # 4. 计算指标
    valid_rows['Mid'] = (valid_rows['Bid'] + valid_rows['Ask']) / 2
    valid_rows['Spread_Pct'] = (valid_rows['Ask'] - valid_rows['Bid']) / valid_rows['Mid']
    valid_rows['Moneyness'] = valid_rows['Strike'] / valid_rows['Spot']
    
    return valid_rows[['Date', 'OptionType', 'Moneyness', 'ImpliedVolatility', 'Spread_Pct', 'DVOL_Level']]

def analyze_regime(df_regime, regime_name):
    """辅助函数：分析特定 DVOL 区间的参数"""
    print(f"\n --- {regime_name} ---")
    try:
        # A. Skew
        iv_put_90 = df_regime[(df_regime['Moneyness'] >= 0.88) & (df_regime['Moneyness'] <= 0.92) & (df_regime['OptionType']=='P')]['ImpliedVolatility'].mean()
        iv_atm = df_regime[(df_regime['Moneyness'] >= 0.98) & (df_regime['Moneyness'] <= 1.02)]['ImpliedVolatility'].mean()
        skew_val = iv_put_90 - iv_atm
        print(f"   Skew Bias (90% Put - ATM): {skew_val:.4f}")
        
        # B. Spread
        spread_atm = df_regime[(df_regime['Moneyness'] >= 0.98) & (df_regime['Moneyness'] <= 1.02)]['Spread_Pct'].mean()
        spread_otm = df_regime[(df_regime['Moneyness'] >= 0.88) & (df_regime['Moneyness'] <= 0.92) & (df_regime['OptionType']=='P')]['Spread_Pct'].mean()
        print(f"   ATM Spread:     {spread_atm:.2%}")
        print(f"   OTM Put Spread: {spread_otm:.2%}")
        
        return skew_val, spread_atm, spread_otm
    except:
        print("   (数据不足)")
        return None

def calibrate_full_model():
    print(f"🚀 开始分层校准 (Stratified Calibration)...")
    
    spot_series = load_spot_data()
    dvol_series = load_dvol_data()
    if spot_series is None or dvol_series is None: return

    chunk_size = 100000 
    processed_chunks = []
    
    try:
        reader = pd.read_csv(FILE_PATHS['options'], iterator=True, chunksize=chunk_size)
        for i, chunk in enumerate(reader):
            print(f"   处理块 {i+1}...", end='\r')
            processed_df = process_chunk(chunk, spot_series, dvol_series)
            if processed_df is not None:
                processed_chunks.append(processed_df)
                
        print("\n✅ 读取完成，开始分层分析...")
        if not processed_chunks: return

        df_all = pd.concat(processed_chunks, ignore_index=True)
        
        # 定义 DVOL 区间
        # Low: < 50%
        # Mid: 50% - 70%
        # High: > 70%
        
        df_low = df_all[df_all['DVOL_Level'] < 0.50]
        df_mid = df_all[(df_all['DVOL_Level'] >= 0.50) & (df_all['DVOL_Level'] < 0.70)]
        df_high = df_all[df_all['DVOL_Level'] >= 0.70]
        
        print(f"\n样本分布: Low={len(df_low)}, Mid={len(df_mid)}, High={len(df_high)}")
        
        # 分别分析
        if not df_low.empty: analyze_regime(df_low, "Low Vol Regime (DVOL < 50%)")
        if not df_mid.empty: analyze_regime(df_mid, "Mid Vol Regime (50% <= DVOL < 70%)")
        if not df_high.empty: analyze_regime(df_high, "High Vol Regime (DVOL >= 70%)")
        
        # 全局分析 (Benchmark)
        analyze_regime(df_all, "Global Average")

    except Exception as e:
        print(f"❌ 运行出错: {e}")

if __name__ == "__main__":
    calibrate_full_model()