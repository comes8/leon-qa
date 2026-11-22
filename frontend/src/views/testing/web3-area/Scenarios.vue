<template><div><el-alert class="design-boundary" title="这里保留原接口场景资产。业务设计用例转为可执行接口场景将在第三批接入；本批生成的业务用例不会自动执行。" type="info" :closable="false"/><WorkflowPanel page="scenarios" /></div></template>
<script setup lang="ts" name="Web3Scenarios">
import WorkflowPanel from '../web3-workbench/index.vue';
</script>
<style scoped>.design-boundary{margin:16px;width:auto}</style>
