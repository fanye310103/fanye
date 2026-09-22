"""
基金列表持久化：JSON 文件存储，带线程锁和原子写。
"""
import json
import os
import threading
from typing import List, Dict


class FundStore:
    def __init__(self, path: str = "funds.json"):
        self.path = path
        self.lock = threading.Lock()
        if not os.path.exists(self.path):
            self._write([])

    def _read(self) -> List[Dict]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write(self, funds: List[Dict]):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(funds, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def list(self) -> List[Dict]:
        with self.lock:
            return self._read()

    def add(self, code: str, alias: str = "") -> bool:
        with self.lock:
            funds = self._read()
            if any(f.get("code") == code for f in funds):
                return False
            funds.append({"code": code, "alias": alias})
            self._write(funds)
            return True

    def update(self, code: str, alias: str) -> bool:
        with self.lock:
            funds = self._read()
            for f in funds:
                if f.get("code") == code:
                    f["alias"] = alias
                    self._write(funds)
                    return True
            return False

    def remove(self, code: str) -> bool:
        with self.lock:
            funds = self._read()
            new_funds = [f for f in funds if f.get("code") != code]
            if len(new_funds) == len(funds):
                return False
            self._write(new_funds)
            return True

    def replace_all(self, funds: List[Dict]):
        with self.lock:
            self._write(funds)