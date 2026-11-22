<template>
	<div class="engine-choice">
		<span>证据来源</span
		><el-radio-group v-model="engine" aria-label="证据来源" @change="selectEngine"
			><el-radio-button value="design">业务设计场景证据</el-radio-button><el-radio-button value="api">原接口场景报告</el-radio-button
			><el-radio-button value="go">本地 Go 证据</el-radio-button></el-radio-group
		><span class="hint">只读查看历史；重新运行请到执行中心</span>
	</div>
	<InterfacePanel v-if="engine === 'design'" presentation="reports" /><WorkflowPanel v-else-if="engine === 'api'" page="reports" /><RunnerPanel
		v-else
		presentation="reports"
	/>
</template>
<script setup lang="ts" name="Web3Reports">
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import WorkflowPanel from '../web3-workbench/index.vue';
import RunnerPanel from '../qa-runner/index.vue';
import InterfacePanel from './InterfacePanel.vue';
const route = useRoute(),
	router = useRouter(),
	engine = ref(
		route.query.engine === 'go'
			? 'go'
			: route.query.engine === 'api'
			? 'api'
			: route.query.engine === 'design' || route.query.plan || route.query.design
			? 'design'
			: 'api'
	);
function selectEngine() {
	void router.replace({ query: { ...route.query, engine: engine.value } });
}
</script>
<style scoped>
.engine-choice {
	padding: 18px 24px 0;
	display: flex;
	gap: 16px;
	align-items: center;
	flex-wrap: wrap;
	font-size: 14px;
}
.hint {
	color: var(--el-text-color-secondary);
	line-height: 1.7;
}
</style>
