from __future__ import annotations

from .types import DirectionComparison, ExchangeReport, RunResult
from .values import serialize_value


def _show(value: object) -> str:
    serial = serialize_value(value)
    if isinstance(serial, dict) and "str" in serial:
        return str(serial["str"])
    if isinstance(serial, dict) and serial.get("type") == "fraction":
        return f"{serial['numerator']}/{serial['denominator']}"
    return str(serial)


def markdown_report(result: RunResult) -> str:
    lines = [
        f"# MMLC 執行報告：{result.ledger_id}",
        "",
        f"- Runtime：`{result.runtime_version}`",
        f"- Execution traversal：`{result.execution_traversal}`",
        f"- Semantic hash：`{result.semantic_hash}`",
        f"- Execution hash：`{result.execution_hash}`",
        f"- Global audit：**{result.global_audit['status']}**",
        f"- Local failures：{', '.join(result.local_failures) if result.local_failures else '無'}",
        f"- Tainted transactions：{', '.join(result.tainted_transactions) if result.tainted_transactions else '無'}",
        "",
        "## 交易結果",
        "",
        "| 交易 | 時間／序列 | 座標 | 算子 | 計算結果 | 稽核結果 | 本地狀態 | 整體狀態 | 根因 |",
        "|---|---|---|---|---:|---:|---|---|---|",
    ]
    for tx_id in result.execution_order:
        tx = result.transactions[tx_id]
        roots = ", ".join(tx.root_causes) if tx.root_causes else "—"
        coord = f"({tx.coordinate.row},{tx.coordinate.column})" if tx.coordinate is not None else "—"
        temporal = f"t={tx.time_index}; {tx.series_id or tx_id}"
        lines.append(
            f"| `{tx_id}` | `{temporal}` | `{coord}` | `{tx.operator_version}` | `{_show(tx.computed_result)}` | `{_show(tx.audited_result)}` | **{tx.local_status}** | **{tx.status}** | {roots} |"
        )
    lines.extend(["", "## 矩陣約束", ""])
    if result.constraint_audits:
        lines.extend([
            "| 約束 | 軸 | 類型 | 欄位 | 成員 | 觀測 | 目標 | 殘差 | 狀態 |",
            "|---|---|---|---|---|---:|---:|---:|---|",
        ])
        for constraint_id in sorted(result.constraint_audits):
            audit = result.constraint_audits[constraint_id]
            lines.append(
                f"| `{constraint_id}` | `{audit.axis}` | `{audit.kind}` | `{audit.field}` | "
                f"{', '.join(audit.members)} | `{_show(audit.observed)}` | `{_show(audit.target)}` | "
                f"`{_show(audit.residual)}` | **{audit.status}** |"
            )
        lines.extend(["", f"- 跨軸衝突數：`{len(result.cross_axis_conflicts)}`"] )
        for conflict in result.cross_axis_conflicts:
            lines.append(
                f"- `{conflict['constraints'][0]}` × `{conflict['constraints'][1]}` "
                f"交於：{', '.join(conflict['intersection'])}"
            )
        repair = result.repair_analysis
        lines.extend([
            "",
            "### 最小修復分析",
            "",
            f"- 狀態：**{repair.status}**",
            f"- 方法：`{repair.method}`",
            f"- 最小支撐：`{repair.minimal_size}`",
            f"- 歧義：`{repair.ambiguous}`",
            f"- 搜尋候選：`{repair.searched_supports}`",
        ])
        for index, proposal in enumerate(repair.proposals, 1):
            changes = ", ".join(
                f"{cell}: Δ={_show(proposal.deltas[cell])}, 新值={_show(proposal.corrected_values[cell])}"
                for cell in proposal.cells
            )
            lines.append(f"- 方案 {index}（`{proposal.field}`）：{changes}")
    else:
        lines.append("- 未設定矩陣約束。")

    lines.extend(["", "## 時間、固定點與補帳", ""])
    temporal = result.temporal_analysis
    lines.append(f"- 時間模式：`{temporal.get('enabled', False)}`；期間：`{temporal.get('periods', [])}`；延遲邊：`{len(temporal.get('delayed_edges', []))}`")
    fixed = result.fixed_point_analysis
    lines.append(f"- 固定點模式：`{fixed.get('enabled', False)}`；全部收斂：`{fixed.get('all_converged', True)}`")
    for group_id, group in fixed.get("groups", {}).items():
        lines.append(
            f"- 固定點 `{group_id}`：converged={group.get('converged')}，iterations={group.get('iterations')}，delta={group.get('final_delta')}"
        )
    correction = result.correction_analysis
    lines.append(
        f"- 不可變補帳：`{correction.get('enabled', False)}`；entries={correction.get('entry_count', 0)}；head=`{correction.get('head_hash', '')}`"
    )
    if correction.get("entries"):
        for entry in correction["entries"]:
            lines.append(
                f"- `{entry.correction_id}`：`{entry.target_tx_id}` {_show(entry.before)} → {_show(entry.after)}；hash=`{entry.entry_hash[:16]}`"
            )
    fdcs = result.fdcs_projection
    lines.append(
        f"- FDCS：**{fdcs.get('status', 'DISABLED')}**；nodes={len(fdcs.get('nodes', []))}；edges={len(fdcs.get('edges', []))}；contexts={len(fdcs.get('contexts', {}))}"
    )
    if fdcs.get("enabled"):
        lines.extend(["", "### FDCS 語境與虛擬干預", ""])
        if fdcs.get("contexts"):
            lines.extend([
                "| 語境 | 類型 | 全域狀態 | 干預數 | 切邊數 | 變動交易 | modulation |",
                "|---|---|---|---:|---:|---:|---:|",
            ])
            for context_id in fdcs.get("branch_order", sorted(fdcs["contexts"])):
                context = fdcs["contexts"][context_id]
                lines.append(
                    f"| `{context_id}` | `{context.get('status')}` | **{context.get('global_audit')}** | "
                    f"{len(context.get('interventions', []))} | {len(context.get('cut_edges', []))} | "
                    f"{len(context.get('changed_transactions', []))} | `{context.get('context_modulation')}` |"
                )
            for context_id in fdcs.get("branch_order", []):
                context = fdcs["contexts"].get(context_id, {})
                if context.get("changed_transactions"):
                    lines.append(
                        f"- `{context_id}` 變動：{', '.join(context['changed_transactions'])}；"
                        f"切邊：{len(context.get('cut_edges', []))}"
                    )
        else:
            lines.append("- 尚未執行反事實語境；目前只有因果投影。")
        if fdcs.get("edges"):
            lines.extend(["", "### FDCS 權重", "",
                "| 邊 | lag | 層級差 | forward | reverse |",
                "|---|---:|---:|---:|---:|",
            ])
            for edge in fdcs["edges"][:20]:
                lines.append(
                    f"| `{edge['source']} → {edge['target']}` | {edge.get('lag', 0)} | "
                    f"{edge.get('fractal_level_gap', 0)} | `{edge.get('forward_effective_weight')}` | "
                    f"`{edge.get('reverse_effective_weight')}` |"
                )
            if len(fdcs["edges"]) > 20:
                lines.append(f"- 其餘 `{len(fdcs['edges']) - 20}` 條邊省略。")
        lines.append("- Reverse weight 是反向稽核／查詢遍歷權重，不代表逆因果。")

    lines.extend([
        "",
        "## 總帳",
        "",
        f"- 有號殘差總和：`{result.global_audit['signed_residual_sum']}`",
        f"- 絕對殘差總和：`{result.global_audit['absolute_residual_sum']}`",
        f"- 偵測到抵消：`{result.global_audit['cancellation_detected']}`",
        f"- 局部失敗保留：`{result.global_audit['local_failures_preserved']}`",
        f"- 污染傳播：`{result.global_audit['taint_propagation_enabled']}`",
        "",
        "## 根因與影響範圍",
        "",
    ])
    roots = result.root_cause_analysis.get("root_causes", [])
    if roots:
        for root in roots:
            affected = result.root_cause_analysis["affected_by_root"].get(root, [])
            lines.append(f"- `{root}` → {' → '.join(affected)}")
    else:
        lines.append("- 無根因；帳本全部健康。")
    lines.extend(["", "## 遍歷", ""])
    for traversal in result.traversals:
        metrics = traversal.get("metrics", {})
        lines.append(
            f"- `{traversal['traversal']}`（{traversal.get('role', 'display')}）："
            f"{' → '.join(traversal['visited'])}；visits={metrics.get('visit_count', 0)}，"
            f"distance={metrics.get('manhattan_distance', 0)}，turns={metrics.get('turn_count', 0)}"
        )
    lines.append("")
    return "\n".join(lines)


