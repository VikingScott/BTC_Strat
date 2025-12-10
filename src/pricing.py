import numpy as np
from scipy.stats import norm

class OptionPricing:
    """
    提供 BSM 定价以及希腊字母计算，支持通过 Delta 反推 Strike。
    """

    @staticmethod
    def bsm_price(S, K, T, r, sigma, option_type='put'):
        """
        计算 Black-Scholes-Merton 价格
        S: 标的价格
        K: 行权价
        T: 年化到期时间 (Days/365)
        r: 无风险利率
        sigma: 波动率
        option_type: 'call' or 'put'
        """
        if T <= 0:
            return max(0, S - K) if option_type == 'call' else max(0, K - S)
            
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        if option_type == 'call':
            price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        else:
            price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
            
        return price

    @staticmethod
    def get_delta(S, K, T, r, sigma, option_type='put'):
        """计算 Delta 值"""
        if T <= 0: return 0
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        
        if option_type == 'call':
            return norm.cdf(d1)
        else:
            return norm.cdf(d1) - 1

    @staticmethod
    def find_strike_for_delta(S, T, r, sigma, target_delta, option_type='put'):
        """
        根据目标 Delta 反推行权价 K。
        这是量化策略中最常用的函数：'我要卖一个 30 Delta 的 Put'
        """
        # Delta = N(d1) - 1  (for put)
        # N(d1) = 1 + Delta
        # d1 = N_inv(1 + Delta)
        # K = S / exp( d1*sigma*sqrt(T) - (r + 0.5*sigma^2)*T )
        
        if option_type == 'put':
            # Put delta is negative (e.g., -0.30)
            target_prob = 1 + target_delta
        else:
            target_prob = target_delta
            
        # 边界保护
        target_prob = np.clip(target_prob, 0.001, 0.999)
        
        d1 = norm.ppf(target_prob)
        
        # 反解 K
        # d1 = (ln(S/K) + ...) / den
        # d1 * den = ln(S/K) + num
        # ln(S/K) = d1*den - num
        # K = S * exp(num - d1*den) -- wait, math verify
        # ln(K) = ln(S) - d1*sigma*sqrt(T) + (r + 0.5*sigma^2)*T
        
        vol_term = sigma * np.sqrt(T)
        drift_term = (r + 0.5 * sigma ** 2) * T
        
        log_k = np.log(S) - (d1 * vol_term) + drift_term
        return np.exp(log_k)