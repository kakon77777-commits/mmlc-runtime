# MMLC Runtime v0.8：機率分支、不確定性傳播、政策選擇與最小追加觀測

**文件編號：** EML-MMLC-2026-R08-E8  
**版本：** v0.8.0  
**日期：** 2026-07-23  
**作者：** Neo.K × Aletheia（GPT-5.6 Thinking）  
**專案：** EveMissLab／MMLC Runtime

---

## 摘要

MMLC Runtime v0.7 已能在已知結構方程下執行硬干預、軟干預、循環固定點重求解、分支差分帳與有限觀測可區分性稽核。v0.8 的目標，是在不把模型分支機率冒充成現實世界客觀機率的前提下，補上四個可執行閉環：

1. 對明示反事實分支附加離散機率；
2. 對各交易結果建立不確定性分布；
3. 將干預效益、風險與成本統一成可稽核政策分數；
4. 在既有觀測不足時，精確搜尋最小追加觀測集合。

本版新增 MMLF v0.8、`mmlc/uncertainty.py`、三個範例、七項新測試與 E8 隨機實驗。完整回歸共有 56 項測試全部通過。E8 隨機實驗涵蓋 64 個政策帳本、256 個政策群組、1,024 條機率分支、64 個可解追加觀測案例與 32 個結構上不可解案例，所有機率質量、期望值、變異數、政策分數、最小觀測集合與重跑雜湊均符合預期。

本結果證明的是：**在 supplied deterministic model、明示離散機率、效用、風險、成本與候選觀測集合下，MMLC 能執行可重現的不確定性聚合、條件式政策排序與有限精確觀測規劃。**它不證明分支機率是真實頻率，也不等於一般統計因果識別或現實政策最佳化。

---

## 1. 版本目標

v0.8／E8 的原始目標為：

\[
\boxed{
\text{機率分支}
+
\text{不確定性傳播}
+
\text{干預成本與政策選擇}
+
\text{最小追加觀測集合}
}
\]

這四部分互相關聯，但必須保持概念分離：

- **分支機率**描述 supplied model 中各情境的宣告權重；
- **不確定性傳播**聚合各分支的交易值；
- **政策選擇**依使用者宣告的目標、成本與風險偏好排序；
- **追加觀測規劃**只處理模型分支的有限可區分性。

Runtime 不會從沒有資料的地方自行估計機率，也不會把政策分數包裝成普遍價值判斷。

---

## 2. MMLF v0.8 格式

語境分支新增四個欄位：

```yaml
fdcs:
  contexts:
    - id: policy-a-low
      policy_id: policy-a
      scenario_id: low
      probability: 0.6
      cost: 2.0
      interventions:
        - id: set-outcome-low
          kind: do_set
          target_tx_id: outcome
          value: 8
```

其語義為：

- `policy_id`：同一候選政策的情境群組；
- `scenario_id`：群組內情境身分；
- `probability`：該情境在政策條件下的宣告機率；
- `cost`：該分支的明示成本。

政策群組內要求：

\[
\sum_{s\in S_p}P(s\mid p)=1.
\]

目前容忍度由：

```yaml
probability_model:
  tolerance: 1.0e-12
```

控制。

### 2.1 機率失敗條件

以下情況會使群組判定 `FAIL`：

- 機率不是有限非負數；
- 群組機率總和不等於 1；
- 正機率分支未成功執行；
- 正機率落在 `CONFLICT` 分支；
- 分支不存在或缺少結果。

Runtime 不會把失敗分支的機率質量偷偷重新正規化到其他分支。

---

## 3. 離散不確定性傳播

對政策群組 \(p\) 與交易 \(X\)，每個情境產生一個決定性值：

\[
X_s=x_s,
\qquad
P(s\mid p)=q_s.
\]

Runtime 建立離散支撐：

\[
\mathcal D_p(X)
=
\{(x_s,q_s)\}_{s\in S_p}.
\]

等價值會被合併，其機率質量相加。數值型交易另外計算：

\[
\mathbb E[X\mid p]
=
\sum_s q_sx_s,
\]

