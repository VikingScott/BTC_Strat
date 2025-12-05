import pandas as pd
import os

def inspect_large_csv():
    # 1. 配置路径
    input_file = os.path.join('data', 'IBIT_Active_Options.csv')
    sample_output = 'sample_options.csv'
    summary_output = 'options_summary.csv'

    print(f"🔍 正在读取文件: {input_file} ...")

    if not os.path.exists(input_file):
        print(f"❌ 错误: 找不到文件 {input_file}。请确认文件在 data 文件夹下。")
        return

    try:
        # --- 任务 A: 提取小切片 (Sample) ---
        # 只读取前 1000 行，速度极快
        df_sample = pd.read_csv(input_file, nrows=1000)
        df_sample.to_csv(sample_output, index=False)
        print(f"✅ [1/2] 切片完成! 已保存至: {sample_output} (前1000行)")

        # --- 任务 B: 全量结构分析 (Summary) ---
        print("⏳ [2/2] 正在分析全量数据结构 (这可能需要几秒钟)...")
        
        # 读取全量数据 (120MB 对于 pandas 来说通常没问题)
        # 如果内存实在不够，可以加 chunksize，但一般不需要
        df_full = pd.read_csv(input_file)
        
        # 构建数据字典概览
        summary_df = pd.DataFrame({
            'Data Type': df_full.dtypes,
            'Non-Null Count': df_full.count(),
            'Null Count': df_full.isnull().sum(),
            'Unique Values': df_full.nunique(), # 这一步计算量稍大
            'Example (First Row)': df_full.iloc[0] #以此为例查看格式
        })
        
        # 保存概览
        summary_df.to_csv(summary_output)
        print(f"✅ [2/2] 结构分析完成! 已保存至: {summary_output}")
        
        # 在终端打印列名，方便立刻查看
        print("\n--- 列名预览 ---")
        print(df_full.columns.tolist())
        print(f"\n总行数: {len(df_full)}")

    except Exception as e:
        print(f"❌ 处理过程中发生错误: {e}")

if __name__ == "__main__":
    inspect_large_csv()