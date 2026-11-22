<template>
	<el-footer class="layout-footer pb15">
		<div class="layout-footer-warp">
			<div>{{ brand.name }} · {{ brand.subtitle }}</div>
		</div>
	</el-footer>
</template>

<script setup lang="ts" name="layoutFooter">
import { brand } from '/@/config/brand';
</script>

<style scoped lang="scss">
.layout-footer {
	width: 100%;
	display: flex;
	&-warp {
		margin: auto;
		color: var(--el-text-color-secondary);
		text-align: center;
		animation: error-num 0.3s ease;
	}
}
</style>