\[
\operatorname{Var}(X\mid p)
=
\sum_s q_s(x_s-\mathbb E[X\mid p])^2,
\]

\[
\sigma_X=\sqrt{\operatorname{Var}(X\mid p)}.
\]

離散熵為：

\[
H(X\mid p)
=-\sum_{x\in\operatorname{supp}(X)}P(x)\log_2P(x).
\]

每筆交易輸出：

- `support_size`；
- `support`；
- `entropy_bits`；
- `deterministic`；
- `expected_value`；
- `variance`；
- `standard_deviation`；
- `minimum`；
- `maximum`。

非數值型結果仍可建立支撐集與熵，但不偽造期望值與變異數。

### 3.1 範例

政策 A：

\[
P(X=8)=0.6,
\qquad
P(X=14)=0.4.
\]

因此：

\[
\mathbb E[X]=0.6(8)+0.4(14)=10.4,
\]

\[
\operatorname{Var}(X)=8.64,
\]

\[
\sigma_X\approx2.9393876913,
\]

\[
H(X)\approx0.9709505945\text{ bits}.
\]

Runtime 的輸出與上述解析值一致。

---

## 4. 干預成本與政策選擇

政策選擇設定：

```yaml
fdcs:
  policy_selection:
    enabled: true
    risk_aversion: 0.2
    cost_weight: 1.0
    objectives:
      - tx_id: outcome
        direction: maximize
        weight: 1.0
```

對情境 \(s\)，多目標效用定義為：

\[
U_s
=
\sum_k d_k w_k X_{k,s},
\]

其中：

\[
d_k=
\begin{cases}
+1,&\text{maximize},\\
-1,&\text{minimize}.
\end{cases}
\]

政策的期望效用與效用風險為：

\[
\mathbb E[U\mid p]=\sum_s q_sU_s,
\]

\[
\sigma_U(p)
=
\sqrt{\sum_s q_s(U_s-\mathbb E[U\mid p])^2}.
\]

期望成本：

\[
\mathbb E[C\mid p]
=
\sum_s q_sC_s.
\]

政策分數：

\[
\operatorname{Score}(p)
=
\mathbb E[U\mid p]
-ho\sigma_U(p)
-\gamma\mathbb E[C\mid p],
\]

其中 \(\rho\) 是風險厭惡係數，\(\gamma\) 是成本權重。

### 4.1 範例比較

政策 A：

\[
\mathbb E[U_A]=10.4,
\qquad
\sigma_A\approx2.9394,
\qquad
C_A=2.
\]

在 \(\rho=0.2,\gamma=1\) 下：

\[
Score(A)
\approx10.4-0.2(2.9394)-2
\approx7.81212.
\]

政策 B：

\[
\mathbb E[U_B]=9,
\qquad
\sigma_B=4,
\qquad
C_B=0.5,
\]

\[
Score(B)=9-0.2(4)-0.5=7.7.
\]

Runtime 因此選擇政策 A。若多個政策分數落在 `tie_tolerance` 內，Runtime 會保留全部最佳政策，不任意破壞平手。

### 4.2 方法邊界

此分數不是客觀倫理函數，也不是自動政策正當性。它只代表：

> 在 supplied model、明示情境機率、目標權重、風險係數與成本權重下，哪個政策具有最高條件式分數。

---

## 5. 最小追加觀測集合

v0.7 已能根據既有觀測交易建立語境等價類。v0.8 進一步回答：

> 若目前觀測不足，最少再觀測哪些交易，才能區分所有目前仍混合的可執行分支？

### 5.1 問題形式化

設目前觀測集合為 \(O\)。若兩個語境 \(c_i,c_j\) 滿足：

\[
\operatorname{Sig}_O(c_i)
=
\operatorname{Sig}_O(c_j),
\]

則它們形成一個未區分配對：

\[
p_{ij}=(c_i,c_j).
\]

對候選交易 \(x\)，若：

\[
X_x(c_i)\neq X_x(c_j),
\]

則 \(x\) 可以切開配對 \(p_{ij}\)。

令：

\[
D_{ij}
=
\{x\mid X_x(c_i)\neq X_x(c_j)\}.
\]

