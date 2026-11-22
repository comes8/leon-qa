<template>
	<div class="design-source">
		<span>工作内容</span
		><el-radio-group v-model="view" aria-label="设计或原接口资产" @change="changeView"
			><el-radio-button value="business">业务设计</el-radio-button><el-radio-button value="legacy">原接口资产</el-radio-button></el-radio-group
		><span class="hint">业务设计按 Skill / Prompt 分阶段生成；接口编排与执行继续使用原引擎</span>
	</div>
	<DesignPanel v-if="view === 'business'" :section="section" /><WorkflowPanel v-else :page="section" />
</template>
<script setup lang="ts">
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import DesignPanel from './DesignPanel.vue';
import WorkflowPanel from '../web3-workbench/index.vue';
defineProps<{ section: 'requirements' | 'testpoints' | 'cases' }>();
const route = useRoute(),
	router = useRouter(),
	view = ref(route.query.view === 'legacy' ? 'legacy' : 'business');
function changeView() {
	void router.replace({ query: { ...route.query, view: view.value } });
}
</script>
<style scoped>
.design-source {
	padding: 18px 24px 0;
	display: flex;
	gap: 14px;
	align-items: center;
	flex-wrap: wrap;
	font-size: 14px;
}
.hint {
	color: var(--el-text-color-secondary);
	line-height: 1.7;
}
</style>
