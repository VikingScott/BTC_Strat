import pandas as pd
import numpy as np
from .pricing import OptionPricing

class CashSecuredPutStrategy:
    """
    Cash-Secured Put (CSP) Strategy
    
    逻辑:
    1. 持有现金。
    2. 每当没有持仓时，卖出 Put Option。
    3. 参数:
       - Target Delta: -0.30 (卖出 30 Delta 的虚值 Put)
       - DTE: 30 天 (滚动周期)
       - Allocation: 100% 资金作为保证金
    4. 结算:
       - 如果到期时 S > K: 赚取全部权利金。
       - 如果到期时 S < K: 发生行权，亏损 (K - S)，用现金支付。
    """
    
    def __init__(self, initial_capital=100_000, target_delta=-0.30, target_dte=30):
        self.initial_capital = initial_capital
        self.target_delta = target_delta
        self.target_dte = target_dte
        self.name = f"CSP (Delta {target_delta})"

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        print(f"   🏃 Running Strategy: {self.name}...")
        
        # 结果容器
        results = df[['date', 'price', 'sigma', 'r', 'regime_signal']].copy()
        
        portfolio_value = []
        cash = self.initial_capital
        
        # 交易状态记录
        current_position = None # 格式: {'strike': K, 'expiry_idx': 123, 'contracts': 10, 'premium_received': 500}
        
        # 遍历每一天
        # 注意: 我们需要按行遍历，因为交易依赖前一天的状态
        for i in range(len(df)):
            row = df.iloc[i]
            current_date = row['date']
            S = row['price']
            sigma = row['sigma']
            r = row['r']
            
            # --- 1. 检查现有持仓是否到期 ---
            if current_position:
                # 检查是否到达或者超过到期日
                # (简化处理: 我们用索引来判断 30天后，而不是真实日期计算，这样在回测数据缺失时更鲁棒)
                if i >= current_position['expiry_idx']:
                    # === 结算 ===
                    K = current_position['strike']
                    contracts = current_position['contracts']
                    
                    # 现金结算损益 (Cash Settlement Logic)
                    # 如果 S < K (被行权), 我们亏付 (K - S) * contracts
                    # 如果 S >= K, 我们什么都不做，权利金已经是我们的了
                    if S < K:
                        loss = (K - S) * contracts
                        cash -= loss
                    
                    # 仓位清空
                    current_position = None
            
            # --- 2. 如果空仓，开新仓 ---
            if current_position is None:
                # 只有在数据足够支持计算时才开仓 (比如不是最后一天)
                if i + self.target_dte < len(df):
                    # A. 计算行权价 (根据 Delta)
                    T_year = self.target_dte / 365.0
                    # ✅ 修复: 调用新接口 get_strike_by_delta 并传入 current_date
                    K = OptionPricing.get_strike_by_delta(current_date, S, T_year, r, sigma, self.target_delta, 'put')
                    
                    # B. 计算权利金 (Premium)
                    # ✅ 修复: 调用新接口 get_price 并传入 current_date
                    premium_per_share = OptionPricing.get_price(current_date, S, K, T_year, r, sigma, 'put')
                    
                    # C. 确定张数 (100% 现金担保)
                    # 每一份合约需要 K 的现金担保。
                    # 我们有 cash，加上即将收到的权利金，总购买力 = cash
                    # 严谨做法: Contracts = Cash / (K - Premium)  <-- 这样是把权利金也算进担保了
                    # 保守做法: Contracts = Cash / K
                    contracts = cash / K
                    
                    total_premium = premium_per_share * contracts
                    
                    # D. 记录开仓
                    cash += total_premium # 先收权利金 (Cash Secured Put 的特性)
                    
                    current_position = {
                        'strike': K,
                        'expiry_idx': i + self.target_dte,
                        'contracts': contracts,
                        'entry_price': premium_per_share
                    }

            # --- 3. 记录当天净值 (Mark to Market) ---
            if current_position:
                # 如果有持仓，我们需要计算期权的当前价值作为负债
                K = current_position['strike']
                contracts = current_position['contracts']
                
                # 计算剩余时间
                days_left = max(0, (df.iloc[current_position['expiry_idx']]['date'] - current_date).days)
                T_left = days_left / 365.0
                
                # 当前期权市场价 (这是我们欠市场的钱，如果是以平仓计算的话)
                # ⚠️ 关键修复: 这里之前调用的是 bsm_price，现已更新为 get_price
                current_option_price = OptionPricing.get_price(current_date, S, K, T_left, r, sigma, 'put')
                
                liability = current_option_price * contracts
                
                # 净值 = 现金 (含已收权利金) - 负债 (买回期权的成本)
                nav = cash - liability
            else:
                nav = cash
                
            portfolio_value.append(nav)

        # 整理结果
        results['portfolio_value'] = portfolio_value
        results['strategy'] = self.name
        results['daily_pnl'] = results['portfolio_value'].diff().fillna(0)
        
        return results