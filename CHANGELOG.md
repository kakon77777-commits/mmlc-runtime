# Changelog

## 1.0.0 — 2026-07-23

- 正式凍結 Runtime 1.x 公開 Python API 與 CLI。
- 正式建立 MMLF v1.0 stable schema，並保留 v0.1–v0.9 載入。
- 新增決定性 `mmlc migrate`，包含舊語法正規化、來源語義保留與執行等價驗證。
- 新增 `metadata.migrated_from`／`migration_profile`，避免格式升級偷偷啟用後期功能。
- 修正未知 MMLF 版本被錯當成 v0.1 的問題；現在明示拒絕。
- 將全部 Schema 封裝成 `mmlc.schemas` 套件資源，安裝後仍可驗證。
- 新增 `mmlc info`、`mmlc benchmark`、機器可讀錯誤與 CLI 退出碼。
- 新增穩定 API facade、相容性 manifest 與 release benchmark。
- 新增英文主 README、繁中 README、API／CLI／架構／遷移／相容／限制文件。
- 新增 Apache-2.0、CITATION、NOTICE、SECURITY、CONTRIBUTING 與 GitHub Actions。
- 新增 release-v1 驗證，涵蓋全範例遷移、代表性執行等價、套件安裝與效能基準。
- v1.0 是統合與穩定版，不額外增加新的數學能力。

## 0.9.0 — 2026-07-23

- 正式完成 E9 連續分布近似、相關不確定性、觀測成本、資訊價值與序貫決策。
- 新增 MMLF v0.9 schema。
- 新增 `continuous_uncertainty.ensembles`。
- 新增決定性 antithetic Halton 樣本與 Gaussian copula。
- 新增 normal、uniform、triangular、lognormal 四種邊際。
- 新增相關矩陣對稱、單位對角、範圍與正定性稽核。
- 新增連續樣本到普通 FDCS 干預語境的編譯。
- 新增目標／經驗均值、標準差、共變異數與相關矩陣報告。
- 新增 `observation_costs`，同時輸出最小格數與最低成本追加觀測方案。
- 新增 `information_value` 與單步 gross/net EVSI。
- 新增最多三階的精確有限情境 observe-then-act 動態規劃。
- 新增政策／情境對齊稽核與政策不變事前訊號要求。
- 新增 `continuous_approximation_analysis` 與 `information_value_analysis` 決定性雜湊。
- 新增 3 個 E9 範例、8 項 E9 測試與 E9 隨機實驗。
- 回歸測試擴充至 64 項。
- E9 完成 32 個連續帳本、8,192 條近似分支、32 個非法相關矩陣負對照、32 組序貫決策與 64 組成本感知觀測案例。
- 保留 MMLF v0.1–v0.8 載入與既有執行語義相容性。

## 0.8.0 — 2026-07-23

- 正式完成 E8 機率分支、不確定性傳播、干預成本／政策選擇與最小追加觀測集合。
- 新增 MMLF v0.8 schema。
- 語境分支新增 `probability`、`policy_id`、`scenario_id` 與 `cost`。
- 新增政策群組內機率質量稽核；正機率不得落在衝突或未執行分支。
- 新增每筆交易的離散支撐集、機率質量、期望值、變異數、標準差、極值與 Shannon entropy。
- 新增機率與政策分析的決定性 `analysis_hash`。
- 新增多目標方向權重、風險懲罰、期望成本與政策分數。
- 政策同分時保留所有最佳方案，不強行選出唯一政策。
- 新增精確有限 hitting-set 追加觀測搜尋。
- 新增 `ALREADY_DISTINGUISHABLE`、`FOUND`、`IMPOSSIBLE`、`NOT_FOUND_WITHIN_LIMIT` 與 `SEARCH_LIMIT` 狀態。
- 明示分支機率是文件宣告的模型權重，不是從資料估計的客觀頻率。
- 明示政策排名只在 supplied model、objective、risk 與 cost 假設下成立。
- 新增 3 個 E8 範例與 7 項 E8 測試。
- 回歸測試擴充至 56 項。
- E8 完成 64 個政策帳本、256 個政策群組、1,024 條機率分支、64 個可解觀測案例與 32 個不可解案例。
- 保留 MMLF v0.1–v0.7 載入與既有執行語義相容性。

