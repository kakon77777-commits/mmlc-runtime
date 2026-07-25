# MMLC Runtime v0.2：實作與 E1／E2 驗證報告

**版本**：0.2.0  
**日期**：2026-07-21  
**研究階段**：矩陣帳本計算的符號一致性與依賴根因驗證

---

## 摘要

MMLC Runtime v0.1 已證明靜態矩陣帳本可以完成四則運算、精確分數、算子不變式、局部錯誤定位、反抵消與決定性重跑。v0.2 進一步驗證兩個此前尚未正式完成的核心：

1. **E1 符號—數值交換**：先執行符號帳本再代入，是否等價於先代入再直接執行數值帳本；
2. **E2 依賴流與根因追蹤**：錯誤在 DAG 中傳播時，系統能否區分原始局部錯帳、下游污染與健康分支。

結果如下：

- 14 項自動回歸測試全部通過；
- E0 的 1,024 筆算術壓力測試維持 precision / recall = 1.0 / 1.0；
- E1 共 8,192 個格級交換比較全部通過；
- 一個刻意不交換的負對照算子被正確判為失敗；
- E2 共 8,192 筆 DAG 交易中，384 個真實根因與 3,635 個污染節點全部正確辨識；
- 根因與污染 precision / recall 均為 1.0 / 1.0；
- 根因路徑錯配為 0；
- 欄位敏感信任成功區分 `computed_result` 與 `audited_result`；
- 根因路徑演算法由逐根 BFS 改為單次拓撲傳播，消除了大量獨立錯帳下的效能退化。

這些結果支持以下有限結論：

> MMLC 的符號—數值交換層與 DAG provenance 根因層具有技術可行性。

但這仍不是對未知現實因果的自動發現，也尚未證明 MMLC 優於既有 AST、DAG、試算表或 provenance 系統。

---

# 1. v0.2 的問題設定

## 1.1 E1：符號—數值交換

令 $L$ 為符號矩陣帳本，$	heta$ 為符號代入映射。需要驗證：

$$
\boxed{
\operatorname{Eval}_{\theta}
\bigl(\operatorname{Execute}(L)\bigr)
=
\operatorname{Execute}
\bigl(\operatorname{Eval}_{\theta}(L)\bigr)
}
$$

左路徑為：

$$
L
\xrightarrow{\operatorname{Execute}}
R_{\mathrm{sym}}
\xrightarrow{\operatorname{Eval}_{\theta}}
R_{\mathrm{sym}\to\mathrm{num}}.
$$

右路徑為：

$$
L
\xrightarrow{\operatorname{Eval}_{\theta}}
L_{\theta}
\xrightarrow{\operatorname{Execute}}
R_{\mathrm{direct}}.
$$

判定條件：

$$
R_{\mathrm{sym}\to\mathrm{num}}
\equiv
R_{\mathrm{direct}}.
$$

等價判定優先使用：

1. SymPy 精確化簡；
2. 整數與有理數精確相等；
3. 尺度化浮點容差。

## 1.2 E2：依賴污染與根因

對交易 DAG：

$$
G=(V,E),
$$

每個節點 $T_i$ 分成兩個狀態：

$$
S_i^{\mathrm{local}}
\in
\{\mathrm{PASS},\mathrm{FAIL},\mathrm{ERROR}\},
$$

以及加入上游可信度後的：

$$
S_i
\in
\{\mathrm{PASS},\mathrm{FAIL},\mathrm{ERROR},\mathrm{TAINTED}\}.
$$

其中：

$$
S_i=\mathrm{TAINTED}
$$

表示本格不變式可以成立，但輸入來自不可信上游，因此結果不可視為獨立可信。

---

# 2. 核心實作

## 2.1 MMLF v0.2

新增根層：

```yaml
evaluation_scenarios:
  - id: positive-integers
    bindings: {x: 2, y: 5}
  - id: exact-fractions
    bindings: {x: "frac:1/2", y: "frac:3/2"}
```

Runtime 同時保留 MMLF v0.1 載入能力。

## 2.2 不可變帳本實例化

`instantiate_ledger()` 不修改原符號帳本，而是產生一個新的 bound ledger：

$$
L_{\theta}=\operatorname{Instantiate}(L,\theta).
$$

代入作用於：

- 來源物件；
- base；
- operand；
- declared result；
- context；
- boundary events。

ValueRef 保持引用身份，不在代入階段被提前求值。

## 2.3 狀態分離

v0.2 將交易結果拆成：

- `computed_result`：Runtime 按算子重新計算的結果；
- `audited_result`：帳本申報或待稽核的結果；
- `local_status`：本格自身狀態；
- `status`：加入依賴信任後的狀態。

這使下列情況可被區分：

```text
上游計算值正確，但申報值被竄改
```

此時引用 `computed_result` 的下游可以保持 PASS，而引用 `audited_result` 的下游必須 TAINTED。

## 2.4 欄位敏感依賴邊

依賴邊不再只是：

$$
T_i\rightarrow T_j,
$$

而是攜帶通道：

$$
T_i.\mathrm{result}\rightarrow T_j.\mathrm{base},
$$

