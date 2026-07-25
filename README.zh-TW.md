# MMLC Runtime v1.0

**Multidirectional Matrix Ledger Computation Runtime／多向矩陣帳本計算執行環境**

MMLC Runtime 是一套可稽核的 Python 矩陣帳本執行環境，將型別化交易、算子不變式、來源追蹤、多方向矩陣遍歷、跨軸約束、時間動態、反事實分支、不確定性傳播與有限決策分析，整合為同一套可檢查的執行模型。

v1.0 不再橫向堆疊新能力，而是正式完成：

- 穩定 Python 公開 API；
- 穩定 CLI 與退出碼；
- MMLF 1.0 Schema；
- MMLF v0.1–v0.9 相容載入；
- 決定性格式遷移與執行等價驗證；
- Schema 套件化，安裝後仍可驗證文件；
- 效能基準與可重現性檢查；
- GitHub、CI、安全、貢獻與發布文件。

## 建議 GitHub 名稱

```text
mmlc-runtime
```

正式名稱：

```text
MMLC Runtime — Multidirectional Matrix Ledger Computation
```

建議描述：

> Auditable multidirectional matrix-ledger runtime for deterministic computation, constraints, temporal dynamics, counterfactuals, uncertainty, and finite decision analysis.

## 安裝

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

## 快速執行

```bash
mmlc validate examples/mmlf_v1_stable.yaml
mmlc run examples/mmlf_v1_stable.yaml \
  --output outputs/quickstart \
  --deterministic \
  --fail-on-audit
```

Python：

```python
from mmlc import execute_file

result = execute_file("examples/mmlf_v1_stable.yaml")
assert result.global_audit["status"] == "PASS"
```

## 遷移舊文件

```bash
mmlc migrate examples/four_operations.yaml \
  --output migrated/four_operations_v1.yaml
```

遷移不是只改版本號。它會：

1. 用原始版本 Schema 驗證；
2. 正規化舊語法；
3. 寫成 MMLF 1.0；
4. 以 `migrated_from` 保留原始執行語義；
5. 重新驗證；
6. 比較原文件與遷移文件的決定性執行快照。

因此格式升級不會偷偷啟用舊文件原本尚未具有的副作用。

## 目前的誠實定位

MMLC v1.0 是研究型 Runtime、可執行規格與稽核框架。它不能宣稱：

- 自動發現現實世界的真實因果；
- 取代專業資料庫、試算表、DAG 引擎或機率程式；
- 解析求解所有連續分布、非線性循環或長期決策；
- 將宣告機率、效用與成本變成客觀真值。

完整文件請從 [英文 README](README.md) 與 [`docs/`](docs/) 開始。
