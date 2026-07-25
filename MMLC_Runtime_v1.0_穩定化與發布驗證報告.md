# MMLC Runtime v1.0：穩定化、格式遷移與公開發布驗證報告

**正式名稱：** MMLC Runtime — Multidirectional Matrix Ledger Computation  
**建議 GitHub 倉庫：** `mmlc-runtime`  
**版本：** `1.0.0`  
**穩定格式：** MMLF `1.0`  
**日期：** 2026-07-23  
**作者／主導：** Neo.K／EveMissLab  
**AI 協作：** Aletheia（GPT-5.6 Thinking）

---

## 摘要

MMLC Runtime v0.1–v0.9 已依序完成矩陣帳本計算、局部與全域稽核、符號—數值交換、依賴污染與根因追蹤、多方向矩陣執行、跨軸約束與最小修復、時間索引與固定點、不可變補帳、硬／軟反事實干預、分支差分帳、有限觀測可識別性、離散與連續不確定性近似、政策評分、資訊價值與有限時域序貫決策。

v1.0 不再增加新的數學或因果功能，而是將前述實驗性能力收斂成第一個可安裝、可遷移、可測試、可公開維護的穩定 Runtime。

本版完成：

1. Python 公開 API 穩定化；
2. CLI 與退出碼穩定化；
3. MMLF 1.0 Schema；
4. MMLF v0.1–v0.9 相容載入；
5. 決定性格式遷移與執行等價驗證；
6. Schema 套件化；
7. wheel 與 source distribution；
8. GitHub Actions、授權、安全、貢獻與引用文件；
9. 公開效能基準；
10. 發布包完整性與安裝後驗證。

因此，v1.0 的主要命題不是：

> MMLC 又新增了更多功能。

而是：

> MMLC 已從連續原型轉化為具有穩定邊界、相容政策與公開發布條件的第一版研究型 Runtime。

---

## 一、名稱與 GitHub 倉庫

建議正式倉庫名稱：

```text
mmlc-runtime
```

理由：

- 短、直接、容易搜尋；
- 與 Python 套件名稱 `mmlc-runtime` 一致；
- 不把倉庫綁死在某一個版本；
- 未來可自然分拆：
  - `mmlc-spec`
  - `mmlc-bench`
  - `mmlc-docs`
  - 其他語言 binding 或視覺工具。

正式顯示名稱：

```text
MMLC Runtime — Multidirectional Matrix Ledger Computation
```

建議 Description：

```text
Auditable multidirectional matrix-ledger runtime for deterministic computation, constraints, temporal dynamics, counterfactuals, uncertainty, and finite decision analysis.
```

---

## 二、v1.0 的穩定邊界

### 2.1 穩定 Python API

Runtime 1.x 正式承諾以下入口：

```python
from mmlc import (
    Runtime,
    load_ledger,
    validate_file,
    execute_file,
    simulate_fdcs_file,
    migrate_file,
    runtime_info,
    save_result,
    verify_symbolic_numeric_exchange,
    compare_directions,
    compare_representations,
)
```

在 Runtime 1.x 期間：

- 可以增加可選欄位或新的相容入口；
- 不應刪除上述名稱；
- 不應重新定義既有核心語義；
- 不相容改動必須進入 Runtime 2.0。

### 2.2 穩定 CLI

正式指令：

```text
mmlc info
mmlc validate
mmlc migrate
mmlc run
mmlc verify-exchange
mmlc compare-directions
mmlc compare-representations
mmlc simulate-fdcs
mmlc benchmark
```

正式退出碼：

| 退出碼 | 意義 |
|---:|---|
| 0 | 指令完成 |
| 2 | 使用方式、Schema、遷移或明示設定錯誤 |
| 3 | 使用者要求將稽核失敗傳遞為程序失敗 |
| 4 | 未預期的內部錯誤 |

### 2.3 MMLF 1.0

MMLF 1.0 凍結 v0.9 已完成的文件表面與計算語義。

原則：

- Runtime 1.x 可增加可選且向後相容的欄位；
- 不相容的文件語義改動需要 MMLF 2.0；
- MMLF 2.0 必須提供明確遷移路徑。

---

## 三、最重要的工程修正：Schema 套件化

v0.9 以前，Schema 位於專案根目錄：

```text
schemas/
```

原始碼資料夾中執行時沒有問題，但安裝成 wheel 後，Runtime 不一定能找到外部 Schema。

v1.0 將全部 Schema 同時封裝於：

```text
mmlc/schemas/
```

並透過 `importlib.resources` 讀取。

正式 wheel 驗證結果：

- wheel 內 Schema：10 份；
- MMLF v0.1–v1.0 全部存在；
- 將 wheel 安裝到獨立臨時目錄後，可以讀取 Schema；
- 不依賴原始碼專案路徑；
- 安裝後可成功驗證並執行 MMLF 1.0 範例。