def exchange_markdown_report(report: ExchangeReport) -> str:
    lines = [
        f"# E1 符號—數值交換報告：{report.ledger_id}",
        "",
        f"- Runtime：`{report.runtime_version}`",
        f"- Status：**{report.status}**",
        f"- Cells：`{report.passed_cells}/{report.total_cells}` 通過",
        "",
    ]
    for scenario in report.scenario_results:
        bindings = ", ".join(f"{k}={_show(v)}" for k, v in scenario.bindings.items())
        lines.extend([
            f"## {scenario.scenario_id}",
            "",
            f"- Bindings：`{bindings}`",
            f"- Status：**{scenario.status}**",
            "",
            "| 交易 | 符號結果代入 | 直接數值執行 | 等價 |",
            "|---|---:|---:|---|",
        ])
        for tx_id, cell in scenario.cells.items():
            lines.append(
                f"| `{tx_id}` | `{_show(cell.substituted_symbolic_value)}` | `{_show(cell.direct_numeric_value)}` | **{'PASS' if cell.equivalent else 'FAIL'}** |"
            )
        lines.append("")
    return "\n".join(lines)


def direction_markdown_report(comparison: DirectionComparison) -> str:
    lines = [
        f"# E3 方向比較報告：{comparison.ledger_id}",
        "",
        f"- Direction sensitive：**{comparison.direction_sensitive}**",
        f"- Semantic equivalence classes：`{comparison.semantic_equivalence_classes}`",
        f"- Result equivalence classes：`{comparison.result_equivalence_classes}`",
        "",
        "| 方向 | 全域狀態 | 語義雜湊 | 執行雜湊 | 執行順序 |",
        "|---|---|---|---|---|",
    ]
    for name in comparison.directions:
        run = comparison.runs[name]
        lines.append(
            f"| `{name}` | **{run.global_audit['status']}** | `{run.semantic_hash[:16]}` | `{run.execution_hash[:16]}` | {' → '.join(run.execution_order)} |"
        )
    lines.extend(["", "## 各方向結果", ""])
    for name in comparison.directions:
        run = comparison.runs[name]
        values = ", ".join(f"{tx_id}={_show(run.transactions[tx_id].computed_result)}" for tx_id in sorted(run.transactions))
        lines.append(f"- `{name}`：{values}")
    lines.append("")
    return "\n".join(lines)


