from .pricing import bsm_price, get_dynamic_skew

# ==========================================
# 策略基类
# ==========================================
class BaseStrategy:
    def __init__(self, initial_capital):
        self.cash = initial_capital
        self.btc = 0.0
        self.positions = [] 
        self.history = []

    def run(self, df):
        for _, row in df.iterrows():
            # 1. 结算持仓
            for i in range(len(self.positions)-1, -1, -1):
                pos = self.positions[i]
                pos['days_left'] -= 1
                if pos['days_left'] <= 0:
                    self._settle(pos, row['price'])
                    self.positions.pop(i)
            # 2. 交易信号
            self.next_signal(row)
            # 3. 记录状态
            self._record(row)

    def _settle(self, pos, spot):
        payoff = 0
        if pos['type'] == 'call': payoff = max(0, spot - pos['strike'])
        elif pos['type'] == 'put': payoff = max(0, pos['strike'] - spot)
        
        if payoff > 0:
            if pos['side'] == 'short': self.cash -= payoff * pos['size']
            else: self.cash += payoff * pos['size']

    def _record(self, row):
        spot, r, sigma = row['price'], row['r'], row['sigma']
        opt_val = 0
        for pos in self.positions:
            p = bsm_price(spot, pos['strike'], pos['days_left'], r, sigma, pos['type'])
            if pos['side'] == 'short': opt_val -= p * pos['size']
            else: opt_val += p * pos['size']
        equity = self.cash + (self.btc * spot) + opt_val
        gap = row.get('vol_gap', 0)
        self.history.append({'date': row['date'], 'equity': equity, 'spot': spot, 'gap': gap})

    def buy_spot(self, price, pct=1.0):
        if self.cash > 10:
            amt = self.cash * pct
            self.btc += amt / price
            self.cash -= amt

    def sell_option(self, strike, days, size, premium, opt_type):
        net = (premium * size) * 0.98
        self.cash += net
        self.positions.append({'type': opt_type, 'side':'short', 'strike': strike, 'days_left': days, 'size': size})

    def buy_option(self, strike, days, size, premium, opt_type):
        cost = (premium * size) * 1.02
        self.cash -= cost
        self.positions.append({'type': opt_type, 'side':'long', 'strike': strike, 'days_left': days, 'size': size})
    
    def next_signal(self, row): pass

# ==========================================
# 具体策略类
# ==========================================

class BuyHoldStrategy(BaseStrategy):
    def next_signal(self, row):
        if self.btc == 0 and self.cash > 0: self.buy_spot(row['price'])

class CoveredCallStrategy(BaseStrategy):
    def __init__(self, capital, days=30, otm=1.10):
        super().__init__(capital)
        self.days = days
        self.otm = otm
    def next_signal(self, row):
        if self.btc == 0: self.buy_spot(row['price'])
        if self.btc > 0 and not self.positions:
            strike = row['price'] * self.otm
            vol = row['sigma'] 
            prem = bsm_price(row['price'], strike, self.days, row['r'], vol, 'call')
            self.sell_option(strike, self.days, self.btc, prem, 'call')

class CashSecuredPutStrategy(BaseStrategy):
    def __init__(self, capital, days=30, otm=0.90):
        super().__init__(capital)
        self.days = days
        self.otm = otm
    def next_signal(self, row):
        if not self.positions:
            strike = row['price'] * self.otm
            current_skew = get_dynamic_skew(row['sigma'])
            vol = row['sigma'] + current_skew
            prem = bsm_price(row['price'], strike, self.days, row['r'], vol, 'put')
            if self.cash > 0:
                size = self.cash / strike
                if size > 0.001: self.sell_option(strike, self.days, size, prem, 'put')

