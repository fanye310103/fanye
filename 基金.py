#!/usr/bin/env python3
"""
基金实时估值逻辑
数据源：
  1. 天天基金估值接口（主）
  2. 重仓股穿透计算（备选）
"""

import json
import re
import time
from typing import Optional

import requests

# ============================================================
# 数据源一：天天基金实时估值接口
# ============================================================

def fetch_estimate_from_fundgz(fund_code: str) -> Optional[dict]:
    url = f"https://fundgz.1234567.com.cn/js/{fund_code}.js"
    headers = {
        "Referer": "https://fund.eastmoney.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        text = resp.text.strip()
        if not text.startswith("jsonpgz("):
            return None
        json_str = text[8:-2]
        data = json.loads(json_str)
        return {
            "source": "天天基金估值接口",
            "fundcode": data.get("fundcode", fund_code),
            "name": data.get("name", ""),
            "jzrq": data.get("jzrq", ""),
            "dwjz": float(data.get("dwjz", 0) or 0),
            "gsz": float(data.get("gsz", 0) or 0),
            "gszzl": float(data.get("gszzl", 0) or 0),
            "gztime": data.get("gztime", ""),
        }
    except Exception:
        return None


# ============================================================
# 数据源二：重仓股穿透
# ============================================================

def fetch_fund_holdings(fund_code: str, top: int = 10) -> list:
    url = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
    params = {"type": "jjcc", "code": fund_code, "topline": top}
    headers = {
        "Referer": "https://fundf10.eastmoney.com",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        content = resp.text
        rows = re.findall(
            r"<td>(\d+)</td>.*?"
            r"r/(\d\.\d+)\'?>(\d{6})</a>.*?"
            r"class='tol'.*?>(.+?)</a>.*?"
            r"class='tor'>([\d.]+)%</td>",
            content,
            re.DOTALL,
        )
        holdings = []
        for row in rows:
            holdings.append({
                "seq": int(row[0]),
                "market": int(row[1].split(".")[0]),
                "code": row[2],
                "name": row[3].strip(),
                "weight": float(row[4]),
            })
        return holdings[:top]
    except Exception:
        return []


def fetch_stock_price(stock_code: str, market: int) -> Optional[float]:
    prefix = "sh" if market == 1 else "sz"
    url = f"https://qt.gtimg.cn/q={prefix}{stock_code}"
    headers = {
        "Referer": "https://gu.qq.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        match = re.search(r'"(.+?)"', resp.text)
        if match:
            fields = match.group(1).split("~")
            if len(fields) > 32:
                return float(fields[32])
        return None
    except Exception:
        return None


def estimate_via_holdings(fund_code: str) -> Optional[dict]:
    holdings = fetch_fund_holdings(fund_code, top=10)
    if not holdings:
        return None
    total_weight = 0.0
    weighted_change = 0.0
    details = []
    for h in holdings:
        change = fetch_stock_price(h["code"], h["market"])
        if change is not None:
            weighted_change += change * (h["weight"] / 100)
            total_weight += h["weight"]
            details.append({
                "name": h["name"],
                "code": h["code"],
                "weight": h["weight"],
                "change": change,
            })
        time.sleep(0.1)
    if total_weight == 0:
        return None
    estimated_change = weighted_change / (total_weight / 100)
    return {
        "source": "重仓股穿透计算",
        "fundcode": fund_code,
        "name": "",
        "jzrq": "",
        "dwjz": 0.0,
        "gsz": 0.0,
        "gszzl": round(estimated_change, 2),
        "gztime": time.strftime("%Y-%m-%d %H:%M"),
        "holdings_detail": details,
        "covered_weight": round(total_weight, 2),
    }


# ============================================================
# 主查询 + 格式化
# ============================================================

def query_fund_estimate(fund_code: str) -> dict:
    fund_code = str(fund_code).strip()
    if not re.match(r"^\d{6}$", fund_code):
        return {"error": f"基金代码格式无效：{fund_code}，应为6位数字"}

    result = fetch_estimate_from_fundgz(fund_code)
    if result and result.get("gsz", 0) > 0:
        return result

    result = estimate_via_holdings(fund_code)
    if result:
        return result

    return {"error": f"无法获取基金 {fund_code} 的估值数据，请检查代码是否正确"}


def format_result(r: dict) -> str:
    if "error" in r:
        return f"❌ {r['error']}"
    lines = []
    lines.append("=" * 50)
    lines.append(f"📊 {r.get('name') or r['fundcode']}  ({r['fundcode']})")
    lines.append("=" * 50)
    lines.append(f"  数据来源：{r['source']}")
    if r.get("jzrq"):
        lines.append(f"  净值日期：{r['jzrq']}")
    if r.get("gztime"):
        lines.append(f"  估值时间：{r['gztime']}")
    if r.get("dwjz", 0) > 0:
        lines.append(f"  单位净值：{r['dwjz']:.4f}")
    if r.get("gsz", 0) > 0:
        lines.append(f"  估算净值：{r['gsz']:.4f}")
    change = r.get("gszzl", 0)
    arrow = "↑" if change >= 0 else "↓"
    color = "🔴" if change >= 0 else "🟢"
    lines.append(f"  估算涨跌：{color} {arrow} {change:+.2f}%")
    if "holdings_detail" in r:
        lines.append("-" * 50)
        lines.append(f"  重仓股明细（覆盖权重 {r['covered_weight']}%）：")
        for d in r["holdings_detail"]:
            stock_arrow = "↑" if d["change"] >= 0 else "↓"
            lines.append(
                f"    {d['name']}({d['code']})  "
                f"权重{d['weight']:.2f}%  "
                f"涨跌{stock_arrow}{d['change']:+.2f}%"
            )
        lines.append(
            f"\n  ⚠️ 穿透估值仅覆盖前10大重仓股"
            f"（合计{r['covered_weight']}%），结果仅供参考"
        )
    lines.append("=" * 50)
    return "\n".join(lines)