這是 v1.0 從「可以在目前資料夾執行」提升為「可以作為 Python 套件安裝」的關鍵差異。

---

## 四、未知版本不再被錯誤降級

舊版 Parser 對未知版本可能落回 v0.1 Schema。

例如：

```yaml
version: "2.0"
```

理論上應代表未來格式，但若被錯用 v0.1 驗證，可能造成：

- 錯誤接受未知文件；
- 新欄位被忽視；
- 使用者誤以為 Runtime 支援 v2.0；
- 執行語義與文件作者意圖不一致。

v1.0 改為：

```text
Unsupported MMLF version
```

明示拒絕。

這符合格式版本的基本安全原則：

\[
\text{未知格式}\neq\text{最舊格式}.
\]

---

## 五、決定性遷移器

正式指令：

```bash
mmlc migrate old.yaml --output stable.yaml
```

遷移流程：

```text
原版本 Schema 驗證
→ 深複製文件
→ 舊語法正規化
→ 設定 version: "1.0"
→ 寫入遷移 metadata
→ MMLF 1.0 Schema 驗證
→ Parser 建構
→ 原文件決定性執行
→ 新文件決定性執行
→ 版本無關快照比較
```

### 5.1 遷移不是只改版本號

例如 v0.5 的舊干預簡寫：

```yaml
- target: x-t1
  value: 100
```

會正規化為：

```yaml
- id: migrated-intervention-1
  kind: do_set
  target_tx_id: x-t1
  value: 100
```

### 5.2 格式升級不等於語義升級

如果直接把 v0.5 文件改成 v1.0，v1.0 Runtime 可能把原本僅宣告的干預真正執行，造成副作用。

因此遷移文件會加入：

```yaml
metadata:
  migrated_from: "0.5"
  migrated_by: "mmlc-runtime 1.0.0"
  migration_profile: mmlf-stable-1.0
```

Runtime 會使用：

\[
V_{semantic}=
\begin{cases}
V_{migrated\_from}, & \text{遷移文件}\cr
V_{document}, & \text{原生 v1.0 文件}
\end{cases}
\]

因此：

\[
\boxed{
\text{文件語法升級}
\not\Rightarrow
\text{執行副作用升級}
}
\]

---

## 六、遷移驗證結果

### 6.1 全範例格式遷移

| 指標 | 結果 |
|---|---:|
| 原始範例 | 40 |
| 成功遷移 | 40 |
| MMLF 1.0 驗證失敗 | 0 |
| Parser 建構失敗 | 0 |

### 6.2 代表性執行等價

選取涵蓋 v0.1–v0.9 與錯誤狀態的 12 個案例：

- 四則運算；
- 符號交換；
- 方向敏感掃描；
- 跨軸錯誤；
- 時間延遲；
- 硬干預；
- 軟干預；
- 機率政策；
- 連續相關不確定性；
- 除零失敗；
- 依賴循環例外；
- 固定點不收斂。

結果：

| 指標 | 結果 |
|---|---:|
| 代表案例 | 12 |
| 執行等價 | 12 |
| 不等價 | 0 |
| 原錯誤類型保留 | 通過 |
| FAIL／PASS 狀態保留 | 通過 |

遷移比較不直接使用 Runtime 的完整 semantic hash，因為版本號本來就屬於 hash 輸入。v1.0 會建立「版本無關執行快照」，移除：

- Runtime 版本；
- 文件版本；
- 衍生 hash；
- 舊／新干預表面語法差異。

再比較：

- 交易結果；
- 稽核狀態；
- 依賴與污染；
- 約束與修復；
- 時間與固定點；
- FDCS 分支結果；
- 顯式錯誤類型。

---

## 七、測試與靜態驗證

正式驗證結果：

\[
\boxed{71\text{ 項自動測試全部通過}}
\]

包含原 E0–E9 回歸，以及 v1.0 新增的：

- 原生 MMLF 1.0 文件；
- 套件內 Schema；
- 未知版本拒絕；
- v0.1 遷移；
- v0.5 語義保留；
- benchmark 決定性；
- CLI `info` 與 `migrate`。

最終檢查亦包括：

- Python 編譯；
- JSON 解析；
- Markdown 程式碼區塊；
- 40 個範例載入；
- wheel 內容；
- source distribution 內容；
- 獨立目錄安裝；
- 安裝後 Schema 讀取；
- 安裝後原生 v1.0 驗證。

---

## 八、發布套件

v1.0 產生：

```text
dist/mmlc_runtime-1.0.0-py3-none-any.whl
dist/mmlc_runtime-1.0.0.tar.gz
```

wheel 驗證：

| 指標 | 結果 |
|---|---:|
| wheel 檔案數 | 51 |
| 內含 Schema | 10 |
| 安裝後 smoke test | PASS |

source distribution 驗證：

