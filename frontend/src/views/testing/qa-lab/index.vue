<template>
  <div class="lab-page">
    <header class="heading"><div><h1>{{presentation==='debug'?'接口调试':presentation==='data'?'测试数据':'本地数据准备'}}</h1><p>{{presentation==='debug'?'使用已有环境和数据集调试资金接口，检查响应与业务断言':'启动独立手工环境，准备可隔离、可重建的资金业务状态'}}</p></div><div class="actions"><el-button :loading="state.loading" @click="refreshPage">刷新</el-button><Diagnostics :project="projectId" /><el-button @click="goOther">{{presentation==='debug'?'管理测试数据':'打开接口调试'}}</el-button><el-button @click="router.push({ path: '/web3/execution', query: { project: projectId,engine:'go' } })">执行中心</el-button></div></header>
    <el-alert class="notice" type="info" :closable="false" show-icon title="仅本机合成环境 · 每个数据集生成 alice、bob 两个测试用户。金额为每位用户的初值，币种固定 TESTUSD；不会修改平台用户或真实账本。" />
    <el-alert v-if="state.error" class="notice" type="error" :closable="false" :title="state.error" />
    <el-alert v-if="!workerReady" class="notice" type="warning" :closable="false" :title="`执行器${state.worker === 'blocked' ? '异常阻塞' : '离线或尚未就绪'}，请先检查本地执行器。`" />
    <el-alert v-if="state.pending" class="notice" type="warning" :closable="false" title="上次请求待确认。请先刷新或按原请求重试，避免重复准备数据。"><el-button @click="controller.submit()" :loading="state.submitting">按原请求重试</el-button></el-alert>
    <div v-if="state.notice" class="operation-notice" role="status">{{ state.notice }}</div>
    <section class="panel environment-panel">
      <div class="environment-controls"><el-select v-model="projectId" aria-label="数据准备所属项目" placeholder="选择项目" :disabled="state.submitting || initializing" @change="changeProject"><el-option v-for="p in projects" :key="p.id" :value="p.id" :label="p.name" /></el-select>
        <el-select v-model="state.selectedEnvironment" aria-label="手工环境" placeholder="尚未启动手工环境" @change="controller.selections()"><el-option v-for="env in state.environments" :key="env.id" :value="env.id" :label="`${env.id.slice(0, 8)} · ${labStatus(env.status)} · ${formatTime(env.creation_date)}`" /></el-select>
        <el-button v-if="presentation!=='debug'" type="primary" :disabled="!canStart" :loading="state.submitting" @click="controller.submit({ action: 'start' })">启动手工环境</el-button>
        <el-button v-if="presentation!=='debug' && environment && ['running', 'error'].includes(environment.status)" type="danger" plain :disabled="locked || busy" @click="stopEnvironment">停止所选环境</el-button>
      </div>
      <template v-if="environment"><div class="environment-meta"><el-tag :type="environment.status === 'running' ? 'success' : 'info'">{{ labStatus(environment.status) }}</el-tag><code class="environment-id">{{ environment.id }}</code><span>资源 {{ environment.status === 'running' ? '使用中' : cleanupLabel(environment.cleanup_status) }}</span></div><p class="muted">手工环境与自动回归分别管理。本机最多两套手工环境，同一用户同一项目限一套。停止后业务数据不可继续使用，历史快照保留。</p><el-alert v-if="environment.error_message" class="notice" type="warning" :closable="false" :title="environment.error_message" /></template>
      <p v-else class="muted">先启动手工环境，再准备两组不同余额的数据。数据操作通过已登记的 Go 工具执行。</p>
      <p v-if="busy" class="busy" role="status">{{ actionLabel(busy.action) }} · {{ labStatus(busy.status) }}，请等待原操作结果</p>
    </section>
    <div class="data-layout" :class="{'debug-layout':presentation==='debug'}">
      <aside v-if="presentation!=='debug'" class="panel seed-panel"><h2>创建数据集</h2><el-form label-position="top" @submit.prevent="createDataset">
        <el-form-item label="数据集名称"><el-input v-model="form.name" aria-label="数据集名称" placeholder="例如：正常划转初值" :maxlength="80" :disabled="!canMutate" /></el-form-item>
        <el-form-item label="每人资金账户初值（TESTUSD）"><el-input v-model="form.funding" aria-label="资金账户初值" placeholder="1000" :disabled="!canMutate" /></el-form-item>
        <el-form-item label="每人现货账户初值（TESTUSD）"><el-input v-model="form.spot" aria-label="现货账户初值" placeholder="0" :disabled="!canMutate" /></el-form-item>
        <p class="muted">使用十进制文本，最多 8 位小数，范围 0–10000000；不接受科学计数法或自动四舍五入。</p>
        <el-button class="create-button" type="primary" native-type="submit" :disabled="!canMutate || !seedValid" :loading="state.submitting">创建合成数据集</el-button>
      </el-form></aside>
      <main class="panel dataset-panel" aria-label="数据集管理">
        <div class="section-heading"><h2>所选环境的数据集</h2><el-button v-if="dataset && presentation!=='debug'" link type="primary" @click="goOther">打开资金接口调试</el-button><span class="muted">{{ datasets.length }} 组</span></div>
        <template v-if="presentation==='debug'"><el-select v-model="state.selectedDataset" aria-label="调试数据集" placeholder="先在测试数据页准备数据"><el-option v-for="d in datasets" :key="d.id" :value="d.id" :label="`${d.name} · ${labStatus(d.status)} · 第${d.generation}代`" /></el-select><p class="muted">{{dataset?`当前数据集 ${dataset.id} · ${dataset.native_id||'历史数据'}。下面展示原始调试记录；不会自动重放请求。`:'暂无可调试数据，请先到测试数据页准备环境与数据集。'}}</p></template>
        <template v-else>
        <el-table :data="datasets" border highlight-current-row :row-class-name="datasetRowClass" @row-click="row => state.selectedDataset = row.id" :max-height="300">
          <el-table-column label="数据集" min-width="160"><template #default="{ row }"><el-button link type="primary" :aria-label="`查看数据集 ${row.name}`" @click.stop="state.selectedDataset = row.id">{{ row.name }}</el-button><code class="small-id">{{ row.id }}</code></template></el-table-column>
          <el-table-column label="原始初值" min-width="110"><template #default="{ row }"><span>{{ row.funding }} / {{ row.spot }}</span><span class="muted">资金 / 现货</span></template></el-table-column>
          <el-table-column label="状态" width="105"><template #default="{ row }"><el-tag :type="row.status === 'ready' ? 'success' : 'info'">{{ labStatus(row.status) }}</el-tag></template></el-table-column>
          <el-table-column prop="generation" label="代次" width="65" />
        </el-table>
        <section v-if="dataset" class="dataset-detail" aria-label="数据集详情">
          <div class="section-heading"><div><h3>{{ dataset.name }}</h3><code class="dataset-id">{{ dataset.id }}</code></div><div class="actions"><el-button :disabled="!canMutate || dataset.status !== 'ready'" @click="dataAction('inspect')">刷新快照</el-button><el-button :disabled="!canMutate || !['ready', 'deleted', 'error'].includes(dataset.status)" @click="rebuildDataset">按初值重建</el-button><el-button type="danger" plain :disabled="!canMutate || dataset.status !== 'ready'" @click="deleteDataset">清理所选数据集</el-button></div></div>
          <p class="muted native-id">当前 Go 数据集 ID：{{ dataset.native_id || '无可用数据集；仅保留历史快照' }} · 第 {{ dataset.generation }} 代 · 版本 {{ dataset.revision }}</p>
          <el-alert v-if="dataset.status !== 'ready'" class="notice" type="warning" :closable="false" :title="`${labStatus(dataset.status)}：下面为最后保存的快照，不代表当前仍可执行。`" />
          <el-empty v-if="!dataset.snapshot" description="创建完成后显示实际快照" :image-size="55" />
          <template v-else><h3 class="snapshot-title">最后保存的账户快照</h3><el-table :data="dataset.snapshot.accounts" border size="small"><el-table-column prop="user_id" label="合成用户" width="90" /><el-table-column label="账户" width="90"><template #default="{ row }">{{ row.kind === 'funding' ? '资金' : '现货' }}</template></el-table-column><el-table-column label="余额（TESTUSD）" min-width="150"><template #default="{ row }"><b>{{ minorAmount(row.balance_minor) }}</b><code class="small-id">最小单位 {{ row.balance_minor }}</code></template></el-table-column></el-table><p class="muted">业务记录 {{ dataset.snapshot.transfers.length }} 条 · 流水 {{ dataset.snapshot.ledger.length }} 条。快照来自本环境 Go SDK；此处只展示状态，不代替业务通过判定。</p></template>
          <details v-if="dataset.history.length"><summary>查看历代快照（{{ dataset.history.length }} 份）</summary><div v-for="(item, i) in dataset.history" :key="i" class="history-snapshot"><b>第 {{ item.generation }} 代 · {{ actionLabel(item.reason) }}</b><code class="small-id">{{ item.native_id }}</code><p class="muted">{{ formatTime(item.at) }} · 操作 {{ item.operation_id }}</p><pre>{{ JSON.stringify(item.snapshot, null, 2) }}</pre></div></details>
        </section>
        </template>
      </main>
    </div>
    <section v-if="dataset && presentation!=='data'" class="panel debug-section"><DebugPanel :dataset="dataset" :environment-id="state.selectedEnvironment" :ready="canMutate && dataset.status === 'ready'" :operations="state.operations" @submit="controller.submit" /></section>
    <section v-if="presentation!=='debug'" class="panel operations"><div class="section-heading"><h2>操作记录</h2><span class="muted">当前项目中自己的最近 100 次操作</span></div><el-table :data="state.operations" size="small" :max-height="300"><el-table-column label="时间" width="155"><template #default="{ row }">{{ formatTime(row.creation_date) }}</template></el-table-column><el-table-column label="操作" min-width="120"><template #default="{ row }">{{ actionLabel(row.action) }}</template></el-table-column><el-table-column label="结果" width="100"><template #default="{ row }"><el-tag :type="row.status === 'completed' ? 'success' : row.status === 'error' ? 'danger' : 'info'">{{ labStatus(row.status) }}</el-tag></template></el-table-column><el-table-column label="记录 / 异常" min-width="230"><template #default="{ row }"><code class="small-id">{{ row.id }}</code><span>{{ row.error_message || '' }}</span></template></el-table-column></el-table></section>
  </div>
