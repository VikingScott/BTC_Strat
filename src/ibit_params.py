# src/ibit_params.py

class IbitRegime:
    """
    【IBIT 市场微观结构参数库】
    
    数据来源：基于 2024 年 IBIT 期权真实成交数据的分层校准。
    用途：为回测提供真实的 Implied Volatility Skew (偏度) 和 Bid-Ask Spread (点差) 估算。
    
    Regime 定义：
    - LOW:    DVOL < 50
    - MID:    50 <= DVOL < 70
    - HIGH:   70 <= DVOL < 90 (基于逻辑推演)
    - EXTREME: DVOL >= 90     (基于压力测试假设)
    """

    # ==========================================
    # 参数查找表 (Lookup Table)
    # ==========================================
    # skew_put_90:  OTM Put 相比 ATM 的波动率溢价 (Vol Premium)
    # spread_atm:   ATM 合约的买卖价差占比 (Spread / Mid_Price)
    # spread_otm:   OTM 合约的买卖价差占比
    
    PARAMS = {
        "LOW": {
            "desc": "Calm / Range Bound (Real Data)",
            "skew_put_90": 0.0359,  # 3.59%
            "spread_atm": 0.0244,   # 2.44%
            "spread_otm": 0.0455    # 4.55%
        },
        "MID": {
            "desc": "Active / Bull Trend (Real Data)",
            "skew_put_90": 0.0101,  # 1.01% (Skew Flattening)
            "spread_atm": 0.0396,   # 3.96%
            "spread_otm": 0.0635    # 6.35% (Liquidity Worsens)
        },
        "HIGH": {
            "desc": "Fear / High Vol (Extrapolated)",
            "skew_put_90": 0.0450,  # 假设 Skew 回归
            "spread_atm": 0.0600,   # 6% Spread
            "spread_otm": 0.1000    # 10% Spread
        },
        "EXTREME": {
            "desc": "Crisis / Meltdown (Extrapolated)",
            "skew_put_90": 0.0800,  # 极度恐慌溢价
            "spread_atm": 0.1000,   # 流动性枯竭
            "spread_otm": 0.2000    # 几乎不可成交
        }
    }

    @classmethod
    def get_params(cls, dvol):
        """
        根据当前的 DVOL 值 (例如 0.55)，返回对应的微观结构参数字典。
        """
        # 容错处理：防止传入 55 这种百分数
        val = dvol / 100.0 if dvol > 2.0 else dvol
            
        if val < 0.50:
            return cls.PARAMS["LOW"]
        elif val < 0.70:
            return cls.PARAMS["MID"]
        elif val < 0.90:
            return cls.PARAMS["HIGH"]
        else:
            return cls.PARAMS["EXTREME"]

    @classmethod
    def get_regime_name(cls, dvol):
        """辅助函数：返回当前状态名称"""
        val = dvol / 100.0 if dvol > 2.0 else dvol
        if val < 0.50: return "LOW"
        elif val < 0.70: return "MID"
        elif val < 0.90: return "HIGH"
        else: return "EXTREME"