class CollarStrategy(BaseStrategy):
    def __init__(self, capital, days=30, protect=0.90, cap=1.10):
        super().__init__(capital)
        self.days = days
        self.protect = protect
        self.cap = cap
    def next_signal(self, row):
        price = row['price']
        # 现金再平衡
        total_equity = self.cash + self.btc * price
        target_cash = total_equity * 0.05
        if self.cash < target_cash:
            shortfall = target_cash - self.cash
            if self.btc * price > shortfall:
                self.btc -= shortfall / price
                self.cash += shortfall

        if self.btc == 0 and self.cash > 0:
            self.buy_spot(price, pct=0.95)
            
        if self.btc > 0 and not self.positions:
            k_put = price * self.protect
            k_call = price * self.cap
            skew_put = get_dynamic_skew(row['sigma'])
            vol_put = row['sigma'] + skew_put
            p_put = bsm_price(price, k_put, self.days, row['r'], vol_put, 'put')
            vol_call = row['sigma']
            p_call = bsm_price(price, k_call, self.days, row['r'], vol_call, 'call')
            cost = (p_put * 1.02 - p_call * 0.98) * self.btc
            if self.cash > cost:
                self.buy_option(k_put, self.days, self.btc, p_put, 'put')
                self.sell_option(k_call, self.days, self.btc, p_call, 'call')


class RegimeCollarStrategy(BaseStrategy):
    def __init__(self, capital, days=30, protect=0.95, cap=1.05):
        super().__init__(capital)
        self.days = days
        self.protect = protect # 保护线 (如 0.95)
        self.cap = cap         # 上限线 (如 1.05)

    def next_signal(self, row):
        # 1. 基础检查
        if len(self.positions) > 0:
            return
        
        price = row['price']
        gap = row['vol_gap']
        
        # 确保有币可交易
        if self.btc == 0:
            if self.cash > 0:
                self.buy_spot(price, pct=0.80)
            else:
                return

        # 2. 【核心逻辑】：判断 IV-RV Gap
        
        # --- 场景 A: Gap < 0 (波动率低估 / 保险便宜区) ---
        # 执行 Collar (买保险 + 卖 Call)
        if gap < 0:
            # Put 加上 Skew
            skew_put = get_dynamic_skew(row['sigma'])
            vol_put = row['sigma'] + skew_put
            p_put = bsm_price(price, price * self.protect, self.days, row['r'], vol_put, 'put')
            
            # Call 使用原始 DVOL
            vol_call = row['sigma']
            p_call = bsm_price(price, price * self.cap, self.days, row['r'], vol_call, 'call')
            
            # 净成本检查
            cost = (p_put * 1.02 - p_call * 0.98) * self.btc
            if self.cash > cost:
                self.buy_option(price * self.protect, self.days, self.btc, p_put, 'put')
                self.sell_option(price * self.cap, self.days, self.btc, p_call, 'call')

        # --- 场景 B: Gap >= 0 (波动率高估 / 正常区) ---
        # 执行 Covered Call (只卖 Call 收租，不买昂贵的 Put)
        else:
            strike = price * self.cap # 使用 Cap 参数作为 Call Strike
            vol = row['sigma']
            prem = bsm_price(price, strike, self.days, row['r'], vol, 'call')
            self.sell_option(strike, self.days, self.btc, prem, 'call')

# class ChameleonStrategy(BaseStrategy):
#     def __init__(self, capital, days=30):
#         super().__init__(capital)
#         self.days = days

#     def next_signal(self, row):
#         if len(self.positions) > 0: return

#         price = row['price']
#         total_equity = self.cash + self.btc * price
#         target_cash = total_equity * 0.05
#         if self.cash < target_cash:
#             shortfall = target_cash - self.cash
#             if self.btc * price > shortfall:
#                 self.btc -= shortfall / price
#                 self.cash += shortfall

#         gap = row['vol_gap']
        
