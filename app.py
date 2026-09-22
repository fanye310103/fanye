import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, request, jsonify, render_template_string

from fund_estimate import query_fund_estimate
from storage import FundStore

app = Flask(__name__)
app.json.ensure_ascii = False

DB_PATH = os.environ.get("FUND_DB", "funds.json")
store = FundStore(DB_PATH)


def batch_query(codes):
    results = {}
    if not codes:
        return results
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(query_fund_estimate, c): c for c in codes}
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                results[code] = fut.result()
            except Exception as e:
                results[code] = {"error": f"查询失败：{e}"}
    return results


@app.route("/api/funds", methods=["GET"])
def api_list():
    funds = store.list()
    estimates = batch_query([f["code"] for f in funds])
    out = []
    for f in funds:
        item = dict(f)
        item["estimate"] = estimates.get(f["code"], {"error": "无数据"})
        out.append(item)
    return jsonify(out)


@app.route("/api/funds", methods=["POST"])
def api_add():
    data = request.get_json(silent=True) or {}
    code = str(data.get("code", "")).strip()
    alias = str(data.get("alias", "")).strip()
    if not (code.isdigit() and len(code) == 6):
        return jsonify({"error": "基金代码必须是6位数字"}), 400
    if not store.add(code, alias):
        return jsonify({"error": "该基金已在列表中"}), 409
    return jsonify({"ok": True})


@app.route("/api/funds/<code>", methods=["PUT"])
def api_update(code):
    data = request.get_json(silent=True) or {}
    alias = str(data.get("alias", "")).strip()
    if not store.update(code, alias):
        return jsonify({"error": "未找到该基金"}), 404
    return jsonify({"ok": True})


@app.route("/api/funds/<code>", methods=["DELETE"])
def api_delete(code):
    if not store.remove(code):
        return jsonify({"error": "未找到该基金"}), 404
    return jsonify({"ok": True})


@app.route("/api/export", methods=["GET"])
def api_export():
    return jsonify(store.list())


@app.route("/api/import", methods=["POST"])
def api_import():
    data = request.get_json(silent=True)
    if not isinstance(data, list):
        return jsonify({"error": "格式错误，应为数组"}), 400
    cleaned = []
    seen = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "")).strip()
        if not (code.isdigit() and len(code) == 6):
            continue
        if code in seen:
            continue
        seen.add(code)
        cleaned.append({"code": code, "alias": str(item.get("alias", "")).strip()})
    store.replace_all(cleaned)
    return jsonify({"ok": True, "count": len(cleaned)})


