# MMLC Runtime v0.6 實作與 E6 驗證報告

**副標題：可執行虛擬干預、多語境平行演化、方向不對稱權重與分形層級衰減**

- 專案：Multidirectional Matrix Ledger Computation Runtime
- 版本：0.6.0
- 文件日期：2026-07-22
- 階段：E6
- 實作狀態：完成
- 自動測試：42 項全部通過
- 相容格式：MMLF v0.1–v0.6

---

## 摘要

MMLC Runtime v0.5 已能將時間索引、延遲依賴、固定點、不可變補帳與 FDCS 節點／邊投影納入同一份矩陣帳本。但 v0.5 的 FDCS 干預仍只有：

```text
DECLARED_NOT_EXECUTED
```

也就是可以記錄「想對某節點做干預」，但 Runtime 不會建立真正的反事實分支，也不會切斷傳入因果邊或重算後代。

v0.6 的主要目標，是讓下式從文件標記變成可執行語義：

\[
do(X_k=x^*).
\]

本版完成四項能力：

1. **虛擬干預分支**：以 `do_set` 取代目標節點的結構方程；
2. **多語境平行演化**：同一帳本可建立多個互不污染的反事實分支；
3. **方向不對稱因果權重**：正向影響與反向稽核／查詢權重分離；
4. **分形層級衰減**：權重可依節點層級差下降。

正式 E6 隨機驗證得到：

- 4,096／4,096 個反事實交易值正確；
- 128／128 條干預傳入邊正確切斷；
- 2,143／2,143 個祖先節點保持不變；
- 2,048／2,048 個無干預語境交易保持不變；
- 256／256 次語境雜湊重跑一致；
- 4,096／4,096 條正向權重正確；
- 4,096／4,096 條反向權重正確。

這些結果支持：在依賴圖與結構方程均已宣告的範圍內，MMLC 已能建立第一版可稽核的離散反事實矩陣帳本。

---

## 1. 問題定義

### 1.1 v0.5 的缺口

v0.5 可以輸出：

- 節點狀態；
- 同期與跨期邊；
- lag；
- 基礎權重；
- 語境 modulation；
- 分形層級欄位；
- 干預宣告。

但沒有回答：

> 當某個節點被設定成另一個值時，哪些傳入邊應被切斷？哪些後代應被重新計算？哪些非後代應保持不變？不同語境分支如何彼此隔離？

因此 v0.6 不只是再增加一個輸出欄位，而是改變 Runtime 的執行路徑。

### 1.2 E6 的驗證命題

E6 驗證以下命題。

#### 命題 E6-A：傳入邊切斷

若對節點 \(X_k\) 執行：

\[
do(X_k=x^*),
\]

則反事實分支中的依賴圖應移除：

\[
Pa(X_k)\rightarrow X_k.
\]

#### 命題 E6-B：後代重算

設 \(De(X_k)\) 為後代集合。則：

\[
\forall Y\in De(X_k),
\quad
Y^{do}
=
F_Y(Pa^{do}(Y)).
\]

#### 命題 E6-C：祖先與非後代穩定

對不受干預影響的節點：

\[
Z\notin \{X_k\}\cup De(X_k)
\Rightarrow
Z^{do}=Z^{obs}.
\]

#### 命題 E6-D：語境隔離

對任意兩個語境分支 \(c_1,c_2\)：

\[
\mathcal L^{(c_1)}
\text{ 的執行不得改寫 }
\mathcal L^{(c_2)}.
\]

#### 命題 E6-E：權重公式正確

每條邊的共同權重為：

\[
\omega_{ij}^{common}(c)
=
\omega_{ij}^{0}
\lambda^{\Delta t_{ij}}
\mu^{|\ell_j-\ell_i|}
M(c).
\]

正向與反向查詢權重分別為：

\[
\omega_{ij}^{\rightarrow}
=
\omega_{ij}^{common}(c)\alpha_{ij}^{\rightarrow},
\]

\[
\omega_{ij}^{\leftarrow}
=
\omega_{ij}^{common}(c)\alpha_{ij}^{\leftarrow}.
\]

---

## 2. 格式擴充

MMLF v0.6 新增：

```yaml
fdcs:
  enabled: true
  base_context: observed
  decay_lambda: 0.9
  fractal_decay_lambda: 0.8
  direction_weights:
    forward: 1.0
    reverse: 0.25
  parallel_workers: 3
  contexts:
    - id: do-root-10
      modulation: 1.0
      interventions:
        - id: set-root-10
          kind: do_set
          target_tx_id: root
          value: 10
          reason: counterfactual test
```