#         # 1. Panic Mode (Sell Put)
#         if gap > 0.15:
#             if self.btc > 0: 
#                 self.cash += self.btc * price
#                 self.btc = 0
#             strike = price * 0.90
#             skew = get_dynamic_skew(row['sigma'])
#             vol = row['sigma'] + skew
#             prem = bsm_price(price, strike, self.days, row['r'], vol, 'put')
#             if self.cash > 0:
#                 size = self.cash / strike
#                 if size > 0.001: self.sell_option(strike, self.days, size, prem, 'put')

#         # 2. Cheap Vol (Collar)
#         elif gap < 0:
#             if self.btc == 0 and self.cash > 0: self.buy_spot(price, pct=0.95)
#             if self.btc > 0:
#                 k_put = price * 0.95
#                 k_call = price * 1.10
#                 skew_put = get_dynamic_skew(row['sigma'])
#                 p_put = bsm_price(price, k_put, self.days, row['r'], row['sigma']+skew_put, 'put')
#                 p_call = bsm_price(price, k_call, self.days, row['r'], row['sigma'], 'call')
#                 cost = (p_put * 1.02 - p_call * 0.98) * self.btc
#                 if self.cash > cost:
#                     self.buy_option(k_put, self.days, self.btc, p_put, 'put')
#                     self.sell_option(k_call, self.days, self.btc, p_call, 'call')

#         # 3. Normal (Covered Call)
#         else:
#             if self.btc == 0 and self.cash > 0: self.buy_spot(price, pct=0.95)
#             if self.btc > 0:
#                 strike = price * 1.10
#                 prem = bsm_price(price, strike, self.days, row['r'], row['sigma'], 'call')
#                 self.sell_option(strike, self.days, self.btc, prem, 'call')


class ChameleonStrategy(BaseStrategy):
    def __init__(self, capital, days=30):
        super().__init__(capital)
        self.days = days

    def next_signal(self, row):
        if len(self.positions) > 0: return

        price = row['price']
        total_equity = self.cash + self.btc * price
        target_cash = total_equity * 0.05
        
        # 1. Cash Rebalancing (保持不变)
        if self.cash < target_cash:
            shortfall = target_cash - self.cash
            if self.btc * price > shortfall:
                self.btc -= shortfall / price
                self.cash += shortfall

        gap = row['vol_gap']
        
        # 2. 核心逻辑：买保护 (Collar) VS 最大化收益 (CSP)
        
        # A. Low Vol (Gap < 0): 买保护 (Collar)
        if gap < 0:
            # 【防御模式】: 只有在保险便宜时才买保护
            
            # 确保有币
            if self.btc == 0 and self.cash > 0: self.buy_spot(price, pct=0.95)
            
            if self.btc > 0:
                k_put = price * 0.95
                k_call = price * 1.10
                skew_put = get_dynamic_skew(row['sigma'])
                p_put = bsm_price(price, k_put, self.days, row['r'], row['sigma']+skew_put, 'put')
                p_call = bsm_price(price, k_call, self.days, row['r'], row['sigma'], 'call')
                
                cost = (p_put * 1.02 - p_call * 0.98) * self.btc
                if self.cash > cost:
                    self.buy_option(k_put, self.days, self.btc, p_put, 'put')
                    self.sell_option(k_call, self.days, self.btc, p_call, 'call')
        
        # B. Normal/Panic Vol (Gap >= 0): 全力卖 Put (CSP)
        else:
            # 【收益模式】: 变色龙的 Alpha 来源于此。
            
            # 1. 资产转换: 卖掉所有币，最大化现金 collateral
            if self.btc > 0: 
                self.cash += self.btc * price
                self.btc = 0
            
            # 2. 执行 CSP 核心逻辑
            if self.cash > 0:
                strike = price * 0.90
                skew = get_dynamic_skew(row['sigma'])
                vol = row['sigma'] + skew
                prem = bsm_price(price, strike, self.days, row['r'], vol, 'put')
                
                size = self.cash / strike
                if size > 0.001: self.sell_option(strike, self.days, size, prem, 'put')

