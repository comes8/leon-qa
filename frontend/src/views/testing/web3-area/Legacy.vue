<template><div class="legacy">正在打开 Web3 测试专区…</div></template>
<script setup lang="ts">
import { onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
const route = useRoute(),
	router = useRouter();
onMounted(() => {
	const targets: Record<string, string> = {
		'/api-automation/web3': '/web3/requirements',
		'/api-automation/data-prep': '/web3/data',
		'/api-automation/runner': '/web3/execution',
	};
	void router.replace({
		path: targets[route.path] || '/web3/requirements',
		query: { ...route.query, ...(route.path.endsWith('/runner') ? { engine: 'go' } : {}), ...(route.path.endsWith('/web3') ? {view:'legacy'} : {}) },
		hash: route.hash,
	});
});
</script>
<style scoped>
.legacy {
	padding: 24px;
	font-size: 16px;
}
</style>
