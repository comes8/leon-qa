<template>
	<div class="artifact-view">
		<p class="summary">{{ content.summary }}</p>
		<ul v-if="content.notes?.length" class="notes">
			<li v-for="(note, index) in content.notes" :key="index">{{ note }}</li>
		</ul>
		<template v-for="section in sections" :key="section.key">
			<section v-if="content[section.key]?.length" class="output-section">
				<h3>
					{{ section.label }} <span>{{ content[section.key].length }}</span>
				</h3>
				<el-table
					v-if="typeof content[section.key][0] === 'object'"
					:data="content[section.key]"
					border
					size="default"
					@selection-change="rows=>emit('select',rows.map((r:any)=>r.id))"
				>
					<el-table-column v-if="['testpoints', 'cases'].includes(section.key) && !readonly" type="selection" width="44" />
					<el-table-column type="expand"
						><template #default="{ row }"
							><dl class="detail">
								<template v-for="(value, key) in row" :key="key"
									><dt>{{ labels[key as string] || key }}</dt>
									<dd v-if="key === 'source_refs'" class="sources">
										<el-button v-for="(ref, index) in value" :key="index" link type="primary" @click="emit('source', ref.source_id)"
											>{{ ref.source_id }} · {{ ref.locator }}</el-button
										>
									</dd>
									<dd v-else-if="key === 'steps'">
										<div v-for="(step, index) in value" :key="index" class="case-step">
											<strong>步骤 {{ Number(index) + 1 }}</strong>
											<p>动作：{{ step.action }}</p>
											<p>预期：{{ step.expected }}</p>
											<p>观察：{{ step.observation }}</p>
										</div>
									</dd>
									<dd v-else>{{ display(value, key as string) }}</dd></template
								>
							</dl></template
						></el-table-column
					>
					<el-table-column label="编号" width="130"
						><template #default="{ row }">{{ row.id || row.case_id }}</template></el-table-column
					>
					<el-table-column label="业务内容" min-width="240"
						><template #default="{ row }"
							><strong>{{
								row.title ||
								row.name ||
								row.statement ||
								row.goal ||
								row.event ||
								row.risk ||
								row.problem ||
								row.question ||
								row.formula_or_property ||
								row.reason
							}}</strong>
							<p v-if="row.expected || row.effect || row.suggestion || row.impact" class="preview">
								{{ row.expected || row.effect || row.suggestion || row.impact }}
							</p></template
						></el-table-column
					>
					<el-table-column label="判据 / 优先级" min-width="130"
						><template #default="{ row }"
							><el-tag v-if="row.design_readiness" :type="row.design_readiness === 'ready' ? 'success' : 'warning'">{{
								readinessLabel(row.design_readiness)
							}}</el-tag
							><span v-if="row.evidence_kind">{{ display(row.evidence_kind, 'evidence_kind') }}</span
							><span v-if="row.severity">{{ display(row.severity, 'severity') }}</span>
							<p v-if="row.priority">{{ row.priority }}</p>
							<span v-if="row.execution_readiness">{{ preparationLabel(row.execution_readiness) }}</span></template
						></el-table-column
					>
					<el-table-column v-if="['testpoints', 'cases'].includes(section.key) && !readonly" label="修订" width="95"
						><template #default="{ row }"
							><el-button link type="primary" :aria-label="`修订 ${row.id}`" @click="emit('edit', { kind: section.key, row })"
								>编辑条目</el-button
							></template
						></el-table-column
					>
				</el-table>
				<ul v-else>
					<li v-for="(text, index) in content[section.key]" :key="index">{{ text }}</li>
				</ul>
			</section>
		</template>
		<p v-if="content.reviewed_scope"><strong>评审范围：</strong>{{ content.reviewed_scope }}</p>
		<p v-if="content.decision">
			<strong>设计判断：</strong>{{ ({ continue: '可继续', revise: '修订后继续', blocked: '关键判据受阻' } as any)[content.decision] }}
		</p>
	</div>