# class WheelStrategy(BaseStrategy):
#     def __init__(self, initial_capital, days=30, put_otm=0.90, call_otm=1.10):
#         super().__init__(initial_capital)
#         self.days = days
#         self.put_otm = put_otm
#         self.call_otm = call_otm
#         self.stage = "CSP"

#     def _settle(self, pos, spot):
#         strike = pos['strike']
#         size = pos['size']
#         otype = pos['type']
#         if otype == 'put' and spot < strike:
#             cost = strike * size
#             if self.cash >= cost: 
#                 self.cash -= cost
#                 self.btc += size
#                 self.stage = "CC" 
#             else:
#                 loss = (strike - spot) * size
#                 self.cash -= loss
#         elif otype == 'call' and spot > strike:
#             revenue = strike * size
#             if self.btc >= size:
#                 self.btc -= size
#                 self.cash += revenue
#                 self.stage = "CSP"
#             else:
#                 loss = (spot - strike) * size
#                 self.cash -= loss

#     def next_signal(self, row):
#         if len(self.positions) > 0: return
#         price = row['price']
#         if self.stage == "CSP":
#             if self.btc > 0.001: 
#                 self.cash += self.btc * price
#                 self.btc = 0
#             strike = price * self.put_otm
#             skew = get_dynamic_skew(row['sigma'])
#             vol = row['sigma'] + skew
#             prem = bsm_price(price, strike, self.days, row['r'], vol, 'put')
#             if self.cash > 0:
#                 size = self.cash / strike
#                 if size > 0.001: self.sell_option(strike, self.days, size, prem, 'put')
#         elif self.stage == "CC":
#             if self.btc < 0.001:
#                 self.stage = "CSP"
#                 return
#             strike = price * self.call_otm
#             vol = row['sigma']
#             prem = bsm_price(price, strike, self.days, row['r'], vol, 'call')
#             self.sell_option(strike, self.days, self.btc, prem, 'call')
class WheelStrategy(BaseStrategy):
    def __init__(self, initial_capital, days=30, put_otm=0.90, call_otm=1.10, slip=0.02):
        super().__init__(initial_capital)
        self.days = days
        self.put_otm = put_otm
        self.call_otm = call_otm
        self.slip = slip          # 2% slippage
        self.stage = "CSP"

    def _settle(self, pos, spot):
        strike = pos['strike']
        size = pos['size']
        otype = pos['type']
        if otype == 'put' and spot < strike:
            cost = strike * size
            if self.cash >= cost: 
                self.cash -= cost
                self.btc += size
                self.stage = "CC" 
            else:
                loss = (strike - spot) * size
                self.cash -= loss
        elif otype == 'call' and spot > strike:
            revenue = strike * size
            if self.btc >= size:
                self.btc -= size
                self.cash += revenue
                self.stage = "CSP"
            else:
                loss = (spot - strike) * size
                self.cash -= loss

    def next_signal(self, row):
        if len(self.positions) > 0: 
            return

        price = row['price']

        if self.stage == "CSP":
            # 清空现货 -> 全现金卖 put
            if self.btc > 0.001: 
                self.cash += self.btc * price
                self.btc = 0

            strike = price * self.put_otm
            skew = get_dynamic_skew(row['sigma'])
            vol = row['sigma'] + skew

            prem = bsm_price(price, strike, self.days, row['r'], vol, 'put')
            prem *= (1 - self.slip)   # 卖 put 少收 2%

            if self.cash > 0:
                size = self.cash / strike
                if size > 0.001:
                    self.sell_option(strike, self.days, size, prem, 'put')

        elif self.stage == "CC":
            # 持币卖 call
            if self.btc < 0.001:
                self.stage = "CSP"
                return

            strike = price * self.call_otm
            vol = row['sigma']

            prem = bsm_price(price, strike, self.days, row['r'], vol, 'call')
            prem *= (1 - self.slip)   # 卖 call 少收 2%

            self.sell_option(strike, self.days, self.btc, prem, 'call')