def representation_markdown_report(ledger_id: str, comparison: dict[str, object]) -> str:
    lines = [
        f"# E4 表示對照報告：{ledger_id}",
        "",
        f"- Flat-table reference equivalent：**{comparison['equivalent']}**",
        f"- Flat table rows：`{comparison['flat_table_rows']}`",
        f"- Factor graph variable nodes：`{comparison['factor_graph_variable_nodes']}`",
        f"- Factor graph constraint nodes：`{comparison['factor_graph_constraint_nodes']}`",
        f"- Factor graph edges：`{comparison['factor_graph_edges']}`",
        "",
        "## 解讀",
        "",
        str(comparison['interpretation']),
        "",
    ]
    mismatches = comparison.get('mismatches', [])
    if mismatches:
        lines.extend(["## 不一致", "", "```json", str(mismatches), "```", ""])
    else:
        lines.extend(["## 不一致", "", "- 無。MMLC 與獨立 flat-table 參考檢查一致。", ""])
    return "\n".join(lines)


def fdcs_markdown_report(result: RunResult) -> str:
    fdcs = result.fdcs_projection
    lines = [
        f"# E8 FDCS 機率、政策與觀測規劃報告：{result.ledger_id}",
        "",
        f"- Runtime：`{result.runtime_version}`",
        f"- Status：**{fdcs.get('status', 'DISABLED')}**",
        f"- Execution mode：`{fdcs.get('execution_mode', 'projection_only')}`",
        f"- Base context：`{fdcs.get('base_context', fdcs.get('context', '—'))}`",
        f"- Contexts：`{len(fdcs.get('contexts', {}))}`",
        f"- Nodes／Edges：`{len(fdcs.get('nodes', []))}`／`{len(fdcs.get('edges', []))}`",
        f"- Intervention conflicts：`{fdcs.get('intervention_conflict_count', 0)}`",
        "",
        "## 語境分支",
        "",
    ]
    contexts = fdcs.get("contexts", {})
    if not contexts:
        lines.append("- 未執行語境分支。")
    else:
        lines.extend([
            "| 語境 | 狀態 | 全域稽核 | modulation | 干預 | 切邊 | 變動交易 | Diff head |",
            "|---|---|---|---:|---:|---:|---:|---|",
        ])
        for context_id in fdcs.get("branch_order", sorted(contexts)):
            item = contexts[context_id]
            diff = item.get("differential_ledger") or {}
            head = str(diff.get("head_hash", "—"))
            lines.append(
                f"| `{context_id}` | `{item.get('status')}` | **{item.get('global_audit')}** | "
                f"`{item.get('context_modulation')}` | {len(item.get('interventions', []))} | "
                f"{len(item.get('cut_edges', []))} | {len(item.get('changed_transactions', []))} | `{head[:16]}` |"
            )
        for context_id in fdcs.get("branch_order", []):
            item = contexts[context_id]
            lines.extend(["", f"### {context_id}", ""])
            lines.append(f"- Semantic hash：`{item.get('semantic_hash')}`")
            lines.append(f"- 變動交易：{', '.join(item.get('changed_transactions', [])) or '無'}")
            audit = item.get("intervention_audit") or {}
            lines.append(
                f"- 干預稽核：**{audit.get('status', '—')}**；conflicts={len(audit.get('conflicts', []))}；redundancies={len(audit.get('redundancies', []))}"
            )
            for conflict in audit.get("conflicts", []):
                lines.append(
                    f"- 衝突：target=`{conflict.get('target_tx_id')}`；ids={conflict.get('intervention_ids')}"
                )
            if item.get("interventions"):
                for intervention in item["interventions"]:
                    kind = intervention.get("kind")
                    target = intervention.get("target_tx_id")
                    if kind == "do_set":
                        desc = f"do(`{target}`) = `{_show(intervention.get('value'))}`"
                    elif kind == "soft_affine":
                        desc = (
                            f"`{target}`: F' = `{_show(intervention.get('scale', 1))}`·F + "
                            f"`{_show(intervention.get('shift', 0))}`"
                        )
                    else:
                        desc = f"{kind}(`{target}`)"
                    lines.append(f"- 干預 `{intervention.get('id')}`：{desc}")
            for cut in item.get("cut_edges", []):
                lines.append(
                    f"- 切邊：`{cut.get('source')} → {cut.get('target')}`；channels={cut.get('channels')}"
                )
            diff = item.get("differential_ledger")
            if diff:
                lines.append(
                    f"- 分支差分帳：records={diff.get('record_count')}；changed={diff.get('changed_count')}；head=`{diff.get('head_hash')}`"
                )
                for record in diff.get("records", []):
                    if record.get("changed"):
                        lines.append(
                            f"  - `{record['tx_id']}`：`{_show(record['baseline_value'])}` → `{_show(record['branch_value'])}`；"
                            f"role=`{record['change_role']}`；hash=`{record['entry_hash'][:16]}`"
                        )

    ident = fdcs.get("identifiability_audit") or {}
    lines.extend(["", "## 帳本可識別性稽核", ""])
    if not ident:
        lines.append("- 未執行。")
    else:
        lines.append(f"- 觀測交易：{', '.join(ident.get('observed_transactions', [])) or '無'}")
        lines.append(f"- 所有效應可見：`{ident.get('all_effects_visible')}`")
        lines.append(f"- 所有語境成對可區分：`{ident.get('all_contexts_pairwise_distinguishable')}`")
        lines.append(f"- 等價類：`{ident.get('equivalence_classes')}`")
        lines.extend([
            "",
            "| 語境 | 判定 | 與基線可區分 | 唯一簽章 | 不可區分對象 |",
            "|---|---|---|---|---|",
        ])
        for context_id, item in ident.get("context_results", {}).items():
            lines.append(
                f"| `{context_id}` | `{item.get('status')}` | `{item.get('ledger_distinguishable_from_baseline')}` | "
                f"`{item.get('pairwise_unique')}` | {', '.join(item.get('indistinguishable_with', [])) or '—'} |"
            )
        lines.extend(["", f"> {ident.get('scope_note', '')}", ""])

    probability = fdcs.get("probability_analysis") or {}
    lines.extend(["", "## 機率分支與不確定性傳播", ""])
    if not probability or not probability.get("enabled"):
        lines.append("- 未啟用機率分支。")
    else:
        lines.append(f"- Status：**{probability.get('status')}**")
        lines.extend([
            "",
            "| 群組 | 狀態 | 機率總和 | 分支數 | 分析雜湊 |",
            "|---|---|---:|---:|---|",
        ])
        for group_id, group in probability.get("groups", {}).items():
            lines.append(
                f"| `{group_id}` | `{group.get('status')}` | `{group.get('probability_sum')}` | "
                f"{len(group.get('contexts', []))} | `{str(group.get('analysis_hash', ''))[:16]}` |"
            )
            for tx_id, item in group.get("transaction_uncertainty", {}).items():
                lines.append(
                    f"- `{group_id}/{tx_id}`：support={item.get('support_size')}；E=`{item.get('expected_value')}`；"
                    f"Var=`{item.get('variance')}`；H=`{item.get('entropy_bits')}` bits"
                )
        lines.extend(["", f"> {probability.get('scope_note', '')}", ""])

    continuous = fdcs.get("continuous_approximation_analysis") or {}
    lines.extend(["", "## 連續分布與相關不確定性近似", ""])
    if not continuous or not continuous.get("enabled"):
        lines.append("- 未啟用連續近似。")
    else:
        lines.append(f"- Status：**{continuous.get('status')}**")
        lines.append(f"- Sampling：`{continuous.get('sampling_method')}`")
        lines.append(f"- Generated contexts：`{continuous.get('generated_context_count')}`")
        for ensemble_id, item in continuous.get("ensembles", {}).items():
            empirical = item.get("empirical", {})
            lines.append(
                f"- `{ensemble_id}`：samples={item.get('sample_count')}；means=`{empirical.get('means')}`；"
                f"std=`{empirical.get('standard_deviations')}`；corr=`{empirical.get('correlation_matrix')}`"
            )
        lines.extend(["", f"> {continuous.get('scope_note', '')}", ""])

    policy = fdcs.get("policy_analysis") or {}
    lines.extend(["", "## 干預成本與政策選擇", ""])
    if not policy or not policy.get("enabled"):
        lines.append("- 未啟用政策選擇。")
    else:
        lines.append(f"- Status：**{policy.get('status')}**")
        lines.append(f"- Selected：`{policy.get('selected_policies', [])}`")
        lines.extend([
            "",
            "| 政策 | 狀態 | 期望效用 | 標準差 | 期望成本 | 分數 |",
            "|---|---|---:|---:|---:|---:|",
        ])
        for policy_id, item in policy.get("policies", {}).items():
            lines.append(
                f"| `{policy_id}` | `{item.get('status')}` | `{item.get('expected_utility')}` | "
                f"`{item.get('utility_standard_deviation')}` | `{item.get('expected_cost')}` | `{item.get('score')}` |"
            )
        lines.extend(["", f"> {policy.get('scope_note', '')}", ""])

    information = fdcs.get("information_value_analysis") or {}
    lines.extend(["", "## 資訊價值與序貫決策", ""])
    if not information or not information.get("enabled"):
        lines.append("- 未啟用資訊價值分析。")
    else:
        lines.append(f"- Status：**{information.get('status')}**")
        lines.append(f"- 先驗最佳值：`{information.get('prior_best_value')}`；政策：`{information.get('prior_selected_policies')}`")
        lines.append(f"- Horizon：`{information.get('horizon')}`")
        lines.append(f"- 序貫期望值：`{information.get('sequential_expected_value')}`")
        lines.append(f"- 序貫淨資訊價值：`{information.get('sequential_net_information_value')}`")
        lines.append(f"- 根決策：`{(information.get('decision_tree') or {}).get('action')}`")
        for tx_id, item in information.get("candidate_information_values", {}).items():
            lines.append(
                f"- 觀測 `{tx_id}`：gross EVSI=`{item.get('gross_information_value')}`；"
                f"cost=`{item.get('observation_cost')}`；net=`{item.get('net_information_value')}`"
            )
        lines.extend(["", f"> {information.get('scope_note', '')}", ""])

    plan = fdcs.get("observation_plan") or {}
    lines.extend(["", "## 最小追加觀測集合", ""])
    if not plan or not plan.get("enabled"):
        lines.append("- 未啟用觀測規劃。")
    else:
        lines.append(f"- Status：**{plan.get('status')}**")
        lines.append(f"- 既有觀測：`{plan.get('observed_transactions', [])}`")
        lines.append(f"- 最小追加數：`{plan.get('minimum_size')}`")
        lines.append(f"- 最小方案：`{plan.get('solutions', [])}`")
        lines.append(f"- 最低成本：`{plan.get('minimum_cost')}`")
        lines.append(f"- 最低成本方案：`{plan.get('minimum_cost_solutions', [])}`")
        lines.append(f"- 觀測成本：`{plan.get('observation_costs', {})}`")
        lines.append(f"- 尚未區分配對：`{plan.get('ambiguous_pairs', [])}`")
        if plan.get("impossible_pairs"):
            lines.append(f"- 無法區分配對：`{plan.get('impossible_pairs')}`")
        lines.extend(["", f"> {plan.get('scope_note', '')}", ""])

    lines.extend(["", "## 方向與分形權重", "",
        "| 邊 | lag | 層級差 | 時間因子 | 分形因子 | forward | reverse |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for edge in fdcs.get("edges", []):
        lines.append(
            f"| `{edge['source']} → {edge['target']}` | {edge.get('lag')} | {edge.get('fractal_level_gap')} | "
            f"`{edge.get('temporal_factor')}` | `{edge.get('fractal_factor')}` | "
            f"`{edge.get('forward_effective_weight')}` | `{edge.get('reverse_effective_weight')}` |"
        )
    lines.extend([
        "",
        "## 邊界",
        "",
        "- `do_set` 切斷傳入邊；`soft_affine` 保留傳入邊並修改結構方程輸出。",
        "- 固定點群內干預只支援已宣告的 Jacobi 群，並重新求解；不等於任意循環系統皆可解。",
        "- 反事實分支忽略觀測帳本的 declared result 與來源等式，但保留原始內容供追溯。",
        "- 可識別性與追加觀測規劃只代表指定模型分支的有限格可區分性，不是統計因果識別。",
        "- Reverse weight 是反向稽核／查詢遍歷權重，不是逆因果。",
        "- 分形層級由文件宣告，Runtime 不會自行推斷層級。",
        "- 機率與成本皆由文件宣告；Runtime 不會把它們當成外部世界的客觀頻率或價值。",
        "- 連續分布以有限決定性樣本近似；經驗矩與相關矩陣不等於解析證明。",
        "- 資訊價值與序貫決策只在對齊的已宣告情境內成立，且目前採風險中立期望淨效用。",
        "",
    ])
    return "\n".join(lines)
