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
    'spot': os.path.join(BASE_DATA_DIR, 'IBIT_Spot_Data.csv'), # <--- 修正为 IBIT 现货
    'dvol': os.path.join(BASE_DATA_DIR, 'DERIBIT_DVOL_1D.csv'),
    'rates': os.path.join(BASE_DATA_DIR, 'IRX_CACHE.csv')
}

def load_spot_data():
    """加载 IBIT 现货价格"""
    try:
        print(f"   正在读取现货数据: {FILE_PATHS['spot']}")
        df = pd.read_csv(FILE_PATHS['spot'])
        
        # 清洗日期
        df['Date'] = pd.to_datetime(df['Date']).dt.normalize()
        
        # 确保按日期排序
        df = df.sort_values('Date')
        
        # 将 Date 设为索引，返回 Spot_Close 列
        # 注意: IBIT 数据的列名通常是 'Spot_Close' 或 'Close'
        col_name = 'Spot_Close' if 'Spot_Close' in df.columns else 'Close'
        return df.set_index('Date')[col_name]
    except Exception as e:
        print(f"❌ 无法加载现货数据: {e}")
        return None

def process_chunk(chunk, spot_series):
    """处理单个数据块"""
    # 1. 日期处理
    chunk['Date'] = pd.to_datetime(chunk['Date']).dt.normalize()
    
    # 2. 匹配现货价格 (利用索引自动对齐)
    if spot_series is not None:
        chunk['Spot'] = chunk['Date'].map(spot_series)
    else:
        chunk['Spot'] = np.nan

    # 3. 过滤无效数据 (必须有 Spot 才能算 Moneyness)
    # 并且只看 20-40 天到期的合约 (模拟 30D 策略)
    # 先解析 Expiration
    chunk['ExpirationStr'] = chunk['Symbol'].apply(lambda x: x.split('|')[1])
    chunk['Expiration'] = pd.to_datetime(chunk['ExpirationStr'], format='%Y%m%d')
    chunk['DTE'] = (chunk['Expiration'] - chunk['Date']).dt.days
    
    # 筛选条件: 
    # 1. 有价格 (Bid/Ask/IV)
    # 2. 有现货价格 (Spot)
    # 3. DTE 在 20 到 40 天之间 (专注 30D 策略的参数校准)
    valid_rows = chunk.dropna(subset=['Bid', 'Ask', 'ImpliedVolatility', 'Spot', 'Strike']).copy()
    valid_rows = valid_rows[(valid_rows['DTE'] >= 20) & (valid_rows['DTE'] <= 40)]
    
    if valid_rows.empty:
        return None

    # 4. 计算指标
    valid_rows['Mid'] = (valid_rows['Bid'] + valid_rows['Ask']) / 2
    # 相对价差
    valid_rows['Spread_Pct'] = (valid_rows['Ask'] - valid_rows['Bid']) / valid_rows['Mid']
    # 虚值程度
    valid_rows['Moneyness'] = valid_rows['Strike'] / valid_rows['Spot']
    
    return valid_rows[['Date', 'OptionType', 'Moneyness', 'ImpliedVolatility', 'Spread_Pct']]

def calibrate_full_model():
    print(f"🚀 开始全量数据校准 (Corrected Spot Source)...")
    
    # 1. 准备现货数据
    spot_series = load_spot_data()
    if spot_series is None: return

    # 2. 逐块读取
    chunk_size = 100000 
    processed_chunks = []
    
    try:
        reader = pd.read_csv(FILE_PATHS['options'], iterator=True, chunksize=chunk_size)
        
        for i, chunk in enumerate(reader):
            print(f"   正在处理第 {i+1} 块数据...", end='\r')
            processed_df = process_chunk(chunk, spot_series)
            if processed_df is not None:
                processed_chunks.append(processed_df)
                
        print("\n✅ 数据读取完成，开始聚合分析...")
        if not processed_chunks:
            print("❌ 警告：没有符合条件(20-40 DTE)的数据。请检查数据源日期范围。")
            return

        df_all = pd.concat(processed_chunks, ignore_index=True)
        print(f"📊 有效样本: {len(df_all)} 行")

        # 3. 分桶统计
        bins = [0.8, 0.9, 0.98, 1.02, 1.1, 1.2]
        labels = ['Deep Put (80-90%)', 'OTM Put (90-98%)', 'ATM (98-102%)', 'OTM Call (102-110%)', 'Deep Call (>110%)']
        df_all['Bucket'] = pd.cut(df_all['Moneyness'], bins=bins, labels=labels)
        
        summary = df_all.groupby(['Bucket', 'OptionType'])[['ImpliedVolatility', 'Spread_Pct']].mean()
        
        print("\n" + "="*60)
        print(" IBIT Options MicroStruc (30 DTE)")
        print("="*60)
        print(summary)
        print("="*60)

        # 4. 提取参数
        print("\n [Calibration Parameters]")
        
        try:
            # 90% Put IV
            iv_put_90 = df_all[(df_all['Moneyness'] >= 0.88) & (df_all['Moneyness'] <= 0.92) & (df_all['OptionType']=='P')]['ImpliedVolatility'].mean()
            # ATM IV
            iv_atm = df_all[(df_all['Moneyness'] >= 0.98) & (df_all['Moneyness'] <= 1.02)]['ImpliedVolatility'].mean()
            
            skew_val = iv_put_90 - iv_atm
            print(f"1. Skew Bias (90% Put - ATM): {skew_val:.4f}")
        except:
            print("   (无法计算 Skew)")

        try:
            # ATM Spread
            spread_atm = df_all[(df_all['Moneyness'] >= 0.98) & (df_all['Moneyness'] <= 1.02)]['Spread_Pct'].mean()
            # OTM Put Spread
            spread_otm = df_all[(df_all['Moneyness'] >= 0.88) & (df_all['Moneyness'] <= 0.92) & (df_all['OptionType']=='P')]['Spread_Pct'].mean()
            
            print(f"2. Real Transaction Costs")
            print(f"   -> ATM Spread: {spread_atm:.2%}")
            print(f"   -> OTM Put Spread: {spread_otm:.2%}")
        except:
            print("   (无法计算 Spread)")
            
        # 5. DVOL 回归分析 (如果需要)
        # 这里需要加载 DVOL 数据并 merge，如果只是为了获取均值，上面已经够了。
        # 为了简单起见，这里只输出均值参数。

    except FileNotFoundError as e:
        print(f"❌ 文件未找到: {e}")
    except Exception as e:
        print(f"❌ 运行出错: {e}")

if __name__ == "__main__":
    calibrate_full_model()