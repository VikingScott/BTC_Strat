import numpy as np
import pandas as pd
from scipy.stats import skew, kurtosis

class PerformanceMetrics:
    """
    金融指标计算器。
    负责计算 CAGR, MaxDrawdown, Sharpe, Sortino, Tail Risk 等指标。
    支持动态无风险利率。
    """
    
    @staticmethod
    def _prepare_excess_returns(series, risk_free_rate=0.03):
        """
        内部辅助函数：计算超额收益序列 (Excess Returns)。
        支持 risk_free_rate 为 float 或 pd.Series。
        """
        # 1. 计算策略日收益率
        returns = series.pct_change().dropna()
        
        # 2. 处理无风险利率
        if isinstance(risk_free_rate, (pd.Series, pd.DataFrame)):
            # 如果是序列，先对齐日期
            rf_aligned = risk_free_rate.reindex(returns.index).ffill().fillna(0.0)
            # 假设传入的是年化利率 (e.g. 0.04), 转换为日化
            rf_daily = rf_aligned / 252.0
            
            # 向量化减法: 每一天的收益减去当天的无风险利率
            excess_returns = returns - rf_daily
        else:
            # 如果是常数
            rf_daily = risk_free_rate / 252.0
            excess_returns = returns - rf_daily
            
        return returns, excess_returns

    @staticmethod
    def get_cagr(series):
        """年化复合增长率"""
        if len(series) < 2: return 0.0
        
        # 计算总天数
        days = (series.index[-1] - series.index[0]).days
        if days <= 0: return 0.0
        
        years = days / 365.25
        total_ret = series.iloc[-1] / series.iloc[0]
        
        # 防止负数开方报错 (虽然净值通常为正)
        if total_ret <= 0: return -1.0
        
        return (total_ret ** (1/years)) - 1

    @staticmethod
    def get_max_drawdown(series):
        """最大回撤 (返回正数, e.g. 0.35)"""
        roll_max = series.expanding().max()
        drawdown = (series - roll_max) / roll_max
        return abs(drawdown.min())

    @staticmethod
    def get_sharpe_ratio(series, risk_free_rate=0.03):
        """
        年化夏普比率。
        :param risk_free_rate: 可以是 float (0.03) 或 pd.Series (每日真实利率)
        """
        _, excess_returns = PerformanceMetrics._prepare_excess_returns(series, risk_free_rate)
        
        if excess_returns.std() == 0: return 0.0
        
        # Sharpe = Mean(Excess Return) / Std(Excess Return) * sqrt(252)
        # 注意：分母通常是用策略收益的标准差，还是超额收益的标准差？
        # 严格定义是 Std(Excess Return)，但在 rf 为常数时 Std(R) == Std(R-rf)。
        # 当 rf 波动时，使用 Std(Excess Return) 更准确。
        return excess_returns.mean() / excess_returns.std() * np.sqrt(252)

    @staticmethod
    def get_sortino_ratio(series, risk_free_rate=0.03):
        """
        年化索提诺比率 (只惩罚下行波动)。
        """
        # 这里我们需要原始 returns 来判断哪些是“负收益”，
        # 同时也需要 excess_returns 来计算分子。
        # Sortino 定义：分子是超额收益均值，分母是“下行偏差”(Downside Deviation)。
        # 下行偏差通常针对 MAR (Minimum Acceptable Return)，这里 MAR = risk_free_rate。
        
        returns, excess_returns = PerformanceMetrics._prepare_excess_returns(series, risk_free_rate)
        
        # 找出所有跑输无风险利率的日子 (即 Excess Return < 0)
        negative_excess_returns = excess_returns[excess_returns < 0]
        
        if len(negative_excess_returns) < 2: return 0.0
        
        # 下行标准差
        downside_std = np.sqrt(np.mean(negative_excess_returns**2)) * np.sqrt(252)
        
        if downside_std == 0: return 0.0
        
        # Sortino
        return (excess_returns.mean() * 252) / downside_std

    @staticmethod
    def get_calmar_ratio(series):
        """卡玛比率 (年化收益 / 最大回撤)"""
        cagr = PerformanceMetrics.get_cagr(series)
        mdd = PerformanceMetrics.get_max_drawdown(series)
        if mdd == 0: return 0.0
        return cagr / mdd

    @staticmethod
    def get_rolling_sharpe(series, window=180):
        """返回滚动夏普序列 (简化版，暂不考虑动态利率，仅用于看趋势)"""
        returns = series.pct_change().dropna()
        
        # 使用 expanding() 代替 rolling()
        # min_periods=90 意味着前3个月不显示，之后开始显示累积数据
        expanding_mean = returns.expanding(min_periods=180).mean()
        expanding_std = returns.expanding(min_periods=180).std()
        
        return (expanding_mean / expanding_std * np.sqrt(252)).fillna(0)

    @staticmethod
    def get_tail_risk_metrics(series):
        """
        计算高阶风控指标：偏度、峰度、VaR、CVaR
        """
        returns = series.pct_change().dropna()
        if len(returns) < 2: return {}

        # 1. 偏度 (Skewness) & 峰度 (Kurtosis)
        # Skew < 0 代表左尾风险大 (崩盘概率大)
        # Kurt > 3 代表肥尾效应 (极端行情多)
        sk = skew(returns)
        kt = kurtosis(returns)

        # 2. Value at Risk (VaR) - 历史模拟法
        # 95% 置信度: 在最糟糕的 5% 的日子里，门槛是多少
        var_95 = np.percentile(returns, 5) 
        var_99 = np.percentile(returns, 1)

        # 3. Conditional VaR (Expected Shortfall)
        # 在那最糟糕的 5% 的日子里，平均亏多少？
        cvar_95 = returns[returns <= var_95].mean()
        cvar_99 = returns[returns <= var_99].mean()

        # 4. 最惨的一天
        worst_day = returns.min()

        return {
            'Skewness': sk,
            'Kurtosis': kt,
            'VaR 95%': var_95,
            'VaR 99%': var_99,
            'CVaR 95%': cvar_95,
            'CVaR 99%': cvar_99,
            'Worst Day': worst_day
        }