<template>
	<div class="source-choice">
		<span>场景来源</span
		><el-radio-group v-model="view" aria-label="接口场景来源" @change="change"
			><el-radio-button value="business">业务设计适配</el-radio-button><el-radio-button value="legacy">原接口资产</el-radio-button></el-radio-group
		>
	</div>
	<InterfacePanel v-if="view === 'business'" presentation="mapping" /><WorkflowPanel v-else page="scenarios" />
</template>
<script setup lang="ts" name="Web3Scenarios">
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import InterfacePanel from './InterfacePanel.vue';
import WorkflowPanel from '../web3-workbench/index.vue';
const route = useRoute(),
	router = useRouter(),
	view = ref(route.query.view === 'legacy' ? 'legacy' : 'business');
function change() {
	void router.replace({ query: { ...route.query, view: view.value } });
}
</script>
<style scoped>
.source-choice {
	display: flex;
	gap: 16px;
	padding: 18px 24px 0;
	align-items: center;
	flex-wrap: wrap;
	font-size: 14px;
}
</style>
