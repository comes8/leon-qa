<template>
 <el-button :disabled="!project" @click="open">运行诊断</el-button>
 <el-dialog v-model="visible" title="本机运行诊断" width="min(760px, 94vw)" top="5vh" append-to-body @closed="controller.clear">
  <div class="diagnostics-body">
  <p class="hint">只读检查平台依赖、执行器及本人项目的手工环境。服务健康不代表业务测试通过。</p>
  <el-alert v-if="error" :title="error" type="error" :closable="false"/>
  <p v-if="loading" role="status">正在检查，最长约数秒…</p>
  <template v-if="report"><p><el-tag :type="report.overall==='ready'?'success':'warning'">{{healthLabel(report.overall)}}</el-tag> <span class="hint">检查时间 {{formatTime(report.checked_at)}}</span></p>
   <el-table :data="report.checks" border size="small"><el-table-column prop="label" label="组件" width="155"/><el-table-column label="状态" width="95"><template #default="{row}">{{healthLabel(row.status)}}</template></el-table-column><el-table-column prop="detail" label="检查结果" min-width="200"/></el-table>
   <h4>本项目自己的手工环境</h4><el-empty v-if="!report.environments?.length" description="当前没有活动手工环境" :image-size="40"/><el-table v-else :data="report.environments" size="small" border><el-table-column prop="id" label="环境编号" min-width="220"/><el-table-column label="健康探测" width="100"><template #default="{row}">{{healthLabel(row.probe||row.status)}}</template></el-table-column><el-table-column prop="consecutive_failures" label="连续失败" width="100"/></el-table>
  </template>
  <h4>本机管理命令</h4><p class="hint">在 Leon QA 项目根目录的终端执行。停止/整体重启会中断运行并关闭手工环境，保留历史快照；单独重启后端不停止独立执行器。</p><pre>./leonqa start
./leonqa status
./leonqa doctor
./leonqa restart backend
./leonqa stop</pre>
  </div>
  <template #footer><el-button @click="visible=false">关闭</el-button><el-button type="primary" :loading="loading" @click="controller.refresh(project)">重新检查</el-button></template>
 </el-dialog>
</template>
<script setup lang="ts">
import {ref,watch,onUnmounted} from 'vue';
import request from '/@/utils/request';
import {formatTime} from './model';
import {createDiagnostics,healthLabel} from './diagnostics';
import type {HealthReport} from './diagnostics';
const props=defineProps<{project:string}>();const visible=ref(false),loading=ref(false),error=ref(''),report=ref<HealthReport|null>(null);
const controller=createDiagnostics(async project=>(await request<unknown,{data:HealthReport}>({url:'/v1/Ntesterc_qa_runner/diagnostics',params:{project_id:project},timeout:10000})).data,(r,e,l)=>{report.value=r;error.value=e;loading.value=l;});
function open(){visible.value=true;controller.refresh(props.project);}
watch(()=>props.project,()=>{controller.clear();if(visible.value&&props.project)controller.refresh(props.project);});onUnmounted(controller.clear);
</script>
<style scoped>.diagnostics-body{max-height:70vh;overflow:auto}.diagnostics-body :deep(.el-empty){padding:12px 0}.hint{font-size:12px;line-height:1.8;color:var(--el-text-color-secondary)}pre{background:var(--el-fill-color-light);padding:14px;line-height:1.8;font-size:12px;overflow:auto}h4{margin:22px 0 10px}</style>