### 2.1 `base_context`

表示原始觀測帳本的語境名稱。它不是反事實分支，而是所有分支的比較基準。

### 2.2 `contexts`

每個語境具有：

- 唯一 ID；
- 權重 modulation；
- 一組干預；
- 可選 metadata。

### 2.3 `do_set`

v0.6 只正式支援：

```yaml
kind: do_set
```

其值必須是 literal，不可包含：

- `ValueRef`；
- `MatrixRef`；
- `TemporalRef`。

否則干預值本身會暗中建立新依賴，破壞「切斷傳入邊」的契約。

---

## 3. 執行語義

### 3.1 觀測執行

Runtime 先正常執行原始帳本：

\[
\mathcal L^{obs}.
\]

這一層仍完整執行：

- 局部稽核；
- 跨軸約束；
- 根因追蹤；
- 時間依賴；
- 固定點；
- 補帳；
- FDCS 基礎投影。

### 3.2 建立分支依賴圖

對每個語境 \(c\)，Runtime 建立獨立依賴圖副本：

\[
G^{(c)}\leftarrow G^{obs}.
\]

對每個干預目標 \(X\)：

\[
InEdges_{G^{(c)}}(X)\leftarrow\varnothing.
\]

切除的每條邊都會記錄：

- source；
- target；
- channels；
- intervention ID。

### 3.3 干預節點執行

干預節點不再執行原算子，而是產生：

```text
operator_version = do_set@0.6:<original_operator>
computed_result  = intervention.value
audited_result   = intervention.value
status           = PASS
intervened       = true
```

它仍保存：

- 原 operator；
- 原 expected result；
- 原來源；
- 座標；
- 時間索引；
- 序列 ID。

因此「替換執行」不等於「刪除歷史」。

### 3.4 反事實申報策略

若原帳本宣告：

\[
X=3,
\]

而分支執行：

\[
do(X=10),
\]

則不能再把觀測申報值 3 當成反事實答案，否則所有合法分支都會被錯判 FAIL。

因此 v0.6 採用：

```text
counterfactual_declared_results_ignored = true
```

原申報值仍留在 `original_declared_result`，但不參與該分支的 value invariant。

來源等式同理：觀測來源仍保留，但反事實分支不要求干預後的 base 等於觀測 source value。

### 3.5 後代重算

干預節點完成後，Runtime 依新的 DAG 拓撲順序重新執行後代。後代仍使用原算子、原 operand 與原結構方程。

這使干預不是把所有後代直接平移，而是讓變化沿原模型傳播。

---

## 4. 多語境平行演化

### 4.1 分支隔離

每個語境擁有：

- 自己的 dependency edges；
- 自己的切邊集合；
- 自己的交易結果；
- 自己的 FDCS 權重；
- 自己的 semantic hash。

Runtime 不會把某分支的 `TransactionResult` 寫回 `MatrixLedger`。

### 4.2 實際併行

當：

```yaml
parallel_workers: 3
```

且存在多個語境時，Runtime 使用 `ThreadPoolExecutor` 執行分支。

輸出會標記：

```text
execution_mode = parallel_thread_pool
```

完成後仍依 context ID 排序，因此執行完成先後不影響輸出與雜湊。

### 4.3 不把語境冒充機率

v0.6 不為語境提供：

- 發生機率；
- posterior；
- 樣本權重；
- 貝氏更新；
- 真實世界選擇。

它只表示：

> 在同一份已宣告模型上，執行多個互相隔離的條件分支。

---

## 5. 方向不對稱權重

### 5.1 正向權重

正向權重用於父節點到子節點的因果傳播描述：

\[
\omega_{ij}^{\rightarrow}.
\]

### 5.2 反向權重

反向權重用於：

- 稽核回溯；
- 根因查詢；
- 影響逆向檢索；
- UI 或 Agent 的反向路徑排序。

它記作：

\[
\omega_{ij}^{\leftarrow}.
\]

但這不是：

\[
j\rightarrow i.
\]

也不是逆時間或逆因果。

### 5.3 局部覆寫

全域可設定：

```yaml
direction_weights:
  forward: 1.0
  reverse: 0.25
```

子交易也可覆寫：

```yaml
context:
  causal_weight: 2.0
  causal_weight_forward: 1.5
  causal_weight_reverse: 0.25
```

---

## 6. 分形層級衰減

每筆交易可宣告：

```yaml
context:
  fractal_level: 2
```

父子層級差：

\[
\Delta \ell_{ij}
=
|\ell_j-\ell_i|.
\]

衰減因子：

\[
F_{ij}
=
\mu^{\Delta \ell_{ij}}.
\]

