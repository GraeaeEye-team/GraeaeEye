"""
Первичный парсинг и чтение банковских выписок (Excel, CSV).
Считывает загруженные файлы и преобразует их в pandas.DataFrame для последующей обработки.
"""
import pandas as pd


def load_file_to_dataframe(file_path: str) -> pd.DataFrame:
    """Загружает файл выписки в pandas DataFrame."""
    if file_path.endswith(".csv"):
        return pd.read_csv(file_path)
    elif file_path.endswith((".xlsx", ".xls")):
        return pd.read_excel(file_path)
    raise ValueError(f"Неподдерживаемый формат файла: {file_path}")