要找追加觀測集合 \(A\)，使：

\[
A\cap D_{ij}\neq\varnothing
\qquad
\forall p_{ij}.
\]

並最小化：

\[
|A|.
\]

這是有限精確 hitting-set 問題。v0.8 以組合搜尋求所有最小方案，並設候選數、最大追加數與最大方案數上限。

### 5.2 可解案例

基線：

\[
root=3,
\qquad
mid=6,
\qquad
leaf=6.
\]

語境一：

\[
do(root=4)
\Rightarrow
(root,mid,leaf)=(4,8,8).
\]

語境二：

\[
do(mid=8)
\Rightarrow
(root,mid,leaf)=(3,8,8).
\]

只看 `leaf` 時，兩個語境皆為 8，因此不可區分。追加觀測 `root` 後：

\[
4\neq3.
\]

故唯一最小追加集合為：

\[
\boxed{\{root\}}.
\]

### 5.3 不可解案例

若：

\[
do(root=4)
\]

與：

\[
soft\_shift(root,+1)
\]

在 supplied model 中對所有候選交易都產生相同值，則：

\[
D_{ij}=\varnothing.
\]

Runtime 回傳：

```text
status = IMPOSSIBLE
```

而不是假裝只要多量一次就能辨認不同機制。

### 5.4 狀態

- `ALREADY_DISTINGUISHABLE`：既有觀測已足夠；
- `FOUND`：找到一組或多組最小方案；
- `IMPOSSIBLE`：至少一對分支在所有候選交易上完全相同；
- `NOT_FOUND_WITHIN_LIMIT`：最大追加數不足；
- `SEARCH_LIMIT`：候選數超過精確搜尋上限。

---

## 6. 實作結構

新增模組：

```text
mmlc/uncertainty.py
```

主要函式：

```text
build_probability_analysis
build_policy_analysis
build_observation_plan
```

Runtime 執行順序：

```text
觀測基線
→ 反事實語境平行執行
→ 干預衝突隔離
→ 有限觀測可識別性
→ 機率群組稽核
→ 交易不確定性聚合
→ 政策效用／風險／成本評分
→ 最小追加觀測搜尋
→ 決定性分析雜湊
```

輸出新增：

```text
fdcs_projection.probability_analysis
fdcs_projection.policy_analysis
fdcs_projection.observation_plan
```

全域稽核摘要新增：

```text
fdcs_probability_status
fdcs_policy_status
fdcs_observation_plan_status
```

---

## 7. 自動測試

v0.8 新增七項 E8 測試：

1. 離散支撐、期望值、變異數與熵；
2. 政策期望效用、風險、成本與排名；
3. 政策群組機率質量必須為 1；
4. 正機率不得落在衝突分支；
5. 精確找到最小追加觀測 `{root}`；
6. 結構上不可區分時回傳 `IMPOSSIBLE`；
7. 機率與政策分析雜湊決定性重跑一致。

完整測試：

\[
\boxed{56\text{ 項全部通過}}
\]

E0–E7 舊測試全部保留，表示 v0.8 未破壞：

- 算術與反抵消；
- 符號—數值交換；
- 根因與污染；
- 多方向矩陣執行；
- 跨軸修復；
- 時間、固定點與補帳；
- 硬／軟干預；
- 分支差分與可識別性。

---

## 8. E8 隨機實驗

隨機種子：

```text
20260723
```

完整指標：

```text
outputs/e8_probability_policy_observation/metrics.json
```

### 8.1 機率與政策實驗

| 指標 | 結果 |
|---|---:|
| 隨機政策帳本 | 64 |
| 政策群組 | 256 |
| 機率分支 | 1,024 |
| 機率質量錯誤 | 0 |
| 期望值／變異數錯誤 | 0 |
| 政策分數／選擇錯誤 | 0 |
| 決定性分析雜湊錯誤 | 0 |
| Accuracy | 1.0 |

每個政策有四個隨機情境；情境機率由隨機正權重正規化。實驗獨立計算解析期望、變異數、成本、風險與分數，再與 Runtime 輸出比較。

### 8.2 追加觀測實驗