| 指標 | 結果 |
|---|---:|
| sdist 檔案數 | 175 |
| README | 有 |
| API 文件 | 有 |
| benchmark | 有 |
| release validation | 有 |

---

## 九、效能基準

環境：

```text
Python 3.13.5
Linux 6.12.13 x86_64
tracemalloc enabled
```

測試兩種工作負載：

1. 獨立交易；
2. 線性依賴鏈。

| 工作負載 | 交易數 | 中位時間 | 中位吞吐量 | 峰值 Python 配置記憶體 |
|---|---:|---:|---:|---:|
| independent | 64 | 0.0277 秒 | 2,307 筆／秒 | 614,231 bytes |
| dependency chain | 64 | 0.0302 秒 | 2,122 筆／秒 | 695,943 bytes |
| independent | 256 | 0.1089 秒 | 2,351 筆／秒 | 2,439,227 bytes |
| dependency chain | 256 | 0.1235 秒 | 2,072 筆／秒 | 2,864,521 bytes |
| independent | 1,024 | 0.4869 秒 | 2,103 筆／秒 | 10,058,055 bytes |
| dependency chain | 1,024 | 0.6566 秒 | 1,560 筆／秒 | 11,722,418 bytes |

所有重跑：

- semantic hash 一致；
- global audit PASS；
- 6 個 benchmark case 全部通過。

這些數字只描述目前環境與實作開銷。因為啟用了 `tracemalloc`，絕對時間也包含追蹤成本。

不能由此宣稱：

- MMLC 快於 Excel；
- MMLC 快於 DAG 引擎；
- MMLC 快於資料庫、SymPy、NumPy 或專業因果框架。

v1.0 的 benchmark 是之後優化的自我基準，不是競品勝負表。

---

## 十、GitHub 公開準備

已加入：

- `README.md`：英文主頁；
- `README.zh-TW.md`：繁中說明；
- `LICENSE`：Apache-2.0；
- `NOTICE`；
- `CITATION.cff`；
- `AUTHORS.md`；
- `CONTRIBUTING.md`；
- `SECURITY.md`；
- `CODE_OF_CONDUCT.md`；
- GitHub Actions CI；
- Issue template；
- Pull request template；
- `.gitignore`；
- GitHub About 欄位與發布指令。

選擇 Apache-2.0 的理由是：

- 寬鬆開源；
- 允許商業與研究使用；
- 保留著作權與 NOTICE；
- 相較 MIT，具有較明確的專利授權條款。

在第一次公開 push 前仍可更換授權，但公開後再更換會牽涉既有貢獻與版本，應避免隨意改動。

---

## 十一、v1.0 仍不代表什麼

MMLC Runtime v1.0 不能宣稱：

1. 自動發現現實世界的真實因果圖；
2. 文件中的機率是客觀機率；
3. 有限觀測等價類等於一般統計可識別性；
4. 固定點收斂等於任意非線性系統的形式證明；
5. Halton＋Gaussian copula 等於解析連續推論；
6. reverse weight 等於逆因果；
7. hash chain 等於區塊鏈共識或外部可信時間戳；
8. 最小修復集等於唯一歷史真因；
9. MMLC 普遍優於試算表、DAG、資料庫、SMT、因果或機率程式框架。

精確定位仍是：

> 一套把多方向矩陣表示、型別化計算、帳本稽核、來源追蹤、動態反事實與有限決策分析統一在同一份可執行文件中的研究型 Runtime。

---

## 十二、v1.0 後的版本策略

v1.0.x 應集中於：

- 錯誤修正；
- 安全修正；
- 套件與安裝修正；
- 文件修正；
- 決定性與效能缺陷。

v1.1 可考慮：

- 安全的 typed extension contract；
- streaming 與有界記憶體；
- 稀疏修復後端；
- 形式化算子規格；
- 跨 Runtime conformance fixtures；
- 根據公開 benchmark 的實際效能優化。

不應只是為了繼續增加版本號，再把新的領域能力全部堆進同一 Runtime。

成熟後可分拆：

```text
mmlc-spec
mmlc-bench
mmlc-docs
```

---

## 結論

從 v0.1 到 v0.9，MMLC 驗證的是功能可行性。

v1.0 驗證的是另一件同樣重要的事：

\[
\boxed{
\text{原型能力}
\rightarrow
\text{穩定 API}
\rightarrow
\text{穩定格式}
\rightarrow
\text{可遷移}
\rightarrow
\text{可安裝}
\rightarrow
\text{可公開維護}
}
\]

目前可以正式確認：

\[
\boxed{
\text{MMLC Runtime 已完成第一個可公開發布的 1.0 穩定版。}
}
\]

它仍然是一套研究型 Runtime，而不是已證明取代所有既有計算框架的通用系統；但其格式、程式、測試、遷移、安裝、發布與誠實邊界，已經形成完整的第一版工程閉環。
