import pandas as pd
import numpy as np
from scipy.stats import norm
import os
from .config import Config

class OptionPricing:
    """
    混合定价引擎 (Hybrid Pricing Engine) - 增强版
    
    特性:
    1. 优先查表 (Market Lookup)：获取真实市场价格 (含 Skew)。
    2. 自动熔断 (Sanity Check)：如果市场价与理论价偏离过大，视为脏数据，回退到 BSM。
    3. 高速缓存 (Caching)：使用字典优化查询速度。
    """
    
    _market_cache = None  # { pd.Timestamp: DataFrame }
    _is_setup = False

    @classmethod
    def setup_market_data(cls, file_name='synthetic_ibit_options.csv'):
        """
        [初始化] 加载期权数据并建立索引。
        """
        if cls._is_setup:
            return

        csv_path = os.path.join(Config.DATA_FOLDER, file_name)
        if not os.path.exists(csv_path):
            print(f"⚠️ [Pricing] Option data not found at {csv_path}. Running in Pure BSM mode.")
            return

        print(f"⏳ [Pricing] Loading option chain from {file_name}...")
        try:
            df = pd.read_csv(csv_path)
            
            # 1. 预处理列名 (兼容不同命名习惯)
            # 你的 CSV 表头是: Date,spot,strike,dte,option_type,price,delta,iv,moneyness,is_synthetic
            col_map = {
                'option_type': 'Type',  # ✅ 适配你的 option_type
                'OptionType': 'Type', 
                'type': 'Type', 
                'call_put': 'Type',
                
                'strike': 'Strike',     # ✅ 适配 strike
                'price': 'Price',       # ✅ 适配 price
                'delta': 'Delta',       # ✅ 适配 delta (关键！后续查找依赖它)
                'Delta': 'Delta'
            }
            df.rename(columns=col_map, inplace=True)
            
            # 2. 格式转换
            df['Date'] = pd.to_datetime(df['Date'])
            df['Type'] = df['Type'].str.lower().str.strip()
            
            # 标准化类型
            df.loc[df['Type'].isin(['c', 'call']), 'Type'] = 'call'
            df.loc[df['Type'].isin(['p', 'put']), 'Type'] = 'put'

            # 3. 建立高速缓存
            # 将巨大的 DataFrame 拆解为按日期索引的字典，实现 O(1) 查找
            cls._market_cache = {date: group for date, group in df.groupby('Date')}
            cls._is_setup = True
            print(f"✅ [Pricing] Cache built. Coverage: {len(cls._market_cache)} days.")
            
        except Exception as e:
            print(f"❌ [Pricing] Failed to load options data: {e}")
            cls._market_cache = None

    # ==========================================
    # 核心接口 1: 获取期权价格 (带熔断机制)
    # ==========================================
    @classmethod
    def get_price(cls, date, S, K, T, r, sigma, option_type='put'):
        """
        获取期权价格。
        逻辑: 查表 -> 校验 -> (如果不合格) -> BSM
        """
        # 1. 计算 BSM 理论价 (作为基准和保底)
        bsm_price = cls._bsm_price_formula(S, K, T, r, sigma, option_type)
        
        # 2. 尝试查市场价
        market_price = cls._lookup_market_price(date, K, option_type)
        
        if market_price is not None:
            # --- 🛡️ 熔断校验 (Sanity Check) ---
            # 如果市场价与理论价偏差过大，说明可能是脏数据 (Liquidity Gap / Bad Tick)
            
            # 相对偏差: |Market - BSM| / BSM
            rel_diff = abs(market_price - bsm_price) / (bsm_price + 0.0001) # 防止除零
            # 绝对偏差: |Market - BSM|
            abs_diff = abs(market_price - bsm_price)
            
            # 判定标准: 偏差 > 50% 且 绝对差值 > $0.5
            # (允许小金额的大比例偏差，例如 $0.05 vs $0.10)
            if rel_diff > 0.5 and abs_diff > 0.5:
                # 触发熔断，使用理论价
                return bsm_price
            
            return market_price
        
        # 3. 如果查不到，直接用 BSM
        return bsm_price

    # ==========================================
    # 核心接口 2: 根据 Delta 反推行权价
    # ==========================================
    @classmethod
    def get_strike_by_delta(cls, date, S, T, r, sigma, target_delta, option_type='put'):
        """
        根据 Delta 寻找 Strike。
        """
        # 1. 尝试查表
        market_strike = cls._lookup_strike_by_delta(date, target_delta, option_type)
        
        if market_strike is not None:
            return market_strike
            
        # 2. Fallback: BSM 反推
        return cls._bsm_find_strike(S, T, r, sigma, target_delta, option_type)

    # ==========================================
    # 内部实现: 查表逻辑
    # ==========================================
    @classmethod
    def _lookup_market_price(cls, date, target_strike, option_type):
        if not cls._is_setup or cls._market_cache is None:
            return None
            
        daily_chain = cls._market_cache.get(pd.Timestamp(date))
        if daily_chain is None or daily_chain.empty:
            return None
            
        chain = daily_chain[daily_chain['Type'] == option_type]
        if chain.empty:
            return None
            
        # 寻找最近的 Strike
        strikes = chain['Strike'].values
        idx = np.abs(strikes - target_strike).argmin()
        best_match_strike = strikes[idx]
        
        # 如果最近的 Strike 还是离得太远 (>5%)，认为该 Strike 不存在
        if abs(best_match_strike - target_strike) / target_strike > 0.05:
            return None
            
        return chain.iloc[idx]['Price']

    @classmethod
    def _lookup_strike_by_delta(cls, date, target_delta, option_type):
        if not cls._is_setup or cls._market_cache is None:
            return None
            
        daily_chain = cls._market_cache.get(pd.Timestamp(date))
        if daily_chain is None or daily_chain.empty:
            return None
            
        chain = daily_chain[daily_chain['Type'] == option_type]
        if chain.empty:
            return None
            
        # 匹配 Delta
        if 'Delta' not in chain.columns:
            # 如果映射失败，这里会返回 None，然后自动降级为 BSM，不会报错
            return None
            
        deltas = chain['Delta'].values
        
        # 处理符号问题 (Put Delta 可能是负数也可能是正数)
        # Opus 数据中的 Put Delta 通常是负数，但有些合成数据是绝对值
        if target_delta < 0 and np.all(deltas > 0):
             idx = np.abs(deltas - abs(target_delta)).argmin()
        else:
             idx = np.abs(deltas - target_delta).argmin()
             
        return chain.iloc[idx]['Strike']

    # ==========================================
    # 内部实现: BSM 公式
    # ==========================================
    @staticmethod
    def _bsm_price_formula(S, K, T, r, sigma, option_type='put'):
        if T <= 0: return max(0, S - K) if option_type == 'call' else max(0, K - S)
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        if option_type == 'call':
            return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        else:
            return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

    @staticmethod
    def _bsm_find_strike(S, T, r, sigma, target_delta, option_type='put'):
        if option_type == 'put':
            # Put Delta is negative, N(d1) - 1 = Delta -> N(d1) = 1 + Delta
            # e.g. 1 + (-0.3) = 0.7
            target_prob = 1 + target_delta
        else:
            target_prob = target_delta
        
        target_prob = np.clip(target_prob, 0.001, 0.999)
        d1 = norm.ppf(target_prob)
        
        vol_term = sigma * np.sqrt(T)
        drift_term = (r + 0.5 * sigma ** 2) * T
        log_k = np.log(S) - (d1 * vol_term) + drift_term
        return np.exp(log_k)