或：

$$
T_i.\mathrm{audited\_result}\rightarrow T_j.\mathrm{base}.
$$

信任規則：

- `audited_result`：上游必須整體 PASS；
- `result`：若上游只是 value mismatch，而 Runtime 計算通道仍有效，可以繼續信任；
- explicit dependency：採保守傳播；
- ERROR、TAINTED、來源錯誤、型別錯誤或定義域錯誤：計算通道亦不可信。

## 2.5 根因定義

v0.2 中的根因不是現實世界的形上因果，而是：

> 在已知依賴 DAG 中，沿不可信資料通道向上追溯所遇到的最早局部 FAIL 或 ERROR。

對每個非 PASS 節點，系統輸出：

- root cause set；
- unhealthy direct dependencies；
- dependency channels；
- 每個根因到該節點的一條穩定 witness path；
- affected-by-root 集合。

## 2.6 根因演算法優化

初版使用每個根因對每個節點執行 BFS，近似成本為：

$$
O(RV(V+E)).
$$

當 E0 壓力測試出現 512 個獨立根因時，效能明顯退化。

正式版改為拓撲序動態傳播：

$$
\mathcal R(T_i)
=
\bigcup_{T_p\in U_i}
\mathcal R(T_p),
$$

其中 $U_i$ 是對 $T_i$ 真正不可信的上游集合。若沒有可繼承根因而本地失敗，則：

$$
\mathcal R(T_i)=\{T_i\}.
$$

這使路徑與根因只需沿 DAG 執行一次。

---

# 3. 自動測試

共 14 項：

1. 正確四則運算；
2. 單欄錯誤定位；
3. 除零明示錯誤；
4. 反抵消；
5. 循環依賴拒絕；
6. 顯示重排不改語義；
7. semantic hash 重現；
8. schema 缺失拒絕；
9. 符號不變式；
10. DAG 拓撲執行；
11. E1 三組代入情境；
12. 單根因污染鏈；
13. 雙根因匯流；
14. `result`／`audited_result` 欄位敏感污染。

結果：

$$
\boxed{14/14\ \mathrm{PASS}}
$$

---

# 4. E0 回歸結果

## 4.1 手工案例

- audit precision = 1.0；
- audit recall = 1.0；
- 正確、竄改、反抵消、除零案例皆符合預期。

## 4.2 1,024 筆壓力測試

| 指標 | 結果 |
|---|---:|
| 交易總數 | 1,024 |
| 正確交易 | 512 |
| 竄改交易 | 512 |
| True positive | 512 |
| False positive | 0 |
| False negative | 0 |
| Precision | 1.0 |
| Recall | 1.0 |
| 有號殘差總和 | 0 |
| 絕對殘差總和 | 512 |
| 抵消偵測 | True |
| 顯示重排 hash 不變 | True |
| 三次重跑一致 | True |
| 本次 Runtime | 約 0.092 秒 |
| 吞吐量 | 約 11,176 筆／秒 |

此結果也驗證根因演算法優化後，大量獨立錯帳不再造成明顯停滯。

---

# 5. E1 實驗結果

## 5.1 正向隨機測試

設定：

- 隨機種子：20260721；
- 128 個符號 ledger；
- 每個 ledger 8 筆交易；
- 每個 ledger 8 組代入；
- 算子：加、減、乘、除；
- 代入包含正整數、負整數、零與精確分數。

總比較數：

$$
128\times8\times8=8192.
$$

| 指標 | 結果 |
|---|---:|
| 格級比較 | 8,192 |
| 通過 | 8,192 |
| 失敗 | 0 |
| Exchange accuracy | 1.0 |
| 失敗 ledger | 0 |
| 本次耗時 | 約 9.45 秒 |

## 5.2 負對照

定義一個刻意依賴「自由符號數量」的算子：

$$
f(z)=|\operatorname{FreeSymbols}(z)|.
$$

對 $z=x$、$x\mapsto2$：

先執行再代入：

$$
f(x)=1\mapsto1.
$$

先代入再執行：

$$
f(2)=0.
$$

因此：

$$
1\neq0.
$$

E1 harness 正確輸出 FAIL。這說明測試不是無條件報喜，而能偵測真正的非交換算子。

## 5.3 E1 結論

在目前支援的純代數算子與測試域中：

$$
\boxed{
\operatorname{Eval}_{\theta}\circ\operatorname{Execute}
=
\operatorname{Execute}\circ\operatorname{Eval}_{\theta}
}
$$

但不能推廣成「所有算子都交換」。算子若依賴：

- 符號本身的結構；
- 表達式大小；
- 自由符號數；
- 求值順序；
- 浮點捨入；
- 隨機性；
- 外部狀態；

便可能不交換，必須逐算子驗證。

---

# 6. E2 實驗結果

設定：

- 隨機種子：20260721；
- 128 個 DAG；
- 每個 DAG 64 筆交易；
- 每個 DAG 8 個來源節點；
- 從來源節點隨機選 3 個根因；
- 後續節點具有 1 至 2 個上游；
- 下游使用 `audited_result`，因此錯帳會沿資料通道傳播。

