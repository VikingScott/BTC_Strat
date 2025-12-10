import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os
import sys

# Ensure we can import from local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.config import Config
from src.regime import RollingPercentileRegime, MarketRegime

def run_visualization():
    print("🎨 Starting Regime Visualization Playground...")

    # ---------------------------------------------------------
    # 1. Load Data
    # ---------------------------------------------------------
    file_path = os.path.join(Config.DATA_FOLDER, 'volatility_index.csv')
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    df = pd.read_csv(file_path)
    df['date'] = pd.to_datetime(df['Date'])
    df.set_index('date', inplace=True)
    
    # Filter for relevant period (2019-Present)
    df = df[df.index >= '2019-01-01'].copy()

    # Map columns for convenience
    # 'vol_index' is the corrected DVOL (Model + Actual)
    vol_col = 'vol_index' 
    price_col = 'ibit_spot'

    # ---------------------------------------------------------
    # 2. Compute Regimes
    # ---------------------------------------------------------
    
    # --- Setting A: Static Thresholds (The "Naive" / Opus Approach) ---
    # Logic: Hardcoded levels based on 7-year stats (Look-Ahead Bias)
    # Low < 53%, High > 71%
    df['static_regime'] = 'Normal'
    df.loc[df[vol_col] < 0.53, 'static_regime'] = 'Low'
    df.loc[df[vol_col] > 0.71, 'static_regime'] = 'High'

    # --- Setting B: Adaptive Rolling (The "Robust" Approach) ---
    # Logic: 1 Year Rolling Window, Hysteresis
    print("   Calculating Rolling Regime...")
    engine = RollingPercentileRegime(
        window=365, 
        min_periods=90,
        high_enter=0.67, high_exit=0.60,
        low_enter=0.33, low_exit=0.40
    )
    
    # We reset index for the engine, then set it back
    df_reset = df.reset_index()
    # Rename for the engine compatibility
    df_reset = df_reset.rename(columns={vol_col: 'sigma'}) 
    
    df_processed = engine.add_signals(df_reset)
    
    # Merge result back to main df
    df['rolling_regime'] = df_processed['regime_signal'].values
    df['roll_high'] = df_processed['q_high_enter'].values
    df['roll_low'] = df_processed['q_low_enter'].values

    # ---------------------------------------------------------
    # 3. Define Significant Market Events
    # ---------------------------------------------------------
    events = [
        ('2020-03-12', 'COVID Crash', 'black'),
        ('2021-05-19', 'China Ban', 'red'),
        ('2022-11-08', 'FTX Collapse', 'purple'),
        ('2024-01-11', 'Spot ETF Launch', 'green')
    ]

    # ---------------------------------------------------------
    # 4. Plotting
    # ---------------------------------------------------------
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 12), sharex=True, gridspec_kw={'height_ratios': [2, 1.5, 1.5]})
    plt.subplots_adjust(hspace=0.05)

    # --- Axes 1: Price & Structure ---
    ax1.plot(df.index, df[price_col], color='#333333', linewidth=1.5, label='IBIT/BTC Spot')
    ax1.set_yscale('log')
    ax1.set_ylabel('Price (Log)', fontsize=12)
    ax1.set_title('BTC Market Structure & Regimes Comparison', fontsize=16, fontweight='bold')
    ax1.grid(True, which='both', alpha=0.2)
    ax1.legend(loc='upper left')

    # Annotate Events on Price
    for date_str, label, color in events:
        date_obj = pd.to_datetime(date_str)
        if date_obj in df.index:
            price_val = df.loc[date_obj, price_col]
            ax1.annotate(label, xy=(date_obj, price_val), xytext=(date_obj, price_val*1.5),
                         arrowprops=dict(facecolor=color, shrink=0.05, width=1, headwidth=5),
                         fontsize=9, fontweight='bold', color=color, ha='center')
            # Draw vertical line through all subplots
            for ax in [ax1, ax2, ax3]:
                ax.axvline(date_obj, color=color, linestyle='--', alpha=0.5, linewidth=1)

    # --- Helper to paint background ---
    def paint_regime_background(ax, dates, regimes):
        # Convert regimes to numerical for fill_between logic
        # High=red, Normal=yellow, Low=green
        y_min, y_max = ax.get_ylim()
        
        # We iterate and paint spans
        # This is a bit slow but accurate for visualization
        start_idx = 0
        current_regime = regimes[0]
        
        color_map = {
            'High': '#ffcccc',   # Light Red
            'Normal': '#ffffe0', # Light Yellow
            'Low': '#ccffcc',    # Light Green
            'Extreme': '#ff9999' # Darker Red (if used)
        }
        
        for i in range(1, len(regimes)):
            if regimes[i] != current_regime:
                # End of a block
                color = color_map.get(current_regime, 'white')
                ax.axvspan(dates[start_idx], dates[i], color=color, alpha=0.6, lw=0)
                # Reset
                current_regime = regimes[i]
                start_idx = i
        
        # Paint last block
        color = color_map.get(current_regime, 'white')
        ax.axvspan(dates[start_idx], dates[-1], color=color, alpha=0.6, lw=0)

    # --- Axes 2: Static Regime (Opus Original) ---
    ax2.plot(df.index, df[vol_col], color='blue', linewidth=1, label='Volatility (DVOL)')
    # Add static thresholds lines
    ax2.axhline(0.71, color='red', linestyle=':', label='Static High (71%)')
    ax2.axhline(0.53, color='green', linestyle=':', label='Static Low (53%)')
    
    # Paint Background
    paint_regime_background(ax2, df.index, df['static_regime'].values)
    
    ax2.set_ylabel('IV (Static Regime)', fontsize=12)
    ax2.legend(loc='upper left')
    ax2.text(0.99, 0.9, "SETTING A: STATIC THRESHOLDS (Opus Default)\nPro: Simple\nCon: Fails in 2019 (Everything looks 'High')", 
         transform=ax2.transAxes, fontsize=10, bbox=dict(facecolor='white', alpha=0.8), ha='right')

    # --- Axes 3: Rolling Regime (Adaptive) ---
    ax3.plot(df.index, df[vol_col], color='blue', linewidth=1, label='Volatility (DVOL)')
    # Plot Dynamic Thresholds
    ax3.plot(df.index, df['roll_high'], color='red', linestyle='--', linewidth=1, alpha=0.7, label='Rolling High (67%ile)')
    ax3.plot(df.index, df['roll_low'], color='green', linestyle='--', linewidth=1, alpha=0.7, label='Rolling Low (33%ile)')
    
    # Paint Background
    paint_regime_background(ax3, df.index, df['rolling_regime'].values)
    
    ax3.set_ylabel('IV (Adaptive Regime)', fontsize=12)
    ax3.legend(loc='upper left')
    ax3.text(0.99, 0.9, "SETTING B: ADAPTIVE ROLLING (New)\nPro: Adjusts to Bear/Bull Cycles\nCon: Slight lag after crashes", 
         transform=ax3.transAxes, fontsize=10, bbox=dict(facecolor='white', alpha=0.8), ha='right')

    # Formatting
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax3.xaxis.set_major_locator(mdates.YearLocator())
    
    plt.tight_layout()
    
    output_path = os.path.join(Config.DATA_FOLDER, 'regime_comparison_viz.png')
    plt.savefig(output_path)
    print(f"✅ Visualization saved to: {output_path}")
    # plt.show() # Uncomment if running in IDE with display

if __name__ == "__main__":
    run_visualization()