HTML = r"""
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>我的基金估值</title>
<style>
  :root {
    --up: #e53935;
    --down: #43a047;
    --bg: #f5f6f8;
    --card: #ffffff;
    --text: #222222;
    --muted: #888888;
    --accent: #1a73e8;
  }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    margin: 0; padding: 12px; background: var(--bg); color: var(--text);
  }
  h1 { font-size: 18px; text-align: center; margin: 8px 0 16px; }
  .toolbar {
    display: flex; flex-wrap: wrap; gap: 8px;
    background: var(--card); padding: 12px; border-radius: 10px;
    margin-bottom: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }
  .toolbar input[type="text"] {
    flex: 1; min-width: 110px; padding: 10px;
    border: 1px solid #ddd; border-radius: 8px; font-size: 15px;
  }
  .toolbar button {
    padding: 10px 14px; border: none; border-radius: 8px;
    background: var(--accent); color: #fff; font-size: 15px; cursor: pointer;
  }
  .toolbar button.secondary { background: #6b7280; }
  .toolbar button:active { opacity: 0.8; }
  .toolbar label {
    display: flex; align-items: center; gap: 4px;
    font-size: 14px; color: var(--muted);
  }
  .status {
    font-size: 13px; color: var(--muted);
    text-align: right; margin-bottom: 8px; min-height: 18px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
    gap: 10px;
  }
  .card {
    background: var(--card); border-radius: 10px;
    padding: 12px 14px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }
  .card .top {
    display: flex; justify-content: space-between;
    align-items: flex-start; gap: 8px;
  }
  .card .title { font-size: 15px; font-weight: 600; line-height: 1.3; }
  .card .code {
    font-size: 12px; color: var(--muted); margin-top: 3px;
    word-break: break-all;
  }
  .card .actions { display: flex; gap: 2px; flex-shrink: 0; }
  .card .actions button {
    border: none; background: transparent; cursor: pointer;
    font-size: 15px; padding: 2px 4px; color: var(--muted);
  }
  .card .actions button:hover { color: var(--accent); }
  .card .change {
    font-size: 26px; font-weight: 700; margin: 8px 0 4px;
    font-variant-numeric: tabular-nums;
  }
  .up { color: var(--up); }
  .down { color: var(--down); }
  .card .meta {
    font-size: 12px; color: var(--muted);
    display: flex; flex-wrap: wrap; gap: 4px 8px;
  }
  .card .error {
    font-size: 13px; color: var(--up); margin: 8px 0 4px;
    word-break: break-all;
  }
  .empty {
    grid-column: 1 / -1; text-align: center;
    color: var(--muted); padding: 40px 0;
  }
</style>
</head>
<body>

<h1>📈 我的基金估值</h1>

<div class="toolbar">
  <input type="text" id="code" placeholder="基金代码（6位）" inputmode="numeric" maxlength="6">
  <input type="text" id="alias" placeholder="备注（可选）">
  <button onclick="addFund()">添加</button>
  <button class="secondary" onclick="loadFunds()">刷新</button>
  <button class="secondary" onclick="exportFunds()">导出</button>
  <button class="secondary" onclick="importFunds()">导入</button>
  <label><input type="checkbox" id="auto"> 自动刷新</label>
</div>

<div class="status" id="status"></div>
<div class="grid" id="grid"></div>
<input type="file" id="fileInput" accept=".json" style="display:none">

<script>
let autoTimer = null;

async function loadFunds() {
  const status = document.getElementById('status');
  status.textContent = '加载中…';
  try {
    const res = await fetch('/api/funds');
    const data = await res.json();
    render(data);
    status.textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN');
  } catch (e) {
    status.textContent = '加载失败：' + e.message;
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;',
    '"': '&quot;', "'": '&#39;'
  }[c]));
}

function render(items) {
  const grid = document.getElementById('grid');
  if (!items.length) {
    grid.innerHTML = '<div class="empty">还没有基金，在上方输入代码添加吧</div>';
    return;
  }

  items.sort((a, b) => {
    const ca = a.estimate && typeof a.estimate.gszzl === 'number' ? a.estimate.gszzl : null;
    const cb = b.estimate && typeof b.estimate.gszzl === 'number' ? b.estimate.gszzl : null;
    if (ca === null && cb === null) return 0;
    if (ca === null) return 1;
    if (cb === null) return -1;
    return cb - ca;
  });

  grid.innerHTML = items.map(item => {
    const est = item.estimate || {};
    const code = item.code;
    const title = item.alias || est.name || code;
    const subtitle = est.name && est.name !== title
      ? code + ' · ' + escapeHtml(est.name)
      : code;

    let changeHtml;
    if (est.error) {
      changeHtml = '<div class="error">⚠ ' + escapeHtml(est.error) + '</div>';
    } else if (typeof est.gszzl === 'number') {
      const cls = est.gszzl >= 0 ? 'up' : 'down';
      const sign = est.gszzl >= 0 ? '+' : '';
      changeHtml = '<div class="change ' + cls + '">' + sign + est.gszzl.toFixed(2) + '%</div>';
    } else {
      changeHtml = '<div class="error">暂无估值</div>';
    }

    const metaParts = [];
    if (est.gsz) metaParts.push('估值 ' + Number(est.gsz).toFixed(4));
    if (est.dwjz) metaParts.push('净值 ' + Number(est.dwjz).toFixed(4));
    if (est.gztime) metaParts.push(est.gztime.slice(5));

    return ''
      + '<div class="card">'
      +   '<div class="top">'
      +     '<div>'
      +       '<div class="title">' + escapeHtml(title) + '</div>'
      +       '<div class="code">' + subtitle + '</div>'
      +     '</div>'
      +     '<div class="actions">'
      +       '<button title="编辑备注" onclick="editAlias(\'' + code + '\')">✏️</button>'
      +       '<button title="删除" onclick="removeFund(\'' + code + '\')">🗑</button>'
      +     '</div>'
      +   '</div>'
      +   changeHtml
      +   '<div class="meta">' + metaParts.map(escapeHtml).join(' · ') + '</div>'
      + '</div>';
  }).join('');
}

async function addFund() {
  const codeEl = document.getElementById('code');
  const aliasEl = document.getElementById('alias');
  const code = codeEl.value.trim();
  const alias = aliasEl.value.trim();
  if (!/^\d{6}$/.test(code)) {
    alert('请输入6位数字基金代码');
    return;
  }
  const res = await fetch('/api/funds', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: code, alias: alias })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(err.error || '添加失败');
    return;
  }
  codeEl.value = '';
  aliasEl.value = '';
  loadFunds();
}

async function removeFund(code) {
  if (!confirm('确定删除 ' + code + ' 吗？')) return;
  await fetch('/api/funds/' + code, { method: 'DELETE' });
  loadFunds();
}

async function editAlias(code) {
  const current = prompt('输入新的备注名（留空则清除备注）：');
  if (current === null) return;
  await fetch('/api/funds/' + code, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ alias: current.trim() })
  });
  loadFunds();
}

async function exportFunds() {
  const res = await fetch('/api/export');
  const data = await res.json();
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'funds-' + new Date().toISOString().slice(0, 10) + '.json';
  a.click();
  URL.revokeObjectURL(a.href);
}

function importFunds() {
  document.getElementById('fileInput').click();
}

document.getElementById('fileInput').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const text = await file.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch (err) {
    alert('文件格式错误，需要 JSON 文件');
    e.target.value = '';
    return;
  }
  if (!Array.isArray(data)) {
    alert('文件内容应为数组');
    e.target.value = '';
    return;
  }
  if (!confirm('导入将覆盖当前列表，确定继续？')) {
    e.target.value = '';
    return;
  }
  const res = await fetch('/api/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  if (res.ok) loadFunds();
  else alert('导入失败');
  e.target.value = '';
});

document.getElementById('auto').addEventListener('change', (e) => {
  if (e.target.checked) {
    autoTimer = setInterval(loadFunds, 60000);
  } else {
    clearInterval(autoTimer);
    autoTimer = null;
  }
});

document.getElementById('code').addEventListener('keydown', e => {
  if (e.key === 'Enter') addFund();
});
document.getElementById('alias').addEventListener('keydown', e => {
  if (e.key === 'Enter') addFund();
});

loadFunds();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)