</template>

<script setup lang="ts" name="LocalQaLab">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useProjectApi } from '/@/api/v1/projects/project';
import { useUserStore } from '/@/stores/user';
import { labApi } from '/@/api/v1/testing/qaLab';
import { cleanupLabel, errorMessage, formatTime } from '../qa-runner/model';
import { createLabController, initialLabState } from './controller';
import { actionLabel, labStatus, minorAmount, validSeed } from './model';
import DebugPanel from './DebugPanel.vue';
import Diagnostics from '../qa-runner/Diagnostics.vue';
import type { LabAction } from './model';
import { readContext, saveContext } from '../web3-area/context';

withDefaults(defineProps<{presentation?:'full'|'data'|'debug'}>(),{presentation:'full'});

const route = useRoute(), router = useRouter(), user = useUserStore();
const state = reactive(initialLabState());
const storageKey = (project: string) => `leon.qa.lab.pending.v1.${user.userInfos.id}.${project}`;
const controller = createLabController(state, labApi, {
  read(project) { const raw = sessionStorage.getItem(storageKey(project)); if (!raw) return null; const body = JSON.parse(raw); return String(body.project_id) === project && typeof body.request_key === 'string' ? body : null; },
  write(project, body) { if (body) sessionStorage.setItem(storageKey(project), JSON.stringify(body)); else sessionStorage.removeItem(storageKey(project)); },
});
const projects = ref<{ id: string; name: string }[]>([]), projectId = ref(''), initializing = ref(true);
const form = reactive({ name: '', funding: '1000', spot: '0' });
const environment = computed(() => state.environments.find(e => e.id === state.selectedEnvironment));
const datasets = computed(() => state.datasets.filter(d => d.environment_id === state.selectedEnvironment));
const dataset = computed(() => datasets.value.find(d => d.id === state.selectedDataset));
const workerReady = computed(() => ['idle', 'running'].includes(state.worker));
const locked = computed(() => state.submitting || !!state.pending || !workerReady.value);
const busy = computed(() => state.operations.find(o => o.environment_id === state.selectedEnvironment && ['queued', 'running'].includes(o.status)));
const canStart = computed(() => !!state.project && !locked.value && !state.environments.some(e => ['queued', 'starting', 'running', 'stopping'].includes(e.status) || e.cleanup_status === 'failed'));
const canMutate = computed(() => environment.value?.status === 'running' && !locked.value && !busy.value);
const seedValid = computed(() => !!form.name.trim() && validSeed(form.funding) && validSeed(form.spot));
let timer: ReturnType<typeof setTimeout> | undefined, mounted = true, loaded = false;
async function changeProject() { await controller.project(projectId.value); }
function syncLabRoute(){if(initializing.value||!mounted)return;const ctx={...readContext(user.userInfos.id,{project:projectId.value}),project:projectId.value,env:state.selectedEnvironment||undefined,dataset:state.selectedDataset||undefined};saveContext(user.userInfos.id,ctx);void router.replace({query:ctx})}
function goOther(){syncLabRoute();void router.push({path:route.path==='/web3/debug'?'/web3/data':'/web3/debug',query:{...readContext(user.userInfos.id,{project:projectId.value})}})}
watch(()=>[projectId.value,state.selectedEnvironment,state.selectedDataset],syncLabRoute);
async function createDataset() { if (!seedValid.value || !environment.value) { ElMessage.warning('请输入有效的名称和十进制初值'); return; } await controller.submit({ action: 'create', environment_id: environment.value.id, ...form }); }
async function dataAction(action: 'inspect' | 'rebuild' | 'delete') { if (!dataset.value || !environment.value) return; await controller.submit({ action, environment_id: environment.value.id, dataset_id: dataset.value.id, expected_revision: dataset.value.revision }); }
async function confirm(text: string, title: string) { try { await ElMessageBox.confirm(text, title, { confirmButtonText: '确认操作', cancelButtonText: '返回', type: 'warning' }); return true; } catch { return false; } }
async function rebuildDataset() { if (dataset.value && await confirm(`仅重建“${dataset.value.name}”：按原始 ${dataset.value.funding}/${dataset.value.spot} 初值创建新 ID，归档旧快照并清理旧业务数据。`, '按原始初值重建')) await dataAction('rebuild'); }
async function deleteDataset() { if (dataset.value && await confirm(`仅清理“${dataset.value.name}”，不影响其他数据集；快照与操作记录继续保留。`, '清理所选数据集')) await dataAction('delete'); }
async function stopEnvironment() { const env = environment.value; if (env && await confirm('停止所选手工环境将销毁其独立数据库，该环境的数据集变为不可用。历史快照保留，不停止自动回归任务。', '停止所选手工环境')) await controller.submit({ action: 'stop', environment_id: env.id }); }
function datasetRowClass({ row }: { row: { id: string } }) { return row.id === state.selectedDataset ? 'selected-dataset' : ''; }
async function poll() { await controller.refresh(); if (mounted) timer = setTimeout(poll, state.error ? 10000 : 1500); }
async function refreshPage() { if (!loaded) await initialize(); else await controller.refresh(); }
async function initialize() {
  initializing.value = true;
  try { const response: any = await useProjectApi().getList({ page: 1, page_size: 100 });if(!mounted)return;projects.value = (response.data.items || response.data.rows || []).map((p: { id: unknown; name: string }) => ({ id: String(p.id), name: p.name })); loaded = true;const ctx=readContext(user.userInfos.id,route.query);projectId.value = projects.value.find(p => p.id === ctx.project)?.id || projects.value[0]?.id || ''; await changeProject();if(state.environments.some(e=>e.id===ctx.env))state.selectedEnvironment=ctx.env!;if(state.datasets.some(d=>d.id===ctx.dataset&&d.environment_id===state.selectedEnvironment))state.selectedDataset=ctx.dataset!; }
  catch (error) { state.error = errorMessage(error); }
  finally { initializing.value = false;syncLabRoute();if (loaded && mounted && !timer) timer = setTimeout(poll, 1500); }
}
onMounted(initialize);
onUnmounted(() => { mounted = false; if (timer) clearTimeout(timer); controller.dispose(); });
</script>

