import numpy as np
from scipy.stats import norm

def get_dynamic_skew(dvol):
    """
    Adjust DVOL, based on market panic
    Logic: The more market panics, DVOL rises, OTM put is more expensive than ATM
    """
    base_skew = 0.02
    panic_threshold = 0.60
    panic_factor = 0.20
    
    panic_premium = max(0.0, (dvol - panic_threshold) * panic_factor)
    return base_skew + panic_premium

def bsm_price(S, K, T_days, r, sigma, option_type='call'):
    """Black-Scholes-Merton"""
    if T_days <= 0:
        return max(0.0, S - K) if option_type == 'call' else max(0.0, K - S)

    T = T_days / 365.0
    # 防止 sigma 为 0 或负数
    if sigma <= 0: 
        return max(0.0, S - K) if option_type == 'call' else max(0.0, K - S)

    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if option_type == 'call':
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    elif option_type == 'put':
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return 0.0