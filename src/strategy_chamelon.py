import pandas as pd
import numpy as np
from .pricing import OptionPricing
from .regime import RollingPercentileRegime  # 引入计算引擎

class SmartWheelStrategy:
    """
    Smart Wheel (Regime-Adaptive) Strategy - 参数化增强版
    
    核心逻辑:
    内部独立计算 Regime 信号，不依赖全局数据。允许针对性测试不同窗口的敏感度。
    
    Regime 行为:
    | Regime | CASH 状态 | STOCK 状态 |
    | :--- | :--- | :--- |
    | **Low** | 买入现货 (Force Buy) | 持币不动 (No Call) |
    | **Normal**| 卖 -0.30 Put | 卖 0.30 Call |
    | **High** | 卖 -0.15 Put (苟住) | 卖 0.30 Call (回血) |
    """
    
    def __init__(self, initial_capital=100_000, 
                 target_dte=30, 
                 regime_window=365):  # <--- 新增参数：自定义窗口
        
        self.initial_capital = initial_capital
        self.target_dte = target_dte
        self.regime_window = regime_window
        # 为了区分不同窗口的策略，把窗口写进名字里
        self.name = f"SmartWheel(W{regime_window})" 
        
        # 参数配置 (在这里微调 High/Low 的 Delta)
        self.params = {
            'Normal': {'put_delta': -0.30, 'call_delta': 0.30},
            'High':   {'put_delta': -0.15, 'call_delta': 0.30} 
            # Low Regime 只有现货操作，无 Delta 参数
        }

    def _calculate_local_regime(self, df):
        """
        [私有方法] 为当前策略单独计算 Regime 信号
        """
        # 实例化一个临时的计算引擎
        # 这里我们可以微调迟滞参数，或者直接沿用默认比例
        engine = RollingPercentileRegime(
            window=self.regime_window,  # 使用策略专属窗口
            min_periods=60,             # 稍微缩短冷启动期
            high_enter=0.67, high_exit=0.60,
            low_enter=0.33, low_exit=0.40
        )
        
        # 计算信号 (返回的是带有 regime_signal 列的 df)
        # 注意：我们只关心 sigma 列作为输入
        temp_df = df[['date', 'sigma']].copy()
        processed = engine.add_signals(temp_df)
        
        return processed['regime_signal']

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        print(f"   🏃 Running Strategy: {self.name}...")
        
        # 1. 复制数据
        data = df.copy()
        
        # 2. 🔥 关键步骤：覆盖全局信号，使用私有信号 🔥
        # 这不会影响外部的原始 df，只影响当前策略内部的 data
        data['regime_signal'] = self._calculate_local_regime(data)
        
        # 结果容器
        results = data[['date', 'price', 'sigma', 'r', 'regime_signal']].copy()
        portfolio_value = []
        
        # --- 核心状态机 ---
        cash = self.initial_capital
        stock_holdings = 0.0
        state = 'CASH' 
        current_option = None 
        
        for i in range(len(data)):
            row = data.iloc[i]
            current_date = row['date']
            S = row['price']
            sigma = row['sigma']
            r = row['r']
            regime = row['regime_signal'] # 使用的是刚刚算出来的私有信号
            
            # ==========================================
            # 1. 处理期权到期
            # ==========================================
            if current_option:
                if i >= current_option['expiry_idx']:
                    K = current_option['strike']
                    contracts = current_option['contracts']
                    opt_type = current_option['type']
                    
                    if opt_type == 'put':
                        if S < K: # 被行权
                            cost = K * contracts
                            cash -= cost
                            stock_holdings += contracts
                            state = 'STOCK'
                        else: pass
                    
                    elif opt_type == 'call':
                        if S > K: # 被赎回
                            revenue = K * contracts
                            cash += revenue
                            stock_holdings -= contracts
                            state = 'CASH'
                        else: pass
                            
                    current_option = None

            # ==========================================
            # 2. 状态切换 (Low Regime 特殊处理)
            # ==========================================
            if current_option is None:
                if regime == 'Low':
                    if state == 'CASH':
                        # 进攻：Low Vol 时直接买入现货
                        if S > 0:
                            stock_holdings = cash / S
                            cash = 0
                            state = 'STOCK'
                    elif state == 'STOCK':
                        # 进攻：Low Vol 时持有现货，不卖 Call (防止卖飞)
                        pass

            # ==========================================
            # 3. 开仓逻辑 (Normal / High)
            # ==========================================
            if current_option is None and regime in ['Normal', 'High'] and (i + self.target_dte < len(data)):
                
                T_year = self.target_dte / 365.0
                p = self.params[regime]
                
                # --- CASH: 卖 Put ---
                if state == 'CASH':
                    target_delta = p['put_delta']
                    K = OptionPricing.get_strike_by_delta(current_date, S, T_year, r, sigma, target_delta, 'put')
                    premium = OptionPricing.get_price(current_date, S, K, T_year, r, sigma, 'put')
                    
                    if K > 0:
                        contracts = cash / K
                        cash += premium * contracts
                        current_option = {
                            'type': 'put', 'strike': K, 
                            'expiry_idx': i + self.target_dte, 'contracts': contracts
                        }

                # --- STOCK: 卖 Call ---
                elif state == 'STOCK':
                    target_delta = p['call_delta']
                    K = OptionPricing.get_strike_by_delta(current_date, S, T_year, r, sigma, target_delta, 'call')
                    premium = OptionPricing.get_price(current_date, S, K, T_year, r, sigma, 'call')
                    
                    if stock_holdings > 0:
                        contracts = stock_holdings
                        cash += premium * contracts
                        current_option = {
                            'type': 'call', 'strike': K, 
                            'expiry_idx': i + self.target_dte, 'contracts': contracts
                        }

            # ==========================================
            # 4. 净值计算
            # ==========================================
            nav = cash
            if stock_holdings > 0:
                nav += stock_holdings * S
            
            if current_option:
                K = current_option['strike']
                contracts = current_option['contracts']
                opt_type = current_option['type']
                
                days_left = max(0, (data.iloc[current_option['expiry_idx']]['date'] - current_date).days)
                T_left = days_left / 365.0
                
                curr_opt_price = OptionPricing.get_price(current_date, S, K, T_left, r, sigma, opt_type)
                nav -= curr_opt_price * contracts
                
            portfolio_value.append(nav)

        results['portfolio_value'] = portfolio_value
        results['strategy'] = self.name
        results['daily_pnl'] = results['portfolio_value'].diff().fillna(0)
        
        return results