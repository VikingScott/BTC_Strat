# src/pricing.py

import numpy as np
from scipy.stats import norm
from .ibit_params import IbitRegime  # 引入新生成的参数库

# ==========================================
# 1. 基础数学公式 (纯计算，无状态)
# ==========================================
def bsm_formula(S, K, T, r, sigma, option_type):
    """
    纯粹的 BSM 公式实现
    """
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K) if option_type == 'call' else max(0.0, K - S)

    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if option_type == 'call':
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    elif option_type == 'put':
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return 0.0

# ==========================================
# 2. 市场定价引擎 (Market Pricing Engine)
# ==========================================
def get_market_price(S, K, T_days, r, dvol, option_type, action='sell'):
    """
    获取基于 IBIT 真实微观结构的期权成交价格。
    
    参数:
        S (float): 标的价格
        K (float): 行权价
        T_days (int): 剩余天数
        r (float): 无风险利率
        dvol (float): 当前市场 DVOL (如 0.55)
        option_type (str): 'call' 或 'put'
        action (str): 'buy' (买入开仓/平仓) 或 'sell' (卖出开仓/平仓)
    
    返回:
        dict: {
            'price': 最终成交价 (扣除 Spread 后),
            'mid_price': 理论中间价,
            'iv_used': 实际使用的 IV (含 Skew),
            'spread_pct': 使用的 Spread 比例,
            'regime': 当前市场状态
        }
    """
    # 1. 获取市场状态参数
    regime_params = IbitRegime.get_params(dvol)
    
    # 2. 计算 Moneyness (K / S)
    # 用于判断是 ATM 还是 OTM，从而决定用哪个 Spread
    moneyness = K / S
    
    # 3. 确定 Volatility (IV)
    # 逻辑：Call 通常用 ATM IV (Skew=0); OTM Put 用 Skew IV
    # 简化处理：只要是 Put 且 K < S (OTM Put)，就加上 Skew 溢价
    # 如果是 Call 或者 ITM Put，使用原始 DVOL (近似 ATM IV)
    
    iv_base = dvol
    iv_skew = 0.0
    
    if option_type == 'put' and moneyness < 0.98:
        # 命中 OTM Put，加上 Skew
        iv_skew = regime_params['skew_put_90']
    
    final_iv = iv_base + iv_skew
    
    # 4. 计算 BSM 理论中间价 (Mid Price)
    T_years = T_days / 365.0
    mid_price = bsm_formula(S, K, T_years, r, final_iv, option_type)
    
    # 5. 确定 Spread (交易滑点)
    # 逻辑：ATM (0.98-1.02) 用低 Spread，其他情况用高 Spread
    if 0.98 <= moneyness <= 1.02:
        spread_pct = regime_params['spread_atm']
    else:
        spread_pct = regime_params['spread_otm']
        
    # 6. 计算最终成交价 (Execution Price)
    # 作为 Taker (吃单) 或 Maker (挂单)，我们这里模拟 "即使挂单也要损失半个 Spread" 的真实损耗
    # Bid = Mid * (1 - spread/2)
    # Ask = Mid * (1 + spread/2)
    
    half_spread = spread_pct / 2.0
    
    if action == 'buy':
        # 买入价 = Ask Price (比中间价贵)
        exec_price = mid_price * (1 + half_spread)
    else: # action == 'sell'
        # 卖出价 = Bid Price (比中间价便宜)
        exec_price = mid_price * (1 - half_spread)
        
    # 兜底：价格不能为负
    exec_price = max(0.0, exec_price)

    return {
        'price': exec_price,       # 这是你需要更新到 cash 的钱
        'mid_price': mid_price,    # 这是用于记录市值的钱
        'iv_used': final_iv,
        'spread_used': spread_pct,
        'regime': IbitRegime.get_regime_name(dvol)
    }

# ==========================================
# 3. 兼容旧代码接口 (可选)
# ==========================================
def bsm_price(S, K, T_days, r, sigma, option_type='call'):
    """
    保留此函数以兼容旧的分析代码 (analytics.py 可能还会用到它算市值)
    """
    return bsm_formula(S, K, T_days/365.0, r, sigma, option_type)