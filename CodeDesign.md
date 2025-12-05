graph TD
    A[数据层 Data Layer] -->|清洗 & 对齐| B[回测引擎 Backtest Engine]
    B -->|每日市场状态| C[策略层 Strategy Layer]
    C -->|交易指令| B
    C -->|调用| D[定价核心 Pricing Kernel]
    B -->|记录资金历史| E[分析层 Analysis Layer]
    E -->|生成图表| F[可视化 Visualization]

2. 模块详细设计
**模块一：数据管理器 (DataManager)**

职责：负责“搬运”和“组装”原材料。它屏蔽了数据来源的差异（本地 vs 网络），向下游提供一张干净的宽表。

核心组件：

PathFinder: 专门解决你的 /data 文件夹路径问题，无论脚本在哪都能定位。

LocalLoader: 读取 DVOL CSV，处理 Unix 时间戳。

WebLoader: 调用 yfinance 抓取 BTC 和 ^IRX (利率)。

Merger: 核心逻辑。负责将不同来源的数据按 Date 索引对齐。

关键处理：时区统一（去除 UTC）、缺失值填充（利率周末填充）、求交集（Inner Join）。

输出：一个 Pandas DataFrame，包含 date, spot, sigma, r。

**模块二：定价核心 (PricingKernel)**

职责：纯数学计算工具箱。无状态（Stateless），不存储任何数据，只负责算数。

核心方法：

bsm_price(S, K, T, r, sigma): 输入参数，返回期权理论价格。

calculate_greeks(...): (可选) 如果未来想做 Delta Hedge，在这里扩展。

设计特点：作为静态函数库存在，策略层随用随调。

**模块三：策略状态机 (StrategyEngine)**

职责：回测的大脑。管理“钱”和“仓位”。

属性 (State)：

Cash: 当前现金余额。

Asset: 当前持有的 BTC 数量。

Position: 当前持有的虚拟期权（记录 Strike, Expiration, Quantity）。

核心行为 (Methods)：

mark_to_market(today_row): 每天收盘，计算当前持仓的浮动盈亏。

check_expiration(today_date): 检查期权是否到期。如果到期，执行结算（现金交割或现货划转）。

next_signal(today_row): 策略逻辑入口。

判断：现在空仓吗？波动率够高吗？

执行：卖出 Call -> 增加 Cash (收到权利金) -> 记录 Position。

模块四：分析与可视化 (Visualizer)

职责：将枯燥的资金流水变成直观的图表。

输入：策略层生成的 History 列表。

核心计算：

Cumulative Return: 净值归一化。

Drawdown: 动态回撤计算。

Performance Metrics: 夏普比率、卡玛比率、总收益率。

图表输出：

Canvas 1: 策略 vs 持币 (净值走势)。

Canvas 2: 水下回撤图 (风险压力测试)。

Canvas 3: DVOL 波动率环境 (展示策略在何种市场环境下赚钱)。

3. 数据流转逻辑 (Data Flow Simulation)
假设回测开始，每一天（Tick）发生的事情如下：

Step 1 (Data): DataManager 吐出一行数据：2024-01-01, Spot=40000, Vol=0.5, Rate=0.04。

Step 2 (Update): StrategyEngine 看到这行数据，先更新账户净值（如果手里有期权，重新用 BSM 算一下它今天值多少钱）。

Step 3 (Logic):

检查: "我手里有期权吗？" -> 没有。

决策: "我要开仓。" -> 设定 Strike = 44000 (+10%), T = 30天。

定价: 调用 PricingKernel，算出权利金 = $500。

交易: 现金 +$500，记录负债仓位。

Step 4 (Loop): 进入下一天。

... 30天后 ...:

检查: "期权到期了。"

结算: 比较 Spot 和 Strike。

如果 Spot < 44000: 期权作废，之前的 $500 落袋为安。

如果 Spot > 44000: 发生赔付，扣除差价。

重置: 仓位清空，准备下一次开仓。

/BTC_STRAT
│
├── data/                   <-- [存放] DERIBIT_DVOL_1D.csv
│
├── main.py                 <-- [入口] 运行这个文件即可
│
├── src/                    <-- [源码目录]
│   ├── __init__.py
│   ├── data_loader.py      <-- 处理 CSV 和 yfinance 的混合加载
│   ├── pricing.py          <-- BSM 公式
│   ├── strategy.py         <-- 账户资金管理和交易逻辑
│   └── analytics.py        <-- 画图和指标计算
│
└── requirements.txt        <-- 记录 pandas, yfinance 等依赖