若 \(\mu<1\)，跨越越多層級，權重越小。

這一機制目前只使用明示層級，不會自動推斷：

- 哪些節點屬於哪一層；
- 層級是否真為分形；
- 最佳 \(\mu\)；
- 跨層關係是否符合真實因果。

---

## 7. 最小案例

觀測鏈：

\[
seed=2,
\]

\[
root=seed+1=3,
\]

\[
mid=2root=6,
\]

\[
leaf=mid+4=10.
\]

### 7.1 干預 root

\[
do(root=10).
\]

切邊：

\[
seed\rightarrow root.
\]

新結果：

\[
seed=2,
\quad
root=10,
\quad
mid=20,
\quad
leaf=24.
\]

變動集合：

\[
\{root,mid,leaf\}.
\]

### 7.2 干預 mid

\[
do(mid=1).
\]

切邊：

\[
root\rightarrow mid.
\]

新結果：

\[
seed=2,
\quad
root=3,
\quad
mid=1,
\quad
leaf=5.
\]

祖先 `seed`、`root` 不變。

### 7.3 只改語境權重

語境：

```yaml
id: high-weight
modulation: 2.0
interventions: []
```

所有交易值不變，但 FDCS edge weights 乘以 2。

這證明 Runtime 能區分：

\[
\text{狀態分支}
\neq
\text{權重語境}.
\]

---

## 8. E6 隨機實驗

### 8.1 干預實驗設計

共生成：

- 64 個鏈式帳本；
- 每帳本 32 筆交易；
- 每帳本 2 個隨機內部節點干預；
- 每帳本 1 個只改 modulation 的語境；
- 每條鏈使用隨機初值與隨機增量。

對干預目標 \(k\) 與替換值 \(v\)：

1. 索引小於 \(k\) 的祖先必須維持觀測值；
2. 第 \(k\) 格必須等於 \(v\)；
3. 後續格依原增量重新累積；
4. 只允許切除第 \(k-1\rightarrow k\) 邊；
5. 無干預語境的全部值必須與觀測分支一致；
6. 重跑分支雜湊必須相同。

### 8.2 干預結果

| 指標 | 結果 |
|---|---:|
| 帳本數 | 64 |
| 每帳本交易 | 32 |
| 反事實分支／帳本 | 2 |
| 權重語境／帳本 | 1 |
| 反事實格級檢查 | 4,096 |
| 正確值 | 4,096 |
| Branch value accuracy | **1.0** |
| 切邊檢查 | 128 |
| 正確切邊 | 128 |
| Cut-edge accuracy | **1.0** |
| 祖先穩定檢查 | 2,143 |
| 正確保持不變 | 2,143 |
| Ancestor stability | **1.0** |
| 無干預語境檢查 | 2,048 |
| 正確保持不變 | 2,048 |
| Context independence | **1.0** |
| 雜湊重跑檢查 | 256 |
| 一致 | 256 |
| Determinism | **1.0** |

本次分支格級吞吐量約：

\[
2,500\sim2,650\text{ 格／秒},
\]

但此數字受 Python、ThreadPool 建立成本、機器負載與帳本尺寸影響，不作普遍效能主張。

### 8.3 權重實驗設計

生成：

- 64 個帳本；
- 每帳本 64 條邊；
- 共 4,096 條邊；
- 隨機時間 lag；
- 隨機分形層級；
- 隨機 base weight；
- 隨機 forward factor；
- 隨機 reverse factor；
- 隨機 context modulation。

每條邊皆由獨立公式重新計算預期值，再與 Runtime 輸出比較。

### 8.4 權重結果

| 指標 | 結果 |
|---|---:|
| Edge checks | 4,096 |
| Forward passes | 4,096 |
| Forward accuracy | **1.0** |
| Reverse passes | 4,096 |
| Reverse accuracy | **1.0** |
| 可辨識不對稱邊 | 4,096 |
| 非零層級差邊 | 3,274 |
| 非零時間 lag 邊 | 3,097 |

---

## 9. 回歸測試

v0.6 新增 7 項 E6 測試：

1. 干預切邊與後代重算；
2. 中間節點干預只影響目標與後代；
3. 多語境獨立與併行模式；
4. 方向、時間與分形權重公式；
5. 不存在的干預目標明示錯誤；
6. 語境分支雜湊決定性；
7. 固定點群組內干預拒絕。

總回歸：

\[
\boxed{42\text{ 項測試全部通過}}
\]

E0–E6 全部重新執行：

