<template>
  <div class="runner-page">
    <header class="page-heading">
      <div><h1>{{presentation==='reports'?'本地 Go 报告与证据':presentation==='execution'?'本地 Go 执行中心':'本地套件运行'}}</h1><p>{{presentation==='reports'?'查看当次运行的断言、日志和原始证据；执行操作请到执行中心':'提交任务、跟踪执行、核对业务断言与原始证据'}}</p></div>
      <div class="heading-actions"><el-tag :type="workerTone" effect="plain">执行器 · {{ workerLabel(workerStatus) }}</el-tag>
        <el-button :loading="state.loading || initializing" @click="refreshPage">刷新</el-button>
        <Diagnostics :project="projectId" />
        <el-button @click="router.push({ path: '/web3/data', query: { project: projectId } })">测试数据</el-button>
        <el-button @click="router.push({path:presentation==='reports'?'/web3/execution':'/web3/reports',query:{project:projectId,job:state.selectedId,engine:'go'}})">{{presentation==='reports'?'前往执行中心':'报告与证据'}}</el-button></div>
    </header>
    <el-alert class="scope-note" type="info" :closable="false" show-icon title="本机合成环境 · 当前套件验证同用户资金账户与现货账户内部划转，不连接真实交易所。" />
    <el-alert v-if="state.pollError || state.error" class="message" type="error" :closable="false" show-icon :title="state.error || state.pollError" description="当前信息可能尚未更新。恢复连接后点击刷新；不要因请求超时反复创建任务。" />
    <el-alert v-if="workerStatus === 'blocked'" class="message" type="error" :closable="false" show-icon :title="state.catalog?.worker.last_error || '执行器异常，已暂停领取新任务'" />
    <el-alert v-if="workerStatus === 'offline'" class="message" type="warning" :closable="false" show-icon title="执行器离线。任务可提交排队，启动本地执行器后才会运行。" />
    <div class="runner-layout">
      <aside class="runner-sidebar">
        <section v-if="presentation!=='reports'" class="panel submit-panel">
          <h2>提交运行</h2>
          <el-form label-position="top" @submit.prevent="submit">
            <el-form-item label="所属项目"><el-select v-model="projectId" aria-label="所属项目" placeholder="选择有权限的项目" :disabled="state.submitting || initializing" @change="changeProject">
              <el-option v-for="project in projects" :key="project.id" :value="project.id" :label="project.name" />
            </el-select></el-form-item>
            <el-empty v-if="!initializing && !projects.length" description="暂无可用项目，请先在项目管理中创建或加入项目" :image-size="55" />
            <el-form-item label="已登记套件"><el-select v-model="form.suite_id" aria-label="已登记套件" :disabled="!!state.pending || state.submitting" placeholder="等待执行器登记套件">
              <el-option v-for="suite in suites" :key="suite.suite_id" :label="suite.name" :value="suite.suite_id" />
            </el-select></el-form-item>
            <p v-if="selectedSuite" class="muted suite-note">v{{ selectedSuite.suite_version }} · 常规回归 {{ selectedSuite.required_tests.length }} 个必跑业务用例</p>
            <el-form-item label="运行类型"><el-radio-group v-model="form.run_kind" aria-label="运行类型" :disabled="!!state.pending || state.submitting">
              <el-radio label="regression">常规回归</el-radio><el-radio label="selftest">故障自检</el-radio>
            </el-radio-group></el-form-item>
            <p v-if="form.run_kind === 'selftest'" class="selftest-note">故意少记一最小单位，验证检测能力。自检成功不等于业务回归通过。</p>
            <el-form-item label="执行超时（秒）"><el-input-number v-model="form.timeout_seconds" aria-label="执行超时（秒）" :min="1" :max="900" :precision="0" controls-position="right" :disabled="!!state.pending || state.submitting" /></el-form-item>
            <p class="muted">超时从开始执行后计算，不含排队；取消后需等待资源清理。</p>
            <el-alert v-if="state.pending && !state.submitting" class="message" type="warning" :closable="false" title="上次提交尚待确认，已保留原请求标识。刷新或重试不会新建第二条任务。" />
            <el-alert v-if="state.submitError" class="message" type="error" :closable="false" :title="state.submitError" />
            <el-button class="submit-button" type="primary" native-type="submit" :loading="state.submitting" :disabled="!canSubmit">{{ state.pending ? '确认或重试原请求' : form.run_kind === 'selftest' ? '运行故障自检' : workerStatus === 'offline' ? '加入回归队列' : '运行常规回归' }}</el-button>
            <p v-if="state.pending" class="request-key muted">请求标识 {{ state.pending.request_key }}</p>
            <p v-if="state.notice" class="notice" role="status">{{ state.notice }}</p>
          </el-form>
          <details v-if="['offline', 'not_configured', 'blocked'].includes(workerStatus)" class="startup-help"><summary>本地执行器启动说明</summary><pre>进入 Leon QA 项目目录的 backend 文件夹
