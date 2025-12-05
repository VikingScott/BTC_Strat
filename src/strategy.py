from .pricing import get_market_price

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
        spot, r, dvol = row['price'], row['r'], row['sigma']
        opt_val = 0
        for pos in self.positions:
            # Mark-to-Market 使用中间价 (Mid Price)
            # action='sell' 只是为了填参数，这里我们只取 mid_price
            res = get_market_price(spot, pos['strike'], pos['days_left'], r, dvol, pos['type'], action='sell')
            p = res['mid_price']
            
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
        # 注意：premium 已经是扣除 Spread 后的 Bid Price (卖价)
        # 所以这里不再需要 * 0.98
        net = premium * size
        self.cash += net
        self.positions.append({'type': opt_type, 'side':'short', 'strike': strike, 'days_left': days, 'size': size})

    def buy_option(self, strike, days, size, premium, opt_type):
        # 注意：premium 已经是加上 Spread 后的 Ask Price (买价)
        # 所以这里不再需要 * 1.02
        cost = premium * size
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
            
            # 获取做市商报价 (Sell -> Bid Price)
            res = get_market_price(row['price'], strike, self.days, row['r'], row['sigma'], 'call', action='sell')
            prem = res['price']
            
            self.sell_option(strike, self.days, self.btc, prem, 'call')

class CashSecuredPutStrategy(BaseStrategy):
    def __init__(self, capital, days=30, otm=0.90):
        super().__init__(capital)
        self.days = days
        self.otm = otm
    def next_signal(self, row):
        if not self.positions:
            strike = row['price'] * self.otm
            
            # 获取做市商报价 (Sell -> Bid Price)
            # get_market_price 会自动识别这是 OTM Put 并加上 IBIT Skew
            res = get_market_price(row['price'], strike, self.days, row['r'], row['sigma'], 'put', action='sell')
            prem = res['price']
            
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
            
            # 询价：买 Put (Ask Price)
            res_put = get_market_price(price, k_put, self.days, row['r'], row['sigma'], 'put', action='buy')
            p_put = res_put['price']
            
            # 询价：卖 Call (Bid Price)
            res_call = get_market_price(price, k_call, self.days, row['r'], row['sigma'], 'call', action='sell')
            p_call = res_call['price']
            
            # 计算净成本 (不再需要手动 *1.02, 价格里已经含了 Spread)
            cost = (p_put - p_call) * self.btc
            
            if self.cash > cost:
                self.buy_option(k_put, self.days, self.btc, p_put, 'put')
                self.sell_option(k_call, self.days, self.btc, p_call, 'call')

class RegimeCollarStrategy(BaseStrategy):
    def __init__(self, capital, days=30, protect=0.95, cap=1.05):
        super().__init__(capital)
        self.days = days
        self.protect = protect 
        self.cap = cap         

    def next_signal(self, row):
        if len(self.positions) > 0: return
        
        price = row['price']
        gap = row['vol_gap']
        
        if self.btc == 0:
            if self.cash > 0: self.buy_spot(price, pct=0.80)
            else: return

        # Gap < 0: 波动率低估 -> 买保护
        if gap < 0:
            # 询价
            res_put = get_market_price(price, price * self.protect, self.days, row['r'], row['sigma'], 'put', action='buy')
            res_call = get_market_price(price, price * self.cap, self.days, row['r'], row['sigma'], 'call', action='sell')
            
            p_put = res_put['price']
            p_call = res_call['price']
            
            cost = (p_put - p_call) * self.btc
            if self.cash > cost:
                self.buy_option(price * self.protect, self.days, self.btc, p_put, 'put')
                self.sell_option(price * self.cap, self.days, self.btc, p_call, 'call')

        # Gap >= 0: 波动率正常/高 -> 只卖 Call
        else:
            strike = price * self.cap
            res = get_market_price(price, strike, self.days, row['r'], row['sigma'], 'call', action='sell')
            prem = res['price']
            self.sell_option(strike, self.days, self.btc, prem, 'call')


class ChameleonStrategy(BaseStrategy):
    def __init__(self, capital, days=30):
        super().__init__(capital)
        self.days = days

    def next_signal(self, row):
        if len(self.positions) > 0: return

        price = row['price']
        total_equity = self.cash + self.btc * price
        target_cash = total_equity * 0.05
        
        if self.cash < target_cash:
            shortfall = target_cash - self.cash
            if self.btc * price > shortfall:
                self.btc -= shortfall / price
                self.cash += shortfall

        gap = row['vol_gap']
        
        # A. Low Vol (Gap < 0): 买保护 (Collar)
        if gap < 0:
            if self.btc == 0 and self.cash > 0: self.buy_spot(price, pct=0.95)
            
            if self.btc > 0:
                k_put = price * 0.95
                k_call = price * 1.10
                
                # 询价 (含 Spread)
                res_put = get_market_price(price, k_put, self.days, row['r'], row['sigma'], 'put', action='buy')
                res_call = get_market_price(price, k_call, self.days, row['r'], row['sigma'], 'call', action='sell')
                
                p_put = res_put['price']
                p_call = res_call['price']
                
                cost = (p_put - p_call) * self.btc
                if self.cash > cost:
                    self.buy_option(k_put, self.days, self.btc, p_put, 'put')
                    self.sell_option(k_call, self.days, self.btc, p_call, 'call')
        
        # B. Normal/Panic Vol (Gap >= 0): 全力卖 Put (CSP)
        else:
            if self.btc > 0: 
                self.cash += self.btc * price
                self.btc = 0
            
            if self.cash > 0:
                strike = price * 0.90
                # 询价：引擎会自动处理 Skew 和 Spread
                res = get_market_price(price, strike, self.days, row['r'], row['sigma'], 'put', action='sell')
                prem = res['price']
                
                size = self.cash / strike
                if size > 0.001: self.sell_option(strike, self.days, size, prem, 'put')


class WheelStrategy(BaseStrategy):
    def __init__(self, initial_capital, days=30, put_otm=0.90, call_otm=1.10, slip=0.02):
        super().__init__(initial_capital)
        self.days = days
        self.put_otm = put_otm
        self.call_otm = call_otm
        self.slip = slip # 这里保留参数定义兼容性，但逻辑中不再使用硬编码滑点
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
            if self.btc > 0.001: 
                self.cash += self.btc * price
                self.btc = 0

            strike = price * self.put_otm
            
            # 自动询价 (含 Skew 和 Spread)
            res = get_market_price(price, strike, self.days, row['r'], row['sigma'], 'put', action='sell')
            prem = res['price']

            if self.cash > 0:
                size = self.cash / strike
                if size > 0.001:
                    self.sell_option(strike, self.days, size, prem, 'put')

        elif self.stage == "CC":
            if self.btc < 0.001:
                self.stage = "CSP"
                return

            strike = price * self.call_otm
            
            # 自动询价
            res = get_market_price(price, strike, self.days, row['r'], row['sigma'], 'call', action='sell')
            prem = res['price']

            self.sell_option(strike, self.days, self.btc, prem, 'call')