<template>
	<section class="evidence panel">
		<h3>当次业务证据</h3>
		<el-empty v-if="!runs.length" description="尚无接口执行记录；生成或发布不表示执行通过。" :image-size="50" /><el-collapse v-else
			><el-collapse-item v-for="j in runs" :key="j.id" :name="j.id" :title="`执行任务 #${j.id} · ${interfaceVerdict(j.receipt, j.status)}`"
				><p v-if="j.error_message">{{ j.error_message }}</p>
				<template v-if="j.receipt"
					><p>开始：{{ j.receipt.started_at }}；完成：{{ j.receipt.finished_at || '尚未完成' }}；结果ID：{{ j.receipt.result_id }}</p>
					<p>步骤：通过{{ j.receipt.passed_steps }} / 失败{{ j.receipt.failed_steps }} / 受阻{{ j.receipt.blocked_steps }}</p>
					<p v-if="j.receipt.unstarted_cases?.length">尚未开始的用例：{{ j.receipt.unstarted_cases.map((c: any) => c.case_id).join('、') }}</p>
					<template v-for="c in [...(j.receipt.cases || []), ...(j.receipt.in_progress_case ? [j.receipt.in_progress_case] : [])]" :key="c.case_id"
						><h4>{{ c.case_id }} · {{ c.name }} · {{ c.status }}</h4>
						<el-table :data="c.steps" border
							><el-table-column type="expand"
								><template #default="{ row }">
									<pre>{{
										JSON.stringify(
											{ 请求: row.request, 响应: row.response, 断言: row.validators, 抽取: row.extracts, 错误: row.error || row.message },
											null,
											2
										)
									}}</pre>
								</template></el-table-column
							><el-table-column prop="name" label="步骤" min-width="220" /><el-table-column prop="status" label="当次状态" width="110" /></el-table
					></template>
					<pre v-if="!j.receipt.cases?.length && !j.receipt.in_progress_case">{{ JSON.stringify(j.receipt, null, 2) }}</pre>
				</template></el-collapse-item
			></el-collapse
		>
		<p>历史通过仅代表当次固定版本与环境；中断、停止或缺证据时不显示为业务通过。</p>
	</section>
</template>
<script setup lang="ts">
import { computed } from 'vue';
import { interfaceVerdict } from './interface-api';
const props = defineProps<{ jobs: any[] }>();
const runs = computed(() => props.jobs.filter((j) => j.kind === 'execute'));
</script>
<style scoped>
.panel {
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 10px;
	padding: 20px;
	margin: 20px 0;
}
p {
	line-height: 1.8;
}
pre {
	font: 13px/1.8 ui-monospace, monospace;
	white-space: pre-wrap;
	overflow-wrap: anywhere;
	background: var(--el-fill-color-light);
	padding: 15px;
	max-height: 60vh;
	overflow: auto;
}
</style>
