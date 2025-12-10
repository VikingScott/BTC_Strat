import numpy as np
import pandas as pd
from scipy.stats import skew, kurtosis

class PerformanceMetrics:
    """
    负责计算所有金融指标。输入是净值序列 (Series)，输出是数字。
    """
    
    @staticmethod
    def get_cagr(series):
        """年化复合增长率"""
        if len(series) < 2: return 0.0
        days = (series.index[-1] - series.index[0]).days
        years = days / 365.25
        total_ret = series.iloc[-1] / series.iloc[0]
        return (total_ret ** (1/years)) - 1

    @staticmethod
    def get_max_drawdown(series):
        """最大回撤 (返回正数百分比, e.g. 0.35 表示 35%)"""
        roll_max = series.expanding().max()
        drawdown = (series - roll_max) / roll_max
        return abs(drawdown.min())

    @staticmethod
    def get_sharpe_ratio(series, risk_free_rate=0.03):
        """年化夏普比率"""
        returns = series.pct_change().dropna()
        if returns.std() == 0: return 0.0
        excess_ret = returns.mean() - (risk_free_rate/252)
        return excess_ret / returns.std() * np.sqrt(252)

    @staticmethod
    def get_sortino_ratio(series, risk_free_rate=0.03):
        """年化索提诺比率 (只惩罚下行波动)"""
        returns = series.pct_change().dropna()
        downside_returns = returns[returns < 0]
        if len(downside_returns) < 2: return 0.0
        downside_std = downside_returns.std()
        excess_ret = returns.mean() - (risk_free_rate/252)
        return excess_ret / downside_std * np.sqrt(252)

    @staticmethod
    def get_calmar_ratio(series):
        """卡玛比率 (年化收益 / 最大回撤)"""
        cagr = PerformanceMetrics.get_cagr(series)
        mdd = PerformanceMetrics.get_max_drawdown(series)
        if mdd == 0: return 0.0
        return cagr / mdd

    @staticmethod
    def get_rolling_sharpe(series, window=180):
        """返回滚动夏普序列，用于画图"""
        returns = series.pct_change().dropna()
        rolling_mean = returns.rolling(window).mean()
        rolling_std = returns.rolling(window).std()
        return (rolling_mean / rolling_std * np.sqrt(252)).fillna(0)
    
    @staticmethod
    def get_tail_risk_metrics(series):
        """
        计算尾部风险指标：偏度、峰度、VaR、CVaR
        """
        returns = series.pct_change().dropna()
        if len(returns) < 2: return {}

        # 1. 偏度与峰度
        sk = skew(returns)
        kt = kurtosis(returns)

        # 2. Value at Risk (VaR) - 历史模拟法
        # 95% 置信度: 意味着只有 5% 的日子亏损会超过这个数
        var_95 = np.percentile(returns, 5) 
        var_99 = np.percentile(returns, 1)

        # 3. Conditional VaR (Expected Shortfall)
        # 在最倒霉的那 5% 的日子里，平均亏损是多少
        cvar_95 = returns[returns <= var_95].mean()
        cvar_99 = returns[returns <= var_99].mean()

        # 4. 最惨的 5 天 (具体的亏损比例)
        worst_5 = returns.nsmallest(5).values

        return {
            'Skewness': sk,
            'Kurtosis': kt,
            'VaR 95%': var_95,
            'VaR 99%': var_99,
            'CVaR 95%': cvar_95,
            'CVaR 99%': cvar_99,
            'Worst Day': worst_5[0]
        }