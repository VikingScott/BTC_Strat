import os

class Config:
    INITIAL_CAPITAL = 1000000.0
    
    # 文件夹路径配置
    # 获取当前脚本(config.py)的上级目录的路径
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_FOLDER = os.path.join(BASE_DIR, 'data')
    TBL_FOLDER = os.path.join(BASE_DIR, 'tbl')
    PIC_FOLDER = os.path.join(BASE_DIR, 'pic')