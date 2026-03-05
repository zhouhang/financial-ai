import pandas as pd, warnings, json
warnings.filterwarnings('ignore')

files = {
    'AI自动化逻辑': 'AI自动化逻辑20260103.xlsx',
    '手工凭证原表': '手工凭证原表.xlsx',
    'BI费用明细表': 'BI费用明细表.xlsx',
    '供应商毛利表': '供应商&代运营毛利表原表.xlsx',
}

import os
base = os.path.dirname(os.path.abspath(__file__))

for label, fname in files.items():
    fpath = os.path.join(base, fname)
    print(f'\n{"="*60}')
    print(f'[{label}] {fname}')
    print('='*60)
    try:
        xl = pd.ExcelFile(fpath)
        for sheet in xl.sheet_names:
            df = xl.parse(sheet, header=None, dtype=str).fillna('')
            print(f'\n  -- Sheet: {sheet} ({df.shape[0]}行 x {df.shape[1]}列) --')
            # 只输出前50行，避免太长
            print(df.head(50).to_string(index=False, header=False))
    except Exception as e:
        print(f'  读取失败: {e}')