總交易數：

$$
128\times64=8192.
$$

| 指標 | 結果 |
|---|---:|
| 真實根因 | 384 |
| 根因 TP | 384 |
| 根因 FP | 0 |
| 根因 FN | 0 |
| 根因 precision | 1.0 |
| 根因 recall | 1.0 |
| 污染節點 TP | 3,635 |
| 污染節點 FP | 0 |
| 污染節點 FN | 0 |
| 污染 precision | 1.0 |
| 污染 recall | 1.0 |
| 根因路徑錯配 | 0 |
| 非 PASS 節點總數 | 4,019 |
| 實際根因數 | 384 |
| 相對樸素根因數減少 | 約 90.45% |
| 本次耗時 | 約 0.65 秒 |
| 吞吐量 | 約 12,626 筆／秒 |

若採用樸素方法，把所有非 PASS 節點都稱為根因，會得到：

$$
4019
$$

個「根因」。v0.2 將其壓縮為真正注入錯誤的：

$$
384.
$$

因此：

$$
1-\frac{384}{4019}
\approx90.45\%.
$$

這個比例不是普遍常數，只是本次 DAG 分布下的結果；其意義是展示「錯誤影響範圍」不能被誤稱為「根因數量」。

---

# 7. 欄位敏感案例

上游：

$$
3+2=5,
$$

但帳本申報為：

$$
6.
$$

因此上游是局部 FAIL。

## 計算通道

下游引用：

```yaml
{ref: origin, field: result}
```

Runtime 提供重新計算值 $5$，再加 $1$ 得：

$$
6.
$$

此交易維持 PASS。

## 申報通道

另一個下游引用：

```yaml
{ref: origin, field: audited_result}
```

取得申報值 $6$，再加 $1$ 得：

$$
7.
$$

其局部算式成立，但來源不可信，因此：

$$
S^{\mathrm{local}}=\mathrm{PASS},
\qquad
S=\mathrm{TAINTED}.
$$

這個例子證明：

$$
\boxed{
\text{計算正確}
\neq
\text{資料可信}
}
$$

也證明 provenance 必須至少細化到欄位／通道，而不能只停在交易節點。

---

# 8. 實作過程中發現並修正的問題

## 8.1 根因 BFS 效能退化

症狀：E0 的 512 個獨立錯帳使根因報告生成超時。

原因：對每個根因與每個交易重複搜尋路徑。

修正：拓撲序動態傳播 root set 與 witness path。

## 8.2 交易級污染過度保守

症狀：上游只有申報結果錯誤時，引用 Runtime 計算值的下游仍被標成 TAINTED。

原因：依賴邊只記錄父子交易，不記錄引用欄位。

修正：加入 `base:result`、`base:audited_result` 等通道標籤與不同信任政策。

## 8.3 根因與症狀混淆

症狀：如果所有非 PASS 節點都列為根因，根因數隨下游規模膨脹。

修正：分離 local failure、taint 與 earliest root cause。

---

# 9. 誠實邊界

## 9.1 E1 是算子性質，不是宇宙定律

E1 的交換性必須針對算子類別與值域驗證。負對照已證明，結構敏感算子可以不交換。

## 9.2 E2 是 provenance，不是未知因果發現

目前系統已知：

- 哪些交易依賴哪些交易；
- 引用了什麼欄位；
- 哪一筆首先違反帳本規則。

因此它做的是：

$$
\text{known-graph fault provenance},
$$

不是從觀測資料中發現未知因果圖。

## 9.3 DAG 限制

目前循環依賴仍被拒絕。尚未定義：

- 時間步更新；
- 固定點語義；
- 迭代收斂；
- 延遲邊；
- 回饋控制；
- FDCS 動態權重。

## 9.4 尚未完成外部基準比較

仍未與以下系統進行正式成本／收益比較：

- Python AST；
- SymPy expression DAG；
- Excel formula dependency graph；
- dataflow framework；
- provenance database；
- spreadsheet auditing tools。

因此不能聲稱 MMLC 已優於它們。

---

# 10. 階段結論

v0.2 可以確認：

$$
\boxed{
\text{符號帳本與數值帳本可以由同一 Runtime 一致執行}
}
$$

$$
\boxed{
\text{局部錯誤、下游污染與根因可以被形式分離}
}
$$

$$
\boxed{
\text{信任傳播必須細化到資料通道，而不只是交易節點}
}
$$

所以目前技術鏈已由：

$$
\text{可計算}
\rightarrow
\text{可稽核}
\rightarrow
\text{可交換驗證}
\rightarrow
\text{可追溯根因}
$$

完成到第四層。

下一階段應進入 MMLC Runtime v0.3：

$$
\boxed{
E3\ \text{矩陣布局與 MMR 多方向執行}
}
$$

並加入：

1. 方向相關依賴與 traversal semantics；
2. 矩陣區域與跨區帳本；
3. 固定點或時間步循環；
4. Excel 公式圖導入；
5. 與 AST／DAG／試算表的正式比較；
6. 最小修復集與自動更正建議。
