<template>
	<div class="engine-choice">
		<span>执行来源</span
		><el-radio-group v-model="engine" aria-label="执行来源" @change="selectEngine"
			><el-radio-button value="design">业务设计场景</el-radio-button><el-radio-button value="api">原接口场景</el-radio-button
			><el-radio-button value="go">本地 Go 套件</el-radio-button></el-radio-group
		><span class="hint">分别使用原执行引擎，不将接口草稿自动转换为 Go 套件</span>
	</div>
	<InterfacePanel v-if="engine === 'design'" presentation="execution" /><WorkflowPanel v-else-if="engine === 'api'" page="execution" /><RunnerPanel
		v-else
		presentation="execution"
	/>
</template>
<script setup lang="ts" name="Web3Execution">
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