<style scoped lang="scss">
.lab-page { padding: 24px; color: var(--el-text-color-primary); min-width: 0; } .debug-section { margin-top:18px; } h1 { margin: 0 0 8px; font-size: 24px; } h2 { margin: 0; font-size: 17px; } h3 { margin: 0; font-size: 15px; }
.data-layout.debug-layout{grid-template-columns:1fr}.debug-layout .el-select{width:min(100%,620px);margin-top:16px}
.heading, .actions, .section-heading, .environment-controls, .environment-meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; } .heading, .section-heading { justify-content: space-between; } .heading { margin-bottom: 20px; } .heading p, .muted { color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.75; } .heading p { margin: 0; font-size: 13px; }
.panel { background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 10px; padding: 20px; min-width: 0; } .notice { margin-bottom: 16px; } .environment-panel { margin: 18px 0; } .environment-controls .el-select { width: 250px; } .environment-meta { margin-top: 18px; font-size: 12px; } .environment-id { overflow-wrap: anywhere; } .busy { color: var(--el-color-primary); font-size: 13px; }
.data-layout { display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 18px; align-items: start; } .seed-panel h2 { margin-bottom: 20px; } .create-button { width: 100%; margin-top: 10px; } .section-heading { margin-bottom: 18px; } .section-heading .actions { gap: 8px; } .actions .el-button + .el-button { margin-left: 0; }
.small-id, .dataset-id { display: block; font-size: 11px; line-height: 1.7; color: var(--el-text-color-secondary); overflow-wrap: anywhere; } .dataset-detail { border-top: 1px solid var(--el-border-color-lighter); margin-top: 22px; padding-top: 22px; } .native-id { overflow-wrap: anywhere; } .snapshot-title { margin: 18px 0; } .operations { margin-top: 18px; } .operation-notice { color: var(--el-color-success-dark-2); font-size: 13px; margin-bottom: 16px; }
:deep(.selected-dataset) { --el-table-tr-bg-color: var(--el-color-primary-light-9); } details { margin-top: 20px; font-size: 13px; } summary { cursor: pointer; color: var(--el-color-primary); } .history-snapshot { padding: 16px 0; border-bottom: 1px solid var(--el-border-color-lighter); }
pre { background: var(--el-fill-color-light); padding: 14px; overflow: auto; max-height: 320px; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; line-height: 1.7; }
@media (max-width: 1000px) { .lab-page { padding: 16px; } .data-layout { grid-template-columns: 240px minmax(0, 1fr); } .panel { padding: 16px; } }
@media (max-width: 800px) { .data-layout { grid-template-columns: 1fr; } .environment-controls .el-select { width: 100%; } .heading .actions { width: 100%; } }
@media (max-width: 550px) { .lab-page { padding: 10px; } .panel { padding: 12px; } h1 { font-size: 22px; } }
</style>
