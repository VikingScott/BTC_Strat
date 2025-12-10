import pandas as pd
import numpy as np
from enum import Enum

class MarketRegime(Enum):
    LOW = "Low"
    NORMAL = "Normal"
    HIGH = "High"
    EXTREME = "Extreme" # 预留给未来扩展

class RegimeEngine:
    """
    Regime 识别引擎基类。
    负责接收清洗后的 DataFrame，计算并追加 regime_signal 列。
    """
    def __init__(self, target_col='sigma'):
        self.target_col = target_col

    def add_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError("Subclasses must implement add_signals")

class RollingPercentileRegime(RegimeEngine):
    """
    基于滚动百分位 (Rolling Percentile) 的自适应 Regime 识别。
    
    特性:
    1. 自适应: 阈值随过去 N 天的市场状态变化。
    2. 防抖动 (Hysteresis): 使用迟滞逻辑，进场门槛高，出场门槛低，防止信号反复横跳。
    """
    
    def __init__(self, window=365, min_periods=90, 
                 high_enter=0.67, high_exit=0.60,
                 low_enter=0.33, low_exit=0.40):
        """
        :param window: 滚动窗口大小 (天)，推荐 365 (一年)
        :param min_periods: 最小样本量，不足时默认为 Normal
        :param high_enter: 进入 High 状态的百分位 (如 67%)
        :param high_exit:  退出 High 状态的百分位 (如 60%) -> 必须 < high_enter
        :param low_enter:  进入 Low 状态的百分位 (如 33%)
        :param low_exit:   退出 Low 状态的百分位 (如 40%) -> 必须 > low_enter
        """
        super().__init__()
        self.window = window
        self.min_periods = min_periods
        # 阈值配置
        self.params = {
            'high_enter': high_enter,
            'high_exit': high_exit,
            'low_enter': low_enter,
            'low_exit': low_exit
        }

    def add_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算 Rolling Thresholds 并应用状态机逻辑。
        """
        # 1. 复制数据，避免污染源数据
        data = df.copy()
        
        # 2. 计算动态阈值 (使用 expanding window 模拟历史记忆，或者 rolling window 保持灵敏)
        # 这里我们使用 rolling，让策略能适应长期波动率结构的变化
        rolling = data[self.target_col].rolling(window=self.window, min_periods=self.min_periods)
        
        # 计算关键分位线
        data['q_high_enter'] = rolling.quantile(self.params['high_enter'])
        data['q_high_exit']  = rolling.quantile(self.params['high_exit'])
        data['q_low_enter']  = rolling.quantile(self.params['low_enter'])
        data['q_low_exit']   = rolling.quantile(self.params['low_exit'])
        
        # 3. 应用状态机 (Hysteresis Loop)
        # 由于状态依赖前一天的状态，这里很难完全向量化，使用循环处理信号
        # 为了速度，我们只循环生成 signal 列表
        
        signals = []
        current_state = MarketRegime.NORMAL.value # 默认初始状态
        
        # 提取 numpy 数组加速循环
        sig_vals = data[self.target_col].values
        q_he = data['q_high_enter'].values
        q_hx = data['q_high_exit'].values
        q_le = data['q_low_enter'].values
        q_lx = data['q_low_exit'].values
        
        for i in range(len(data)):
            val = sig_vals[i]
            
            # 如果阈值是 NaN (数据不足)，保持 Normal
            if np.isnan(q_he[i]):
                signals.append(MarketRegime.NORMAL.value)
                continue
            
            # --- 状态转移逻辑 ---
            
            if current_state == MarketRegime.NORMAL.value:
                if val > q_he[i]:
                    current_state = MarketRegime.HIGH.value
                elif val < q_le[i]:
                    current_state = MarketRegime.LOW.value
            
            elif current_state == MarketRegime.HIGH.value:
                # 只有跌破 exit 阈值才回到 Normal，形成缓冲带
                if val < q_hx[i]:
                    current_state = MarketRegime.NORMAL.value
            
            elif current_state == MarketRegime.LOW.value:
                # 只有涨破 exit 阈值才回到 Normal
                if val > q_lx[i]:
                    current_state = MarketRegime.NORMAL.value
            
            signals.append(current_state)
            
        data['regime_signal'] = signals
        return data

# -----------------------------------------------
# 单元测试 (Unit Test)
# 可以在命令行直接运行: python src/regime.py
# -----------------------------------------------
if __name__ == "__main__":
    # 创建假数据测试逻辑
    dates = pd.date_range(start='2020-01-01', periods=500)
    # 模拟一个正弦波波动率，看能不能正确识别 Low -> Normal -> High
    vol = 0.5 + 0.2 * np.sin(np.linspace(0, 10, 500)) 
    
    test_df = pd.DataFrame({'date': dates, 'sigma': vol})
    
    print("🧪 Testing Regime Engine...")
    engine = RollingPercentileRegime(window=100, min_periods=10)
    result = engine.add_signals(test_df)
    
    print(result[['date', 'sigma', 'regime_signal']].iloc[150:160])
    print("\n分布统计:")
    print(result['regime_signal'].value_counts())