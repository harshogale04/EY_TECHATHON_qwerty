import pandas as pd

def load_oem(path):
    return pd.read_excel(path, sheet_name='Product Catalog')