## 0.7.0 — 2026-07-22

- 正式完成 E7 軟干預、循環干預重求解、分支差分帳與可識別性稽核。
- 新增 MMLF v0.7 schema 與 `observed_transactions`。
- 新增 `soft_affine`、`soft_shift`、`soft_scale` 三種軟干預語法。
- 明確分離硬干預 `do_set` 與軟干預：前者切斷傳入邊，後者保留父節點並修改結構方程輸出。
- 新增 `structural_result` 與 `intervention_kinds`，避免將原方程結果與干預後結果混為一談。
- 允許已宣告 Jacobi 固定點群接受硬／軟干預並重新求解整個循環。
- 新增固定點群內硬干預鎖定與軟仿射方程變換。
- 新增 `MMLC-BRANCH-DIFF v0.7` 分支差分帳與逐筆 SHA-256 雜湊鏈。
- 新增 hard intervention、soft intervention、fixed-point response、descendant response 等差分角色。
- 新增同目標干預衝突、等價重複與冗餘稽核。
- 衝突語境改為分支隔離：標記 `CONFLICT`，不拖垮其他有效語境。
- 新增有限觀測格上的語境簽章、等價類與分支可區分性稽核。
- 明示 ledger identifiability 僅為已知決定性模型中的有限觀測可區分性，不是統計因果識別。
- 新增 3 個 E7 範例與 7 項 E7 測試。
- 回歸測試擴充至 49 項。
- E7 完成 2,048 個軟干預交易值、128 條固定點干預分支、256 組衝突／冗餘案例與 64 組識別性案例。
- 保留 MMLF v0.1–v0.6 載入與既有執行語義相容性。

## 0.6.0 — 2026-07-22

- 正式完成 E6 可執行 FDCS 虛擬干預。
- 新增 MMLF v0.6 schema。
- 新增 `contexts`、`base_context` 與 `parallel_workers`。
- 新增 literal `do_set` 干預。
- 干預節點會切斷傳入依賴邊，並以原結構方程重算後代。
- 反事實分支保留原始申報與來源資料，但不將觀測答案當成反事實答案。
- 新增分支變動交易、delta、切邊與獨立 semantic hash。
- 新增 thread-pool 多語境獨立執行，並保持排序輸出與可重現性。
- 新增時間延遲、分形層級差、語境 modulation 的複合權重。
- 新增 `forward_effective_weight` 與 `reverse_effective_weight`。
- 明示 reverse weight 是回溯／查詢權重，不是逆因果。
- 新增 `simulate-fdcs` CLI 與 `fdcs_analysis.json`／`fdcs_report.md`。
- 禁止干預值暗中引用帳本節點。
- 禁止 v0.6 直接干預固定點群組成員。
- 修正 v0.5 相容性：舊版 top-level interventions 繼續保持 `DECLARED_NOT_EXECUTED`。
- 新增 3 個 E6 範例與 7 項 E6 測試。
- 回歸測試擴充至 42 項。
- E6 完成 4,096 個反事實值、128 條切邊、2,143 個祖先穩定檢查與 4,096 條方向／分形權重驗證。
- 保留 MMLF v0.1–v0.5 相容性。

## 0.5.0 — 2026-07-22

- 正式完成 E5 時間索引、延遲依賴、固定點、不可變補帳與 FDCS 投影。
- 新增 MMLF v0.5 schema。
- 新增交易 `time_index` 與 `series_id`。
- 新增 `TemporalRef` 與序列邊界 default。
- 新增每期狀態快照與時間依賴審計。
- 新增 `fixed_point_groups` 與 Jacobi 同步迭代。
- 保持未宣告循環為明示錯誤。
- 新增 `affine` 算子作為固定點最小測試算子。
- 新增收斂次數、最終 delta、容忍度與不收斂錯誤。
- 新增 append-only `corrections`。
- 同時保存 original/effective declared result。
- 新增補帳 SHA-256 雜湊鏈與 deterministic head hash。
- 新增 FDCS 節點、延遲邊、語境調製與分形欄位投影。
- FDCS interventions 明示為 `DECLARED_NOT_EXECUTED`。
- 新增 5 個 E5 範例與 6 項 E5 測試。
- 回歸測試擴充至 35 項。
- E5 完成 4,096 筆時間交易、128 組收縮固定點、32 組發散負對照與 256 組補帳鏈。
- 保留 MMLF v0.1–v0.4 相容性。