</template>
<script setup lang="ts">
import { readinessLabel, preparationLabel } from './design-state';
defineProps<{ content: any; readonly?: boolean }>();
const emit = defineEmits(['select', 'edit', 'source']);
const sections = [
	{ key: 'requirements', label: '需求行为' },
	{ key: 'rules', label: '规则及证据性质' },
	{ key: 'entities', label: '业务对象与状态' },
	{ key: 'transitions', label: '状态流转' },
	{ key: 'invariants', label: '数量、资金与不变量' },
	{ key: 'testpoints', label: '测试点' },
	{ key: 'cases', label: '详细业务用例' },
	{ key: 'issues', label: '评审意见' },
	{ key: 'findings', label: '专项发现' },
	{ key: 'risks', label: '风险' },
	{ key: 'acceptance', label: '关键验收依据' },
	{ key: 'impacts', label: '变更影响' },
	{ key: 'selection', label: '回归选择' },
	{ key: 'questions', label: '待确认事项' },
	{ key: 'missing_coverage', label: '覆盖缺口' },
	{ key: 'execution_gaps', label: '执行准备缺口' },
	{ key: 'remaining_risks', label: '剩余风险' },
];
const labels: Record<string, string> = {
	id: '编号',
	title: '标题',
	statement: '规则',
	scope: '适用范围',
	evidence_kind: '证据性质',
	source_refs: '资料来源',
	unresolved: '待确认部分',
	rule_ids: '关联规则',
	model_ids: '关联模型',
	testpoint_ids: '关联测试点',
	conditions: '前提 / 初态',
	trigger: '触发动作',
	expected: '预期判据',
	verification: '独立核对方法',
	priority: '建议优先级',
	design_readiness: '设计就绪度',
	execution_readiness: '执行准备',
	preconditions: '前置条件',
	data: '测试数据',
	steps: '步骤与逐步预期',
	expected_result: '整体判据',
	cleanup: '收尾',
	question: '问题',
	impact: '影响',
	affected_ids: '受影响编号',
	goal: '需求目标',
	risk: '风险',
	name: '对象',
	states: '状态',
	observation: '观察位置',
	entity_id: '业务对象',
	from_state: '原状态',
	event: '事件',
	guard: '守卫条件',
	to_state: '目标状态',
	effect: '业务效果',
	condition: '成立前提',
	formula_or_property: '公式 / 不变量',
	units_and_phase: '单位与事件截面',
	independent_evidence: '独立证据',
	target_ids: '评审目标',
	category: '问题类型',
	severity: '严重程度',
	problem: '问题',
	consequence: '后果',
	suggestion: '修订建议',
	action: '动作',
	case_id: '用例编号',
	disposition: '回归处置',
	reason: '理由',
	prerequisites: '准备条件',
};
function display(value: any, key: string): string {
	if (key === 'design_readiness') return readinessLabel(value);
	if (key === 'execution_readiness') return preparationLabel(value);
	if (key === 'evidence_kind')
		return ({ stated: '材料明示', observed: '实现观察', proposed: '建议补充', unknown: '待确认', conflict: '存在冲突' } as any)[value] || value;
	if (key === 'severity') return ({ blocking: '阻塞性', important: '重要', minor: '一般' } as any)[value] || value;
	if (Array.isArray(value)) return value.length ? value.map((v) => (typeof v === 'object' ? JSON.stringify(v, null, 2) : v)).join('\n') : '无';
	return typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value ?? '无');
}
</script>
<style scoped>
.summary {
	font-size: 16px;
	line-height: 1.9;
	white-space: pre-wrap;
}
.notes {
	font-size: 14px;
	line-height: 1.9;
	color: var(--el-text-color-secondary);
}
h3 {
	font-size: 17px;
	margin: 24px 0 14px;
}
h3 span {
	font-size: 14px;
	color: var(--el-text-color-secondary);
	margin-left: 8px;
}
.preview {
	line-height: 1.7;
	margin: 7px 0;
	white-space: pre-wrap;
}
.detail {
	display: grid;
	grid-template-columns: 150px minmax(0, 1fr);
	padding: 16px 22px;
	font-size: 14px;
	gap: 10px 18px;
	line-height: 1.85;
}
.detail dt {
	color: var(--el-text-color-secondary);
}
.detail dd {
	margin: 0;
	white-space: pre-wrap;
	overflow-wrap: anywhere;
}
.sources {
	display: flex;
	gap: 8px;
	flex-direction: column;
	align-items: flex-start;
}
.sources .el-button {
	white-space: normal;
	text-align: left;
	line-height: 1.7;
	height: auto;
	margin: 0;
}
.case-step {
	padding: 10px 0;
	border-bottom: 1px solid var(--el-border-color-lighter);
}
.case-step p {
	margin: 5px 0;
}
@media (max-width: 750px) {
	.detail {
		grid-template-columns: 1fr;
		gap: 5px;
		padding: 12px;
	}
	.detail dt {
		font-weight: 600;
		margin-top: 10px;
	}
}
</style>
