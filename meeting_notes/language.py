"""轉為臺灣繁體中文；保留英文專名及識別碼。"""
from functools import lru_cache
from opencc import OpenCC

@lru_cache(maxsize=1)
def converter():
    return OpenCC('s2twp')

def traditional(text: str) -> str:
    return converter().convert(text)