## 0.4.0 — 2026-07-21

- 正式完成 E4 橫列、直欄、區塊約束與跨軸稽核。
- 新增 MMLF v0.4 schema 與 `constraints`。
- 新增 row、column、block、region、cells 五種作用域。
- 新增 `sum_equals` 與 `all_equal` 約束。
- 新增跨軸失敗約束交點分析。
- 新增格子—約束 factor graph 與 flat table projection。
- 新增 `compare-representations` CLI。
- 新增線性總和約束的最小支撐修復求解。
- 新增修復 delta、corrected value、minimal size、ambiguity 與 exact 標記。
- 明示 `all_equal` 可稽核但不冒充已支援精確線性修復。
- 新增單格錯誤、跨軸抵消、多解歧義與乾淨帳本案例。
- E4 完成 128 個單格案例與 32 個抵消案例。
- 160／160 與獨立 flat table 參考實作一致。
- 回歸測試擴充至 29 項，E0–E4 全部重跑通過。
- 保留 MMLF v0.1／v0.2／v0.3 相容性。

## 0.3.0 — 2026-07-21

- 正式完成 E3 矩陣布局與 MMR 多方向執行。
- 新增 MMLF v0.3 schema。
- 將 `layout` 升級為可含空格的真正二維矩陣，並為每筆交易建立穩定座標。
- 修正 v0.2 將 `top_to_bottom`／`bottom_to_top` 視為扁平順序的問題。
- 新增六種物理遍歷：左右、上下、水平蛇形、垂直蛇形。
- 新增 `MatrixRef`：`previous`、`next`、`left`、`right`、`up`、`down`。
- 正式分離展示方向與執行方向。
- 新增 `--execution-traversal` 與 `compare-directions` CLI。
- 新增 semantic hash／execution hash 雙雜湊。
- 新增遍歷座標、訪問格數、曼哈頓距離、轉彎與區域跨越指標。
- 新增方向中立、方向敏感、固定空間引用、稀疏矩陣與缺失鄰居測試。
- 回歸測試擴充至 22 項。
- 完成 E3 64 個中立帳本、128 個方向帳本、64 個空間引用帳本與 1,024 次路由查詢。
- 保留 MMLF v0.1／v0.2 與程式化單列帳本相容性。

## 0.2.0 — 2026-07-21

- 正式完成 E1 符號—數值交換驗證。
- 新增 `evaluation_scenarios` 與 MMLF v0.2 schema。
- 新增不可變 ledger substitution / instantiation。
- 新增 `verify-exchange` CLI 與 Markdown / JSON 報告。
- 新增非交換算子負對照。
- 正式完成 E2 依賴污染與根因追蹤。
- 新增 `local_status` 與 `TAINTED` 狀態。
- 新增單根因、多根因匯流、blast radius 與穩定根因路徑。
- 新增欄位敏感資料通道：`result` 與 `audited_result` 分離信任。
- 新增巢狀 ValueRef 解析。
- 保留 MMLF v0.1 載入相容性。
- 回歸測試擴充至 14 項。
- 完成 E1 8,192 格與 E2 8,192 交易隨機驗證。

## 0.1.0 — 2026-07-21

- 完成 MMLF v0.1 schema。
- 完成決定性算術 runtime。
- 完成 Operator Registry 與算子專屬不變式。
- 完成局部／區域／全域稽核與反抵消政策。
- 完成 MMR 左右遍歷、拓撲遍歷與逆向依賴遍歷。
- 完成 semantic hash、manifest、JSONL 與 Markdown 報告。
- 加入 SymPy 與 DAG 相容預覽。
