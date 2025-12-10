
# 🦎 Project Chameleon: Bitcoin Options Backtest Engine

**A regime-based, microstructure-aware backtesting engine for Bitcoin options strategies (CSP, Wheel, Smart Wheel).**

## 📖 Overview

Project Chameleon bridges the gap between theoretical pricing models and real-world execution. It simulates the performance of various options selling strategies (Cash-Secured Puts, The Wheel, and the Regime-Adaptive "Smart Wheel") using synthesized market data and dynamic volatility regime detection.

**Key Features:**
* **Microstructure Pricing:** Uses a "Hybrid Pricing Engine" that prioritizes real market data (Volatility Skew & Spread) over pure Black-Scholes models.
* **Regime Detection:** Automatically classifies the market into `Low`, `Normal`, and `High` volatility regimes using a rolling window percentile algorithm.
* **Smart Logic:** Strategies like `SmartWheel` change behavior based on the market regime (e.g., forcing Spot Buys in Bull markets vs. Deep OTM Puts in Bear markets).

---

## 🛠️ Installation & Setup

### 1. Prerequisites
* Python 3.8+
* Recommended: Use a virtual environment (Conda or venv).

### 2. Install Dependencies
```bash
pip install pandas numpy matplotlib seaborn yfinance scipy
````

### 3\. Data Preparation (Crucial)

Ensure the `data/` directory contains the following two essential files. **The engine will NOT run without them.**

1.  **`volatility_index.csv`**: Contains the historical DVOL (Implied Volatility) and Spot prices.
2.  **`synthetic_ibit_options.csv`**: The large options chain database used for realistic pricing lookups.

*(Note: If these files are missing, the pricing engine will fallback to a naive BSM model, which may be inaccurate.)*

-----

## 🚀 Usage Guide

### 1\. Running the Standard Backtest

This is the main entry point. It runs all strategies defined in the configuration against historical data.

```bash
python main.py
```

  * **Output:** \* Console logs showing trade execution.
      * `tbl/performance_summary.csv`: Key metrics (Sharpe, Sortino, Drawdown).
      * `pic/compare_equity_curves.png`: Visual comparison of strategies.

### 2\. Running Diagnostics (Sanity Check)

If results look "too good to be true" or "jagged," run this to check for bad data (artifacts) or overnight gaps.

```bash
python src/sanity_check.py
```

### 3\. Visualizing Regimes

To see how the engine classifies historical periods (High vs Low Volatility):

```bash
python playground_regime_visualization.py
```

### 4\. Visualizing Strategy Payoffs

To generate educational charts explaining *how* the strategies work (e.g., for client presentations):

```bash
python playground_payoff.py
```

-----

## ⚙️ Configuration & Tuning

### Changing Strategies

Open `main.py` to comment/uncomment strategies or change their parameters:

```python
strategies = [
    # Baseline
    BuyAndHoldStrategy(initial_capital=100_000),
    
    # Compare different rolling windows
    SmartWheelStrategy(initial_capital=100_000, regime_window=90),  # Sensitive/Fast
    SmartWheelStrategy(initial_capital=100_000, regime_window=180), # Balanced (Recommended)
]
```

### Adjusting Regime Sensitivity

Open `src/strategy_smart_wheel.py` or `src/regime.py` to tweak how `Low`, `Normal`, and `High` are defined (e.g., changing percentiles from 33%/67% to 25%/75%).

-----

## 📂 Project Structure

  * `src/data_loader.py`: Ingests raw CSVs and calculates derived metrics (rates, regimes).
  * `src/pricing.py`: The hybrid engine (Lookup Table -\> Fallback to BSM Formula).
  * `src/strategy_*.py`: Individual strategy logic files.
  * `src/reporting.py`: Generates the beautiful CSV tables and PNG charts.
  * `data/`: Stores raw input data.
  * `pic/` & `tbl/`: Stores output results.

<!-- end list -->