| 指標 | 結果 |
|---|---:|
| 可解帳本 | 64 |
| 正確找到最小大小 1 | 64 |
| 可解案例錯誤 | 0 |
| 結構不可解帳本 | 32 |
| 正確回傳 `IMPOSSIBLE` | 32 |
| 不可解案例錯誤 | 0 |
| Accuracy | 1.0 |

本次共搜尋 192 個候選集合。所有可解案例的唯一最小方案均為：

```text
[root]
```

---

## 9. E0–E8 完整回歸

| 階段 | 結果 |
|---|---|
| E0 | 算術、竄改定位與反抵消通過 |
| E1 | 8,192／8,192 符號—數值交換通過 |
| E2 | 根因與污染 precision／recall 1.0 |
| E3 | 方向中立、方向敏感、空間引用與路由通過 |
| E4 | 160／160 與獨立 flat-table 參考一致 |
| E5 | 4,096 個跨期交易、固定點與補帳通過 |
| E6 | 4,096 個反事實值、切邊與權重通過 |
| E7 | 2,048 個軟干預值、128 條循環分支與識別性通過 |
| E8 | 1,024 條機率分支與 96 個觀測規劃案例通過 |

整套腳本因單次命令執行時間上限，在 E3 後被外部命令層截斷；此後 E4 與 E5–E8 分段重新執行並全部通過。這是執行封裝層的逾時，不是實驗失敗。

---

## 10. 誠實邊界

### 10.1 機率不是自動學習

v0.8 的 \(P(s\mid p)\) 全部由文件宣告。Runtime 只驗證與聚合，不會：

- 從歷史資料估計機率；
- 校準預測分布；
- 給出貝葉斯後驗；
- 自動判斷分支是否完整涵蓋現實。

### 10.2 不確定性是分支不確定性

目前處理的是有限離散模型分支，不包括：

- 連續隨機變數；
- 算子內部噪聲；
- 測量誤差模型；
- 相關隨機源；
- 一般機率固定點。

### 10.3 政策分數不是價值真理

政策排名高度依賴：

- 目標交易；
- maximize／minimize 方向；
- 權重；
- 風險厭惡；
- 成本定義；
- supplied model；
- supplied probabilities。

改變判定域，排名可能改變。

### 10.4 追加觀測只在目前模型內成立

找到 `{root}`，只代表它能區分目前 supplied branches；不代表：

- 現實中一定可觀測；
- 量測沒有成本或誤差；
- 未列入模型的機制也可被區分；
- 它是一般因果識別的充分統計量。

### 10.5 精確搜尋具有組合限制

最小追加觀測使用有限組合搜尋。v0.8 提供：

- `max_candidates`；
- `max_additional_observations`；
- `max_solutions`。

大規模問題未接 SAT、ILP、SMT 或近似集合覆蓋求解器。

---

## 11. 結論

MMLC 的技術鏈目前已推進為：

\[
\text{格級計算}
\rightarrow
\text{多層稽核}
\rightarrow
\text{符號交換}
\rightarrow
\text{根因追蹤}
\rightarrow
\text{方向與時間}
\rightarrow
\text{固定點與修復}
\rightarrow
\text{硬／軟反事實}
\rightarrow
\text{有限可識別性}
\rightarrow
\text{離散機率分支}
\rightarrow
\text{不確定性傳播}
\rightarrow
\text{政策評分}
\rightarrow
\text{追加觀測規劃}.
\]

現階段可以確認：

\[
\boxed{
\text{MMLC 已具備第一版可稽核的離散機率反事實帳本、條件式政策排序與有限精確觀測規劃。}
}
\]

但不能宣稱：

- 已從現實資料學得真實機率；
- 已完成一般隨機因果模型；
- 政策分數可替代人類價值判斷；
- 最小追加觀測在模型外仍充分；
- 已普遍優於機率程式、決策分析、POMDP、SMT 或統計因果框架。

下一個合理階段為 MMLC Runtime v0.9／E9：

\[
\boxed{
\text{連續分布近似}
+
\text{相關不確定性}
+
\text{觀測成本}
+
\text{資訊價值}
+
\text{序貫決策}
}
\]
