import pandas as pd
import numpy as np
from .pricing import OptionPricing

class WheelStrategy:
    """
    The Wheel Strategy (Triple Income Strategy)
    
    A state-machine based strategy that cycles between:
    1. CASH State: Sell Cash-Secured Puts (CSP)
    2. STOCK State: If Put assigned -> Hold Stock + Sell Covered Calls (CC)
    3. Back to CASH: If Call assigned -> Stock called away -> Return to step 1
    
    Parameters are symmetric to the CSP benchmark:
    - Put Delta: -0.30
    - Call Delta: 0.30
    - DTE: 30 Days
    """
    
    def __init__(self, initial_capital=100_000, target_delta=0.20, target_dte=30):
        self.initial_capital = initial_capital
        # Put Delta is negative (-0.3), Call Delta is positive (0.3)
        self.put_delta = -abs(target_delta)
        self.call_delta = abs(target_delta)
        self.target_dte = target_dte
        self.name = f"Wheel (Delta {target_delta})"

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        print(f"   🏃 Running Strategy: {self.name}...")
        
        # 结果容器
        results = df[['date', 'price', 'sigma', 'r', 'regime_signal']].copy()
        
        portfolio_value = []
        
        # --- 核心状态机 ---
        cash = self.initial_capital
        stock_holdings = 0.0
        
        # state: 'CASH' or 'STOCK'
        state = 'CASH' 
        
        # 期权持仓记录
        # {'type': 'put'/'call', 'strike': K, 'expiry_idx': 123, 'contracts': 10}
        current_option = None 
        
        for i in range(len(df)):
            row = df.iloc[i]
            current_date = row['date']
            S = row['price']
            sigma = row['sigma']
            r = row['r']
            
            # ==========================================
            # 1. 处理现有期权 (到期检查)
            # ==========================================
            if current_option:
                if i >= current_option['expiry_idx']:
                    K = current_option['strike']
                    contracts = current_option['contracts']
                    opt_type = current_option['type']
                    
                    # --- Case A: Put 到期 (在 CASH 状态) ---
                    if opt_type == 'put':
                        if S < K:
                            # 被行权 (Assignment): 用现金买入股票
                            cost = K * contracts
                            cash -= cost
                            stock_holdings += contracts
                            # 状态切换: 变成地主
                            state = 'STOCK'
                            # print(f"[{current_date.date()}] Put Assigned at {K:.2f}. Switched to STOCK.")
                        else:
                            # 过期作废: 赚了权利金，继续做 CASH 地主
                            pass 
                    
                    # --- Case B: Call 到期 (在 STOCK 状态) ---
                    elif opt_type == 'call':
                        if S > K:
                            # 被赎回 (Called Away): 卖出股票换现金
                            revenue = K * contracts
                            cash += revenue
                            stock_holdings -= contracts
                            # 状态切换: 回归现金
                            state = 'CASH'
                            # print(f"[{current_date.date()}] Call Assigned at {K:.2f}. Switched to CASH.")
                        else:
                            # 过期作废: 保住了股票，赚了权利金，继续卖 Call
                            pass
                            
                    # 清空期权仓位
                    current_option = None

            # ==========================================
            # 2. 开新仓 (根据当前状态)
            # ==========================================
            if current_option is None and (i + self.target_dte < len(df)):
                
                T_year = self.target_dte / 365.0
                
                # --- State 1: CASH (卖 Put) ---
                if state == 'CASH':
                    # 1. 找行权价 (-0.30 Delta)
                    K = OptionPricing.get_strike_by_delta(current_date, S, T_year, r, sigma, self.put_delta, 'put')
                    
                    # 2. 算权利金
                    premium = OptionPricing.get_price(current_date, S, K, T_year, r, sigma, 'put')
                    
                    # 3. 确定张数 (100% Cash Secured)
                    # Contracts = Cash / Strike
                    if K > 0:
                        contracts = cash / K
                        total_premium = premium * contracts
                        
                        cash += total_premium
                        current_option = {
                            'type': 'put',
                            'strike': K,
                            'expiry_idx': i + self.target_dte,
                            'contracts': contracts
                        }

                # --- State 2: STOCK (卖 Call) ---
                elif state == 'STOCK':
                    # 1. 找行权价 (+0.30 Delta)
                    # 注意: 这里不强制要求 K > 成本价 (纯波动率策略)
                    K = OptionPricing.get_strike_by_delta(current_date, S, T_year, r, sigma, self.call_delta, 'call')
                    
                    # 2. 算权利金
                    premium = OptionPricing.get_price(current_date, S, K, T_year, r, sigma, 'call')
                    
                    # 3. 确定张数 (Covered Call: 有多少股卖多少张)
                    contracts = stock_holdings
                    
                    if contracts > 0:
                        total_premium = premium * contracts
                        cash += total_premium
                        current_option = {
                            'type': 'call',
                            'strike': K,
                            'expiry_idx': i + self.target_dte,
                            'contracts': contracts
                        }

            # ==========================================
            # 3. 计算每日净值 (Mark to Market)
            # ==========================================
            nav = cash
            
            # 加上股票市值
            if stock_holdings > 0:
                nav += stock_holdings * S
            
            # 减去期权负债 (我们是卖方，期权涨价对我们是浮亏)
            if current_option:
                K = current_option['strike']
                contracts = current_option['contracts']
                opt_type = current_option['type']
                
                days_left = max(0, (df.iloc[current_option['expiry_idx']]['date'] - current_date).days)
                T_left = days_left / 365.0
                
                # 查当前期权市价
                curr_opt_price = OptionPricing.get_price(current_date, S, K, T_left, r, sigma, opt_type)
                liability = curr_opt_price * contracts
                nav -= liability
                
            portfolio_value.append(nav)

        # 整理输出
        results['portfolio_value'] = portfolio_value
        results['strategy'] = self.name
        results['daily_pnl'] = results['portfolio_value'].diff().fillna(0)
        
        # 记录一下状态，方便debug (可选)
        # results['state'] = ... 
        
        return results