| 階段 | 主要結果 |
|---|---|
| E0 | 算術與反抵消 precision／recall 1.0 |
| E1 | 8,192／8,192 符號交換通過，負對照成功失敗 |
| E2 | 8,192 筆 DAG，根因與污染 precision／recall 1.0 |
| E3 | 方向中立、方向敏感與空間引用全部通過 |
| E4 | 160／160 與 flat-table 參考一致，修復與歧義保留通過 |
| E5 | 4,096 跨期交易、128 收縮循環、32 發散負對照、256 補帳全部通過 |
| E6 | 干預、切邊、祖先穩定、語境隔離與權重全部通過 |

---

## 10. 回歸中發現的相容性問題

第一輪 E6 實作曾將 v0.5 的 top-level `interventions` 自動升級為可執行分支，導致既有測試預期：

```text
PROJECTED
```

變成：

```text
EXECUTED
```

這代表新版破壞了舊格式語義。

修正後：

- MMLF v0.1–v0.5 的 top-level interventions 仍保持 `DECLARED_NOT_EXECUTED`；
- 只有 MMLF v0.6 的 `contexts` 或 v0.6 top-level interventions 會執行；
- 舊版 35 項測試全部恢復通過。

此修正很重要，因為版本相容不只是「檔案載得進來」，還包括：

\[
\text{舊文件不能被新版偷偷賦予更強的執行副作用。}
\]

---

## 11. CLI 與輸出

新增：

```bash
mmlc simulate-fdcs <ledger> --output <dir> --deterministic
```

輸出：

```text
run_result.json
report.md
events.jsonl
manifest.json
fdcs_analysis.json
fdcs_report.md
```

`fdcs_analysis.json` 保存：

- 基礎節點與邊；
- 正向／反向權重；
- 觀測語境；
- 所有反事實語境；
- 每個語境的 values；
- changed transactions；
- deltas；
- cut edges；
- interventions；
- semantic hash；
- execution hash；
- context modulation。

---

## 12. 方法邊界

### 12.1 已完成

v0.6 已完成：

- 已知 DAG 上的 literal `do_set`；
- 傳入邊切斷；
- 後代決定性重算；
- 祖先／非後代穩定；
- 多語境獨立分支；
- thread-pool 併行執行；
- 分支差異與雜湊；
- 時間衰減；
- 分形層級衰減；
- 正向／反向查詢權重。

### 12.2 尚未完成

v0.6 尚未完成：

- `do_operator`；
- `do_edge`；
- stochastic intervention；
- soft intervention；
- policy intervention；
- 固定點群組內干預；
- 干預後重新求解循環系統；
- 從資料學習 causal graph；
- 識別 confounder；
- 機率反事實；
- SCM 可識別性證明；
- 分形層級自動生成；
- 多分支合併；
- 分支間通信；
- GPU／分散式併行。

### 12.3 不應宣稱

目前不能宣稱：

- MMLC 已成為完整 Pearl SCM；
- 帳本依賴圖等於真實世界因果圖；
- reverse weight 證明逆因果；
- 分形層級一定具有自然本體論；
- 多語境分支具有真實機率；
- ThreadPool 一定提高吞吐量；
- E6 已解決一般循環干預問題。

---

## 13. 現階段結論

v0.5 的 FDCS 是：

\[
\text{可投影但不可干預}.
\]

v0.6 推進為：

\[
\text{可投影}
\rightarrow
\text{可切邊}
\rightarrow
\text{可建立反事實分支}
\rightarrow
\text{可重算後代}
\rightarrow
\text{可並行比較語境}.
\]

因此可以確認：

\[
\boxed{
\text{MMLC 已具備第一版可執行、可稽核的離散虛擬干預能力。}
}
\]

更精確地說，它不是自行發現因果，而是在使用者已提供：

- 節點；
- 結構方程；
- 依賴邊；
- 時間；
- 層級；
- 語境；
- 干預；

之後，可靠地執行與記錄這些分支。

---

## 14. 下一階段建議

下一版可進入 **MMLC Runtime v0.7／E7**：

\[
\boxed{
\text{軟干預}
+
\text{循環干預重新求解}
+
\text{分支差分帳本}
+
\text{干預可識別性與衝突檢查}
}
\]

建議拆為四個可驗證節點：

1. `do_operator`：替換算子或參數，而非直接指定狀態；
2. fixed-point intervention：切斷或固定循環內部分變數後重新求解；
3. branch delta ledger：不複製全部結果，只保存與觀測分支的最小差分；
4. intervention conflict audit：偵測同一語境中的重複目標、互斥干預與不可識別操作。

在 E7 通過以前，不應把 v0.6 描述成通用動態因果求解器。