.venv/bin/python scripts/qa_runner.py status
.venv/bin/python scripts/qa_runner.py start</pre><p class="muted">异常时先检查 worker.log 和本任务 cleanup.json，核对清理状态后再启动。</p></details>
        </section>
        <section v-else class="panel"><h2>所属项目</h2><el-select v-model="projectId" aria-label="报告所属项目" @change="changeProject"><el-option v-for="p in projects" :key="p.id" :value="p.id" :label="p.name" /></el-select></section>
        <section class="panel history-panel" aria-label="运行历史">
          <div class="section-heading"><h2>运行历史</h2><span class="muted">{{ state.jobs.length }} 条</span></div>
          <el-input v-model="search" aria-label="筛选运行编号" placeholder="筛选运行编号" clearable />
          <p class="muted history-hint">当前项目中自己提交的最近 100 条</p>
          <el-empty v-if="!visibleJobs.length" :description="search ? '没有匹配记录' : state.loading ? '正在读取历史' : '暂无运行记录'" :image-size="50" />
          <div class="history-list">
            <button v-for="job in visibleJobs" :key="job.id" class="history-item" :class="{ selected: state.selectedId === job.id }" :aria-label="`查看任务 ${job.run_id}`" :aria-pressed="state.selectedId === job.id" @click="selectJob(job.id)">
              <span class="history-top"><b>{{ job.run_kind === 'selftest' ? '故障自检' : '常规回归' }}</b><span>{{ lifecycleLabel(job.status) }}</span></span>
              <code>{{ job.run_id.slice(-16) }}</code><span class="history-bottom"><span :class="'verdict-' + verdictTone(job)">{{ verdictLabel(job) }}</span><time>{{ formatTime(job.creation_date) }}</time></span>
            </button>
          </div>
        </section>
      </aside>
      <main class="panel run-detail" aria-label="运行详情">
        <el-empty v-if="!state.job" :description="state.selectedId ? '正在读取所选任务' : '选择历史记录，或提交第一条套件任务'" :image-size="90"><p class="muted">每次运行都有独立编号，保留测试结论、状态变化和原始证据。</p></el-empty>
        <template v-else>
          <div class="detail-heading"><div><div class="detail-title"><h2>{{ state.job.run_kind === 'selftest' ? '故障自检' : '常规回归' }}</h2><el-tag :type="terminal(state.job.status) ? 'info' : 'warning'">{{ lifecycleLabel(state.job.status) }}</el-tag><el-tag :type="verdictTone(state.job)">{{ verdictLabel(state.job) }}</el-tag></div><code class="run-id">{{ state.job.run_id }}</code></div>
            <div v-if="presentation!=='reports'" class="detail-actions"><el-button v-if="canCancel(state.job)" type="danger" plain :loading="state.cancelling" @click="cancel">取消任务</el-button><el-button v-if="state.job.status === 'cancelling'" disabled>正在取消并清理</el-button><el-button :disabled="state.submitting || !!state.pending" @click="reuseConfiguration">复用运行配置</el-button></div>
          </div>
          <div class="run-meta"><span>提交 {{ formatTime(state.job.creation_date) }}</span><span>开始 {{ formatTime(state.job.started_at) }}</span><span>结束 {{ formatTime(state.job.finished_at) }}</span><span>资源 {{ cleanupLabel(state.job.cleanup_status) }}</span></div>
          <el-alert v-if="state.job.error_message" class="message" :type="state.job.result_status === 'ENV_ERROR' || state.job.cleanup_status === 'failed' ? 'error' : 'warning'" :closable="false" :title="state.job.error_message" />
          <el-alert v-if="state.job.run_kind === 'selftest'" class="message" type="warning" :closable="false" show-icon :title="state.job.result_status === 'PASS' ? '自检成功：已检出预期缺陷。原始门禁为 FAIL，这是自检的预期结果。' : '故障自检用于验证断言检测能力，不计作正常业务回归。'" />
          <div v-if="state.job.result" class="metrics"><div><b>{{ state.job.result.cases.length }}</b><span>有证据的业务用例</span></div><div><b>{{ assertionCounts.passed }}</b><span>通过断言</span></div><div><b :class="{ failed: assertionCounts.failed > 0 }">{{ assertionCounts.failed }}</b><span>失败断言</span></div><div><b>{{ state.job.process_exit_code ?? '—' }}</b><span>进程退出码</span></div></div>
          <el-tabs v-model="detailTab" class="detail-tabs">
            <el-tab-pane label="业务用例与断言" name="cases">
              <el-empty v-if="!state.job.result" :description="terminal(state.job.status) ? '本次没有完整可导入报告，请查看日志与状态事件' : '执行完成并导入报告后显示业务断言'" :image-size="60" />
              <template v-else>
                <el-alert v-if="state.job.result.gate_result.missing_mandatory.length" type="warning" :closable="false" :title="`缺少 ${state.job.result.gate_result.missing_mandatory.length} 个必跑用例，本次不能判为通过`" />
                <p class="muted">结论由后端核验报告后提供。点击业务用例查看该次运行的断言、数据与接口记录。</p>
                <el-table :data="state.job.result.cases" border size="small" :max-height="280" highlight-current-row :row-class-name="caseRowClass" @row-click="row => controller.selectCase(row.case_id)">
                  <el-table-column label="业务用例" min-width="180"><template #default="{ row }"><el-button link type="primary" :aria-label="`查看用例 ${row.case_id}`" @click.stop="controller.selectCase(row.case_id)">{{ caseLabel(row.case_id) }}</el-button><code class="case-id">{{ row.case_id }}</code></template></el-table-column>
                  <el-table-column label="结果" width="80"><template #default="{ row }"><el-tag :type="row.status === 'PASS' ? 'success' : 'danger'" size="small">{{ row.status }}</el-tag></template></el-table-column>
                  <el-table-column prop="assertions_passed" label="通过断言" width="90" /><el-table-column prop="assertions_failed" label="失败断言" width="90" />
                </el-table>
                <section v-if="state.selectedCase" class="case-section" aria-label="用例证据">
                  <div class="section-heading"><div><h3>{{ caseLabel(state.selectedCase) }}</h3><code class="case-id">{{ state.selectedCase }}</code></div><el-button size="small" :disabled="!selectedCaseEntry" @click="selectedCaseEntry && download(selectedCaseEntry.evidence_file)">下载用例证据</el-button></div>
                  <p v-if="state.caseLoading" class="muted">正在读取该次运行的证据…</p>
                  <el-alert v-if="state.caseError" type="error" :closable="false" :title="state.caseError"><el-button link @click="controller.selectCase(state.selectedCase)">重新读取证据</el-button></el-alert>
                  <template v-if="state.caseBundle">
                    <p class="muted dataset">数据集 {{ state.caseBundle.dataset_id }} · 金额按原始最小单位展示，保留字符串精度</p>
                    <el-checkbox v-model="failedOnly">仅看失败断言</el-checkbox>
                    <el-table :data="visibleAssertions" border size="small" :max-height="420" empty-text="当前筛选下没有失败断言">
                      <el-table-column label="断言 / 业务对象" min-width="195"><template #default="{ row }"><strong>{{ row.rule_id }}</strong><span class="assertion-subject">{{ row.subject }}</span><span class="muted">{{ row.label }}</span></template></el-table-column>
                      <el-table-column label="预期" min-width="110"><template #default="{ row }"><pre class="assertion-value">{{ displayValue(row.expected) }}</pre></template></el-table-column>
                      <el-table-column label="实际" min-width="110"><template #default="{ row }"><pre class="assertion-value">{{ displayValue(row.actual) }}</pre></template></el-table-column>
                      <el-table-column label="判断 / 单位" min-width="105"><template #default="{ row }"><span>{{ row.operator }}</span><code class="case-id">{{ row.unit || '—' }}</code></template></el-table-column>
                      <el-table-column label="结果" width="76"><template #default="{ row }"><el-tag :type="row.status === 'PASS' ? 'success' : 'danger'" size="small">{{ row.status }}</el-tag></template></el-table-column>
                    </el-table>
                    <details><summary>查看测试数据前后快照</summary><pre>{{ JSON.stringify({ before: state.caseBundle.before, after: state.caseBundle.after }, null, 2) }}</pre></details>
                    <details><summary>查看接口请求与响应（{{ state.caseBundle.http_events.length }} 条）</summary><pre>{{ JSON.stringify(state.caseBundle.http_events, null, 2) }}</pre></details>
                    <details><summary>查看服务日志</summary><pre>{{ state.caseBundle.service_logs.join('\n') }}</pre></details>
                  </template>
                </section>
              </template>
            </el-tab-pane>
            <el-tab-pane label="执行日志" name="logs">
              <div class="log-controls"><el-select :model-value="state.stream" aria-label="日志流" @change="value => controller.setStream(value)"><el-option label="测试执行日志（stderr）" value="stderr" /><el-option label="结构化输出（stdout）" value="stdout" /><el-option label="进程日志（supervisor）" value="supervisor" /></el-select><el-button @click="controller.progress()">读取后续日志</el-button></div>
              <p class="muted">已读 {{ state.logOffset }} / {{ state.logSize }} 字节 · {{ state.logComplete ? '本日志已读完' : '运行中自动更新，可手动继续读取' }}</p>
              <el-alert v-if="state.logTrimmed" type="info" :closable="false" title="界面仅保留最近 300,000 个字符；完整执行记录可在证据文件中下载 runner.log。" />
              <pre class="execution-log" aria-label="执行日志内容">{{ state.logText || (terminal(state.job.status) ? '该日志暂未生成；可切换日志流或查看状态事件。' : '等待进程输出…') }}</pre>
            </el-tab-pane>
            <el-tab-pane :label="`状态事件 (${state.events.length})`" name="events"><el-empty v-if="!state.events.length" description="等待任务事件" :image-size="50" /><ol class="event-list"><li v-for="event in state.events" :key="event.seq"><div><b>#{{ event.seq }} {{ event.code }}</b><time>{{ formatTime(event.at) }}</time></div><p>{{ event.message }}</p></li></ol><el-button v-if="state.events.length" @click="controller.progress()">读取后续事件</el-button></el-tab-pane>
            <el-tab-pane label="证据文件与来源" name="artifacts">
              <el-empty v-if="!state.job.result" description="完整报告未导入。取消或中断的任务请先查看日志和状态事件。" :image-size="60" />
              <template v-else><dl class="source-info"><dt>运行环境</dt><dd>{{ state.job.result.profile }}</dd><dt>套件版本</dt><dd>{{ state.job.result.suite_id }} / {{ state.job.result.suite_version }}</dd><dt>源码摘要</dt><dd><code>{{ state.job.result.source.sha256 || '未取得' }}</code></dd><dt>代码版本</dt><dd>{{ state.job.result.source.commit }}{{ state.job.result.source.dirty ? ' · 含本地改动' : '' }}</dd><dt>原始门禁</dt><dd>{{ state.job.result.gate_result.status }}</dd></dl>
                <el-input v-model="artifactSearch" aria-label="筛选证据文件" placeholder="筛选文件，例如 summary.json、junit.xml、runner.log" clearable />
                <el-table :data="visibleArtifacts" size="small" :max-height="480"><el-table-column label="本次运行的文件" min-width="210"><template #default="{ row }"><code class="artifact-name">{{ row }}</code></template></el-table-column><el-table-column label="操作" width="100"><template #default="{ row }"><el-button link type="primary" :loading="downloading === row" :aria-label="`下载 ${row}`" @click="download(row)">下载</el-button></template></el-table-column></el-table>
              </template>
            </el-tab-pane>
          </el-tabs>
        </template>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts" name="LocalQaRunner">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useProjectApi } from '/@/api/v1/projects/project';
import { runnerApi } from '/@/api/v1/testing/qaRunner';
import { useUserStore } from '/@/stores/user';
import { createRunnerController, initialState } from './controller';
import { canCancel, caseLabel, cleanupLabel, displayValue, errorMessage, formatTime, lifecycleLabel, terminal, verdictLabel, verdictTone, workerLabel } from './model';
import type { CreateJob, RunKind } from './types';
import Diagnostics from './Diagnostics.vue';
import {readContext,saveContext} from '../web3-area/context';
withDefaults(defineProps<{presentation?:'full'|'execution'|'reports'}>(),{presentation:'full'});

const route = useRoute(), router = useRouter(), user = useUserStore();
const state = reactive(initialState());
const storageKey = (project: string) => `leon.qa.runner.pending.v1.${user.userInfos.id}.${project}`;
const controller = createRunnerController(state, runnerApi, {
  read(project) { const raw = sessionStorage.getItem(storageKey(project)); if (!raw) return null; const value: CreateJob = JSON.parse(raw); return String(value.project_id) === project && typeof value.request_key === 'string' ? value : null; },
  write(project, body) { if (body) sessionStorage.setItem(storageKey(project), JSON.stringify(body)); else sessionStorage.removeItem(storageKey(project)); },
});
const projects = ref<{ id: string; name: string }[]>([]), projectId = ref(''), initializing = ref(true);
const form = reactive({ suite_id: 'funds-transfer-v1', run_kind: 'regression' as RunKind, timeout_seconds: 300 });
const search = ref(''), artifactSearch = ref(''), failedOnly = ref(false), detailTab = ref('cases'), downloading = ref('');
const suites = computed(() => state.catalog?.catalog?.suites || []);
const selectedSuite = computed(() => suites.value.find(s => s.suite_id === form.suite_id));
const workerStatus = computed(() => state.catalog?.worker.status || 'starting');
const workerTone = computed(() => ['idle', 'running'].includes(workerStatus.value) ? 'success' : ['blocked', 'not_configured'].includes(workerStatus.value) ? 'danger' : 'warning');
const canSubmit = computed(() => !!projectId.value && (!!state.pending || !!selectedSuite.value) && !['blocked', 'not_configured'].includes(workerStatus.value) && !initializing.value);
const visibleJobs = computed(() => state.jobs.filter(j => j.run_id.includes(search.value.trim())));
const assertionCounts = computed(() => (state.job?.result?.cases || []).reduce((total, c) => ({ passed: total.passed + c.assertions_passed, failed: total.failed + c.assertions_failed }), { passed: 0, failed: 0 }));
const selectedCaseEntry = computed(() => state.job?.result?.cases.find(c => c.case_id === state.selectedCase));
const visibleAssertions = computed(() => state.caseBundle?.assertions.filter(a => !failedOnly.value || a.status === 'FAIL') || []);
const visibleArtifacts = computed(() => state.job?.result?.artifacts.filter(a => a.toLowerCase().includes(artifactSearch.value.toLowerCase())) || []);
let timer: ReturnType<typeof setTimeout> | undefined, mounted = true, projectsLoaded = false;

function syncRoute() { if (mounted && !initializing.value) {const ctx={...readContext(user.userInfos.id,{project:state.projectId}),project:state.projectId||undefined,job:state.selectedId||undefined};saveContext(user.userInfos.id,ctx);void router.replace({ query: { ...ctx,engine:'go' } });} }
watch(() => [state.projectId, state.selectedId], syncRoute);
watch(() => state.selectedId, id => { detailTab.value = state.jobs.find(j => j.id === id)?.result ? 'cases' : 'logs'; artifactSearch.value = ''; });
watch(() => state.selectedCase, () => { failedOnly.value = state.job?.run_kind === 'selftest'; });
watch(() => state.pending, pending => { if (pending) Object.assign(form, { suite_id: pending.suite_id, run_kind: pending.run_kind, timeout_seconds: pending.timeout_seconds }); });
async function changeProject() { search.value = ''; await controller.setProject(projectId.value); }
async function selectJob(id: string) { await controller.selectJob(id); }
async function submit() { await controller.submit({ ...form }); }
async function cancel() {
  try { await ElMessageBox.confirm('将结束所选任务的执行进程并清理本次资源，历史记录和已生成证据会保留。', '取消当前任务', { confirmButtonText: '确认取消任务', cancelButtonText: '继续执行', type: 'warning' }); }
  catch { return; }
  await controller.cancel();
}
function reuseConfiguration() { if (!state.job) return; Object.assign(form, { suite_id: state.job.suite_id, run_kind: state.job.run_kind, timeout_seconds: state.job.timeout_seconds }); state.notice = '配置已填入左侧。点击运行会创建新任务，保留原记录。'; }
const caseRowClass = ({ row }: { row: { case_id: string } }) => row.case_id === state.selectedCase ? 'selected-case' : '';
async function download(relative: string) {
  const job = state.job; if (!job) return; downloading.value = relative;
  try { const blob = await runnerApi.artifact(job.id, relative); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `${job.run_id}-${relative.replaceAll('/', '_')}`; document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  catch (error) { ElMessage.error(errorMessage(error)); }
  finally { downloading.value = ''; }
}
async function poll() { await controller.refresh(); if (mounted) timer = setTimeout(poll, state.pollError ? 10000 : 2200); }
async function refreshPage() { if (!projectsLoaded) await initialize(); else await controller.refresh(); }
async function initialize() {
  initializing.value = true;
  try {
    const response: any = await useProjectApi().getList({ page: 1, page_size: 100 });
    if (!mounted) return;
    projects.value = (response.data.items || response.data.rows || []).map((p: { id: unknown; name: string }) => ({ id: String(p.id), name: p.name }));
    projectsLoaded = true;
    const ctx=readContext(user.userInfos.id,route.query);
    const requested = ctx.project || '';
    const requestedJob = ctx.job || '';
    projectId.value = projects.value.find(p => p.id === requested)?.id || projects.value[0]?.id || '';
    await controller.setProject(projectId.value, requestedJob);
  } catch (error) { state.error = errorMessage(error); }
  finally { initializing.value = false; if (projectsLoaded) { syncRoute(); if (mounted && !timer) timer = setTimeout(poll, 2200); } }
}
onMounted(initialize);
onUnmounted(() => { mounted = false; if (timer) clearTimeout(timer); controller.dispose(); });
</script>

<style scoped lang="scss">
.runner-page { padding: 24px; color: var(--el-text-color-primary); min-width: 0; }
.page-heading, .section-heading, .detail-heading, .heading-actions, .detail-actions, .detail-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.page-heading { margin-bottom: 20px; flex-wrap: wrap; } h1 { font-size: 24px; margin: 0 0 7px; } h2 { font-size: 17px; margin: 0; } h3 { font-size: 16px; margin: 0; }
.page-heading p, .muted { color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.65; } .page-heading p { margin: 0; font-size: 13px; }
.heading-actions, .detail-actions, .detail-title { justify-content: flex-start; flex-wrap: wrap; } .heading-actions .el-button + .el-button, .detail-actions .el-button + .el-button { margin-left: 0; }
.scope-note { margin-bottom: 18px; } .message { margin: 12px 0; } .runner-layout { display: grid; grid-template-columns: 310px minmax(0, 1fr); gap: 20px; align-items: start; }
.panel { background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 10px; } .submit-panel, .history-panel { padding: 20px; } .submit-panel h2 { margin-bottom: 20px; }
.runner-sidebar { min-width: 0; } .runner-sidebar .panel + .panel { margin-top: 18px; } .el-select, .el-input-number { width: 100%; } .submit-panel :deep(.el-form-item) { margin-bottom: 17px; }
.submit-button { width: 100%; margin-top: 12px; } .suite-note { margin: -8px 0 15px; } .selftest-note { color: var(--el-color-warning-dark-2); font-size: 12px; line-height: 1.7; margin: -8px 0 16px; }
.request-key, .notice { font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; margin-top: 10px; } .notice { color: var(--el-color-success-dark-2); }
.history-panel .section-heading { margin-bottom: 16px; } .history-hint { margin: 10px 0; } .history-list { max-height: 520px; overflow-y: auto; }
.history-item { display: block; text-align: left; width: 100%; padding: 13px 11px; margin-bottom: 8px; border: 1px solid var(--el-border-color-lighter); border-radius: 7px; background: var(--el-bg-color); color: inherit; cursor: pointer; }
.history-item:hover, .history-item.selected { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); } .history-item:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
.history-top, .history-bottom { display: flex; justify-content: space-between; gap: 6px; font-size: 12px; } .history-top b { font-size: 13px; } .history-item code { display: block; margin: 9px 0; font-size: 12px; color: var(--el-text-color-secondary); }
.history-bottom { flex-wrap: wrap; line-height: 1.6; } .history-bottom time { color: var(--el-text-color-secondary); } .verdict-success { color: var(--el-color-success-dark-2); } .verdict-danger, .failed { color: var(--el-color-danger); } .verdict-warning { color: var(--el-color-warning-dark-2); } .verdict-info { color: var(--el-text-color-secondary); }
.run-detail { min-width: 0; min-height: 590px; padding: 22px; } .detail-heading { align-items: flex-start; flex-wrap: wrap; } .detail-title { margin-bottom: 10px; } .run-id { display: block; font-size: 12px; overflow-wrap: anywhere; line-height: 1.7; }
.run-meta { display: flex; flex-wrap: wrap; gap: 8px 18px; color: var(--el-text-color-secondary); font-size: 12px; margin: 16px 0; } .metrics { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid var(--el-border-color-lighter); border-radius: 8px; margin: 18px 0; }
.metrics > div { padding: 16px 10px; text-align: center; } .metrics b { display: block; font-size: 24px; font-weight: 600; margin-bottom: 7px; } .metrics span { font-size: 12px; color: var(--el-text-color-secondary); }
.case-id, .assertion-subject { display: block; font-size: 11px; overflow-wrap: anywhere; line-height: 1.65; } .case-id { color: var(--el-text-color-secondary); } .case-section { margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--el-border-color-lighter); } .case-section .section-heading { flex-wrap: wrap; } .dataset { overflow-wrap: anywhere; }
.assertion-value { margin: 0; padding: 0; background: none; font-size: 12px; max-height: 110px; } .assertion-subject { margin: 5px 0; } :deep(.selected-case) { --el-table-tr-bg-color: var(--el-color-primary-light-9); }
.log-controls { display: flex; gap: 12px; align-items: center; margin: 12px 0; } .log-controls .el-select { max-width: 300px; } .execution-log { min-height: 260px; max-height: 580px; padding: 16px; background: var(--el-fill-color-light); font-size: 12px; line-height: 1.7; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; overflow: auto; background: var(--el-fill-color-light); padding: 14px; border-radius: 6px; font-size: 12px; line-height: 1.65; max-height: 460px; } details { margin: 18px 0; font-size: 13px; } summary { cursor: pointer; color: var(--el-color-primary); line-height: 1.8; }
.source-info { display: grid; grid-template-columns: 85px minmax(0, 1fr); gap: 12px; font-size: 12px; margin: 18px 0 24px; } .source-info dt { color: var(--el-text-color-secondary); } .source-info dd { margin: 0; overflow-wrap: anywhere; } .artifact-name { font-size: 12px; overflow-wrap: anywhere; }
.event-list { list-style: none; padding: 0; } .event-list li { border-left: 2px solid var(--el-border-color); margin: 0 0 20px 4px; padding-left: 16px; font-size: 13px; } .event-list li > div { display: flex; gap: 10px; flex-wrap: wrap; justify-content: space-between; } .event-list time { color: var(--el-text-color-secondary); font-size: 12px; } .event-list p { margin: 8px 0; line-height: 1.8; }
@media (max-width: 1120px) { .runner-page { padding: 16px; } .runner-layout { grid-template-columns: 270px minmax(0, 1fr); gap: 14px; } .submit-panel, .history-panel, .run-detail { padding: 16px; } .detail-title { gap: 8px; } }
@media (max-width: 880px) { .runner-layout { grid-template-columns: 1fr; } .runner-sidebar { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; align-items: start; } .runner-sidebar .panel + .panel { margin-top: 0; } .history-list { max-height: 520px; } .heading-actions { width: 100%; } }
@media (max-width: 600px) { .runner-sidebar { grid-template-columns: 1fr; } .history-list { max-height: 240px; } .runner-page { padding: 10px; } h1 { font-size: 21px; } .heading-actions { gap: 8px; } .log-controls { flex-wrap: wrap; } .metrics { grid-template-columns: repeat(2, 1fr); } .run-detail { padding: 12px; } .detail-tabs :deep(.el-tabs__item) { padding: 0 13px; } }
</style>
