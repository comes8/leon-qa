<template>
  <div class="web3-page">
    <div class="page-heading">
      <div><h1>{{ pageInfo.title }}</h1><p>{{ pageInfo.help }}</p></div>
      <div class="workbench-actions"><el-button @click="go('assets')">知识与技能</el-button><el-button v-if="page === 'requirements' || page === 'legacy'" type="primary" @click="openCreate">新建测试</el-button></div>
    </div>
    <el-alert v-if="['requirements','testpoints','cases'].includes(page)" class="batch-note" title="当前查看原 Web3 v1 接口资产。要使用业务 Skill 分阶段生成，请切换上方“业务设计”；这里继续保留原接口生成和执行记录。" type="info" :closable="false" />
    <div class="workspace">
      <aside class="task-sidebar">
        <el-select v-model="projectId" placeholder="选择项目" @change="loadProject">
          <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
        </el-select>
        <el-empty v-if="!runs.length" description="创建第一条测试需求" :image-size="64" />
        <button v-for="item in runs" :key="item.id" class="task" :class="{ active: current?.id === item.id }" @click="selectRun(item.id)">
          <strong>{{ item.title }}</strong><span>#{{ item.id }} · {{ statusLabel(item.status) }}</span>
        </button>
      </aside>
      <main v-if="current" class="run-content">
        <div class="run-heading"><div><h2>{{ current.title }}</h2><p>{{ scopeLabel(current.scope) }} · {{ environmentName }}</p></div><el-tag :type="statusType(current.status)">{{ statusLabel(current.status) }}</el-tag></div>
        <div class="stage-links"><el-button v-for="link in stageLinks" :key="link.key" size="small" :type="page === link.key ? 'primary' : 'default'" @click="go(link.key)">{{ link.title }}</el-button></div>
        <el-alert v-if="current.last_error" :title="current.last_error" type="error" :closable="false" show-icon />
        <div v-if="busy" class="processing"><el-icon class="is-loading"><Loading /></el-icon>{{ statusLabel(current.status) }}，结果会自动更新</div>
        <div class="stage-content">
          <section v-if="['requirements','testpoints','legacy'].includes(page)">
            <p v-if="page !== 'testpoints'" class="requirement">{{ current.requirement }}</p>
            <template v-if="current.analysis">
              <template v-if="page !== 'testpoints'">
              <h3>业务理解</h3><p>{{ current.analysis.summary }}</p>
              <div class="domain-tags"><el-tag v-for="domain in current.analysis.domains" :key="domain">{{ domain }}</el-tag></div>
              <div class="analysis-grid">
                <section v-for="block in analysisBlocks" :key="block.key"><h3>{{ block.label }}</h3><ul><li v-for="text in current.analysis[block.key]" :key="text">{{ text }}</li></ul><p v-if="!current.analysis[block.key]?.length" class="muted">本次未提出</p></section>
              </div>
              <section v-if="current.analysis._review"><h3>分析复核记录</h3><p>{{ current.analysis._review.note }}</p></section>
              </template>
              <template v-if="page !== 'requirements'">
              <h3>覆盖矩阵</h3>
              <el-table :data="current.analysis.coverage" border>
                <el-table-column prop="id" label="编号" width="105" /><el-table-column prop="scenario" label="测试场景" min-width="210" /><el-table-column prop="expected" label="验证预期" min-width="250" />
                <el-table-column label="类别" width="90"><template #default="{ row }">{{ categoryLabel(row.category) }}</template></el-table-column>
                <el-table-column prop="priority" label="优先级" width="80" /><el-table-column label="规则状态" width="100"><template #default="{ row }"><el-tag :type="row.needs_confirmation ? 'warning' : 'success'">{{ row.needs_confirmation ? '待确认' : '有依据' }}</el-tag></template></el-table-column>
              </el-table>
              </template>
              <div class="actions"><el-button :disabled="busy || !!current.publication" @click="editAnalysis">评审与修正分析</el-button><el-button type="primary" :disabled="busy || !!current.publication" @click="action('generate')">确认范围并生成用例</el-button></div>
            </template>
            <div v-else-if="!busy" class="actions"><el-button @click="action('analyze')">重新分析需求</el-button></div>
          </section>
          <section v-if="['cases','scenarios','legacy'].includes(page)">
            <el-empty v-if="!current.draft" description="完成需求分析后生成用例" />
            <template v-else>
              <div class="section-heading"><h3>生成的业务场景</h3><div><el-button v-if="!current.publication" :disabled="busy" @click="editJson">编辑草稿</el-button><el-button v-if="!current.publication" :disabled="busy" @click="action('review')">重新评审</el-button><el-button v-if="!current.publication && current.review" :disabled="busy" type="primary" plain @click="action('revise')">按评审意见修订</el-button></div></div>
              <el-table ref="casesTable" :data="current.draft.scenarios" border @selection-change="selection = $event.map((row: any) => row.case_id)">
                <el-table-column v-if="page !== 'cases'" type="selection" width="45" :selectable="selectable" />
                <el-table-column type="expand"><template #default="{ row }"><div class="case-detail"><p><b>前置条件</b> {{ row.preconditions.join('，') }}</p><p><b>预期</b> {{ row.expected }}</p><p><b>规则</b> {{ row.rule_ids.join('、') }}</p><p v-if="row.blocked_reason" class="warning">{{ row.blocked_reason }}</p><ol><li v-for="(step, index) in row.steps" :key="index"><strong>{{ step.name }}</strong><span class="muted"> · 接口 #{{ step.api_id }} · {{ step.validators.length }} 项断言</span><pre v-if="page !== 'cases'">{{ JSON.stringify({ path_variables: step.path_variables, query: step.query, body: step.body, extracts: step.extracts, validators: step.validators }, null, 2) }}</pre><ul v-else><li v-for="(check, i) in step.validators" :key="i">{{check.check}} · {{comparatorLabel(check.comparator)}} · {{JSON.stringify(check.expect)}}</li></ul></li></ol></div></template></el-table-column>
                <el-table-column prop="case_id" label="用例编号" min-width="140" /><el-table-column prop="name" label="场景" min-width="220" />
                <el-table-column label="类别" width="90"><template #default="{ row }">{{ categoryLabel(row.category) }}</template></el-table-column>
                <el-table-column label="可执行性" min-width="180"><template #default="{ row }"><span :class="caseIssue(row.case_id) ? 'warning' : ''">{{ caseIssue(row.case_id) || (current.review ? '校验通过' : '等待评审') }}</span></template></el-table-column>
              </el-table>
              <section v-if="current.review && page !== 'scenarios'" class="review-panel"><h3>Reviewer 评审</h3><p>{{ current.review.summary }}</p><ul><li v-for="(issue, index) in current.review.issues" :key="index">{{ issue.case_id }} · {{ issue.severity === 'blocking' ? '需处理' : '建议' }} · {{ issue.message }}</li><li v-for="text in current.review.missing_coverage" :key="text">待补覆盖 · {{ text }}</li></ul></section>
              <div v-if="current.status === 'review_ready' && page !== 'cases'" class="publish-panel"><el-input v-model="approvalNote" type="textarea" :rows="2" placeholder="评审备注，可记录本批执行范围和待补项" /><el-checkbox v-model="acknowledge">我已复核所选用例及 Reviewer 意见</el-checkbox><div><el-button type="primary" :disabled="!selection.length || busy" @click="publish">发布所选 {{ selection.length }} 条到接口用例集</el-button></div></div>
              <section v-if="current.approval"><h3>发布复核记录</h3><p>{{ current.approval.note || '已复核所选范围' }}</p><p class="muted">发布基于草稿版本 {{ current.approval.revision }}，修改已发布内容后需重新评审。</p></section>
              <el-alert v-if="current.publication" type="success" :closable="false" :title="`已发布到接口用例集 #${current.publication.suite_id}，共 ${current.publication.cases.length} 条`" />
            </template>
          </section>
          <section v-if="['execution','reports','legacy'].includes(page)">
            <div v-if="current.publication && page !== 'reports'" class="execution-controls"><el-checkbox v-model="confirmEnvironment">确认在 {{ scopeLabel(current.scope) }} / {{ environmentName }} 执行</el-checkbox><el-button type="primary" :disabled="busy || !confirmEnvironment || current.scope === 'binance_reference'" @click="execute">{{ latest ? '重新执行' : '执行用例集' }}</el-button></div>
            <el-button v-if="latest && page !== 'execution'" @click="exportRun">导出本次记录</el-button>
            <el-empty v-if="!latest" description="发布用例集后执行并查看报告" />
            <template v-else><div class="report-summary"><strong>{{ latest.passed_cases ?? 0 }} 条通过</strong><span>{{ latest.failed_cases ?? 0 }} 条失败</span><span>{{ latest.passed_steps }} / {{ latest.total_steps }} 步通过</span><span>{{ latest.blocked_steps }} 个步骤阻塞</span><span>执行编号 {{ latest.result_id }}</span></div>
              <el-collapse v-if="page !== 'execution'"><el-collapse-item v-for="test in latest.cases" :key="test.case_id" :title="`${test.status === 'passed' ? '通过' : '失败'} · ${test.case_id} · ${test.name}`" :name="test.case_id"><div v-for="(step, index) in test.steps" :key="index" class="evidence-step"><h4>{{ index + 1 }}. {{ step.name }} <el-tag :type="step.status === 'passed' ? 'success' : step.status === 'blocked' ? 'warning' : 'danger'">{{ step.status === 'passed' ? '通过' : step.status === 'blocked' ? '阻塞' : '失败' }}</el-tag></h4><p v-if="step.error">{{ step.error }}</p><el-table v-if="step.validators?.length" :data="step.validators" size="small"><el-table-column prop="check" label="断言字段" min-width="150"/><el-table-column label="判断方式" width="100"><template #default="{ row }">{{ comparatorLabel(row.comparator) }}</template></el-table-column><el-table-column label="期望"><template #default="{ row }">{{ row.comparator === 'not_null' ? '非空' : row.comparator === 'is_null' ? '不存在或为空' : JSON.stringify(row.expect) }}</template></el-table-column><el-table-column label="实际"><template #default="{ row }">{{ JSON.stringify(row.actual) }}</template></el-table-column><el-table-column prop="result" label="结果" width="80"/></el-table><details v-if="step.response"><summary>查看请求与响应</summary><pre>{{ JSON.stringify({ request: step.request, response: step.response.body }, null, 2) }}</pre></details></div></el-collapse-item></el-collapse>
              <p class="muted">{{ current.executions.length }} 次执行已保存，每次重跑保留独立编号。</p><el-select v-if="current.executions.length > 1" v-model="historyIndex" placeholder="查看历史执行"><el-option :value="-1" label="最新一次执行"/><el-option v-for="(entry, index) in current.executions" :key="entry.result_id" :value="index" :label="`${entry.result_id} · ${entry.passed_cases ?? 0} 条通过`" /></el-select>
            </template>
          </section>
          <details v-if="current.citations?.length && page !== 'execution'" class="rule-sources"><summary>本任务规则来源（{{current.citations.length}}）</summary><el-collapse><el-collapse-item v-for="source in current.citations" :key="source.source_id" :name="source.source_id" :title="`#${source.source_id} · ${source.title}`"><pre>{{ source.content }}</pre><p class="muted">{{ source.captured_at }} · SHA256 {{ source.sha256.slice(0, 16) }}</p></el-collapse-item></el-collapse></details>
        </div>
      </main>
      <main v-else class="empty-main"><el-empty description="选择历史任务，或输入一条需求开始分析" /></main>
    </div>
    <el-dialog v-model="createVisible" title="新建 Web3 测试" width="min(760px, 94vw)" destroy-on-close>
      <el-form label-position="top">
        <div class="form-grid"><el-form-item label="接口服务"><el-select v-model="form.service_id"><el-option v-for="item in config.services" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="测试环境"><el-select v-model="form.environment_id"><el-option v-for="item in config.environments" :key="item.id" :label="item.name" :value="item.id"/></el-select></el-form-item></div>
        <el-form-item label="规则适用范围"><el-radio-group v-model="form.scope" @change="selectScope"><el-radio value="local_mock" label="local_mock">本机模拟</el-radio><el-radio value="project_qa" label="project_qa">项目测试环境</el-radio><el-radio value="binance_reference" label="binance_reference">币安参考设计</el-radio></el-radio-group></el-form-item>
        <el-form-item label="知识库"><el-select v-model="form.knowledge_base_ids" multiple collapse-tags :max-collapse-tags="2"><el-option v-for="item in config.knowledge_bases" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item>
        <div class="form-grid"><el-form-item label="Writer"><el-select v-model="form.writer_id"><el-option v-for="item in writers" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="Reviewer"><el-select v-model="form.reviewer_id"><el-option v-for="item in reviewers" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item></div>
        <el-form-item label="需求名称"><el-input v-model="form.title" maxlength="180" /></el-form-item>
        <el-form-item label="需求内容"><div class="example-buttons"><el-button v-for="item in examples" :key="item.title" size="small" @click="fillExample(item)">{{ item.title }}</el-button></div><el-input v-model="form.requirement" type="textarea" :rows="7" maxlength="24000" placeholder="描述本次新增或修改的行为、约束和希望验证的结果，也可以粘贴接口需求。" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="createVisible = false">取消</el-button><el-button type="primary" :loading="submitting" @click="createRun">分析需求</el-button></template>
    </el-dialog>
    <el-dialog v-model="analysisEditVisible" title="评审需求分析" width="min(1100px, 96vw)">
      <template v-if="analysisDraft"><el-alert type="info" :closable="false" title="对照规则来源修正预期，已确认的项目可关闭“待确认”。保存会归档当前草稿，并要求重新生成用例。" />
      <el-table :data="analysisDraft.coverage" style="margin:16px 0" max-height="450"><el-table-column prop="id" label="编号" width="105"/><el-table-column prop="scenario" label="场景" min-width="170"/><el-table-column label="预期" min-width="260"><template #default="{ row }"><el-input v-model="row.expected" type="textarea" :autosize="{minRows:2,maxRows:5}" /></template></el-table-column><el-table-column label="待确认" width="100"><template #default="{ row }"><el-switch v-model="row.needs_confirmation" /></template></el-table-column></el-table>
      <el-form label-position="top"><el-form-item label="保留的待确认事项（一行一项）"><el-input v-model="analysisQuestions" type="textarea" :rows="3" /></el-form-item><el-form-item label="复核依据与说明（必填）"><el-input v-model="analysisNote" type="textarea" :rows="2" placeholder="记录已核对的规则编号、确认人或需求说明，不能用推测代替确认" /></el-form-item></el-form></template>
      <template #footer><el-button @click="analysisEditVisible = false">取消</el-button><el-button type="primary" @click="saveAnalysis">保存分析与复核记录</el-button></template>
    </el-dialog>
    <el-dialog v-model="editVisible" title="编辑用例草稿" width="min(1000px, 94vw)"><el-input v-model="draftJson" type="textarea" :rows="24" spellcheck="false"/><template #footer><el-button @click="editVisible = false">取消</el-button><el-button type="primary" @click="saveDraft">保存并重新评审</el-button></template></el-dialog>
  </div>
</template>

<script setup lang="ts" name="Web3Workbench">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue';
import { Loading } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import request from '/@/utils/request';
import { useProjectApi } from '/@/api/v1/projects/project';
import { useRoute, useRouter } from 'vue-router';
import { useUserStore } from '/@/stores/user';
import { readContext, saveContext, workflowPages } from '../web3-area/context';
import type { WorkflowPage } from '../web3-area/context';

const props = withDefaults(defineProps<{page?: WorkflowPage | 'legacy'}>(), {page:'legacy'});
const pageInfo = computed(() => props.page === 'legacy' ? {title:'Web3 接口测试',help:'从需求分析到业务回归'} : workflowPages[props.page]);
const stageLinks = Object.entries(workflowPages).map(([key,value])=>({key,title:value.title}));

const api = '/v1/Ntesterc_web3';
const router = useRouter(), route = useRoute(), user = useUserStore();
const projects = ref<any[]>([]), projectId = ref<number>(), runs = ref<any[]>([]), current = ref<any>(null);
const config = reactive<any>({ services: [], environments: [], knowledge_bases: [], models: [] });
const form = reactive<any>({ service_id: undefined, environment_id: undefined, writer_id: undefined, reviewer_id: undefined, scope: 'local_mock', knowledge_base_ids: [], title: '', requirement: '' });
const createVisible = ref(false), submitting = ref(false), editVisible = ref(false), draftJson = ref('');
const analysisEditVisible = ref(false), analysisDraft = ref<any>(null), analysisQuestions = ref(''), analysisNote = ref('');
const activeTab = ref('analysis'), casesTable = ref<any>(), selection = ref<string[]>([]), approvalNote = ref(''), acknowledge = ref(false), confirmEnvironment = ref(false), historyIndex = ref(-1);
let timer: ReturnType<typeof setInterval> | undefined;
let refreshing = false;
let projectEpoch = 0, selectedEpoch = 0, requestEpoch = 0, alive = true;
const writers = computed(() => config.models.filter((item: any) => item.role === 'writer'));
const reviewers = computed(() => config.models.filter((item: any) => item.role === 'reviewer'));
const busy = computed(() => ['analyzing', 'generating', 'executing', 'publishing'].includes(current.value?.status));
const environmentName = computed(() => config.environments.find((item: any) => item.id === current.value?.environment_id)?.name || '所选环境');
const activeStage = computed(() => current.value?.status === 'passed' ? 4 : current.value?.publication ? 3 : current.value?.draft ? 1 : 0);
const latest = computed(() => historyIndex.value >= 0 ? current.value?.executions?.[historyIndex.value] : current.value?.executions?.at(-1));
const analysisBlocks = [{ key: 'changed_behavior', label: '本次行为与改动' }, { key: 'regression_scope', label: '关联回归范围' }, { key: 'data_plan', label: '测试数据' }, { key: 'open_questions', label: '待确认事项' }];
const examples = [
  { title: '现货撤单', requirement: '在本机 Web3 多业务模拟中验证现货下单 5，价格 10，显式模拟成交 2 后撤销余单。核对原订单号、累计成交 2、剩余冻结归零、独立流水成交支出 20 和解冻 30，账户 free 为 980。补充重复撤单、未知订单、非法数量和 0.01 步长边界场景。每个用例创建独立会话。' },
  { title: '合约只减仓', requirement: '在本机 Web3 多业务模拟中验证合约 LONG 初始持仓 5，reduceOnly=true 减仓 2 后查询持仓为 3。覆盖减仓大于持仓、零数量和 reduceOnly=false 的拒绝行为，每个用例创建独立会话。' },
  { title: '资金幂等', requirement: '在本机 Web3 多业务模拟中验证钱包向合约钱包划转 10，初始余额分别为 100 和 0。相同 clientId 和数量重复提交只产生一笔流水，同一 transferId，最终余额分别 90 和 10。覆盖同一 clientId 改数量冲突及余额不足。每个用例创建独立会话。' },
  { title: 'DEX 兑换', requirement: '在本机 Web3 多业务模拟中验证报价、兑换和回执。报价 chainId=31337，minAmountOut=900，兑换成功后按交易哈希查询回执 status=0x1、amountOut=950 和 balanceDelta=950。覆盖错误链、错误报价和过高 minAmountOut 的拒绝。每个用例创建独立会话。' },
];
const statusLabel = (status: string) => ({ created: '待分析', analyzing: '正在分析', analysis_ready: '待确认范围', generating: '正在生成与评审', review_ready: '待评审发布', draft_edited: '待重新评审', publishing: '正在发布', suite_ready: '待执行', executing: '正在执行', passed: '执行通过', failed: '执行有失败', error: '处理受阻' }[status] || status);
const statusType = (status: string): any => status === 'passed' ? 'success' : ['failed', 'error'].includes(status) ? 'danger' : 'info';
const categoryLabel = (category: string) => ({ positive: '正向', negative: '反向', boundary: '边界', exception: '异常', business: '业务链路' }[category] || category);
const scopeLabel = (scope: string) => ({ local_mock: '本机模拟', project_qa: '项目测试环境', binance_reference: '币安参考设计' }[scope] || scope);
const comparatorLabel = (comparator: string) => ({eq:'等于',ne:'不等于',decimal_eq:'数值相等',decimal_gte:'数值不小于',decimal_lte:'数值不大于',not_null:'非空',is_null:'为空',contains:'包含',gt:'大于',gte:'不小于',lt:'小于',lte:'不大于'}[comparator] || comparator);
const caseIssue = (id: string) => current.value?.review?.technical_issues?.find((issue: any) => issue.case_id === id)?.message;
const selectable = (row: any) => !!current.value?.review && !busy.value && !row.blocked_reason && !!row.steps.length && !caseIssue(row.case_id);
const fail = (error: any) => ElMessage.error(error.response?.data?.detail || error.message || '请求失败');

function syncLocation() {
  if (!projectId.value || !alive) return;
  const context = { ...readContext(user.userInfos.id, { project: String(projectId.value) }), project: String(projectId.value), ...(current.value ? {workflow:String(current.value.id)} : {}) };
  saveContext(user.userInfos.id, context);
  void router.replace({query:{...route.query,...context}});
}
function go(page: string) { syncLocation(); void router.push({path:'/web3/'+page,query:{...readContext(user.userInfos.id,{project:String(projectId.value)}),...(['requirements','testpoints','cases'].includes(page)?{view:'legacy'}:{})}}); }
async function loadRuns() { const project=projectId.value,epoch=projectEpoch; if (project) {const response:any=await request({url:api+'/workflows',params:{project_id:project}});if(alive&&epoch===projectEpoch)runs.value=response.data;} }
async function loadProject() {
  const epoch=++projectEpoch;
  selectedEpoch++;requestEpoch++;
  current.value = null;
  runs.value = [];
  config.services = []; config.environments = []; config.models = []; config.knowledge_bases = [];
  if (!projectId.value) return;
  const requested=readContext(user.userInfos.id,{project:String(projectId.value),...(String(route.query.project)===String(projectId.value)?{workflow:route.query.workflow}:{})});
  try { const response: any = await request({ url: api + '/options', params: { project_id: projectId.value } }); if(!alive||epoch!==projectEpoch)return;Object.assign(config, response.data); await loadRuns();if(!alive||epoch!==projectEpoch)return;if(runs.value.length)await selectRun(runs.value.find(r=>String(r.id)===requested.workflow)?.id||runs.value[0].id);else syncLocation(); } catch (error) {if(alive&&epoch===projectEpoch)fail(error); }
}
async function selectRun(id: number) { selectedEpoch++;current.value=null;selection.value = []; approvalNote.value = ''; acknowledge.value = false; confirmEnvironment.value = false; historyIndex.value = -1; await refresh(id,true); }
async function refresh(id = current.value?.id, force = false) {
  if (!id || (!force&&refreshing)) return;
  const epoch=selectedEpoch,project=projectEpoch,req=++requestEpoch;refreshing = true;
  try { const response: any = await request({ url: api + '/workflows/' + id });if(!alive||epoch!==selectedEpoch||project!==projectEpoch||req!==requestEpoch)return;const before = current.value?.status; current.value = response.data;syncLocation(); if (before !== current.value.status) { await loadRuns(); if (current.value?.status === 'review_ready') { await nextTick(); if(!alive||epoch!==selectedEpoch)return;for (const row of current.value.draft.scenarios) if (selectable(row)) casesTable.value?.toggleRowSelection(row, true); } } } catch (error) {if(alive&&epoch===selectedEpoch&&project===projectEpoch)fail(error); } finally {if(req===requestEpoch)refreshing = false; }
}
function selectScope() { form.knowledge_base_ids = config.knowledge_bases.filter((item: any) => form.scope === 'local_mock' ? item.name.includes('多业务模拟') : form.scope === 'binance_reference' ? item.name.includes('币安') : !item.name.includes('模拟') && !item.name.includes('币安')).map((item: any) => item.id); }
function openCreate() {
  form.service_id = config.services.find((item: any) => item.name.includes('Web3 多业务模拟'))?.id || config.services[0]?.id;
  form.environment_id = config.environments.find((item: any) => item.name === 'Web3 本机模拟')?.id || config.environments[0]?.id;
  form.writer_id = writers.value[0]?.id; form.reviewer_id = reviewers.value[0]?.id; selectScope(); createVisible.value = true;
}
function fillExample(item: any) { form.title = item.title; form.requirement = item.requirement; form.scope = 'local_mock'; selectScope(); }
async function createRun() {
  if (!form.service_id || !form.environment_id || !form.writer_id || !form.reviewer_id || !form.knowledge_base_ids.length || form.title.trim().length < 2 || form.requirement.trim().length < 10) { ElMessage.warning('请填写需求并选择服务、环境、模型和知识库'); return; }
  submitting.value = true;
  try { const response: any = await request({ url: api + '/workflows', method: 'POST', data: { ...form, project_id: projectId.value } }); createVisible.value = false; await selectRun(response.data.id); await loadRuns(); } catch (error) { fail(error); } finally { submitting.value = false; }
}
async function action(action: string) { try { await request({ url: `${api}/workflows/${current.value.id}/actions/${action}`, method: 'POST' }); await refresh(); } catch (error) { fail(error); } }
function editAnalysis() { analysisDraft.value = JSON.parse(JSON.stringify(current.value.analysis)); for (const key of Object.keys(analysisDraft.value)) if (key.startsWith('_')) delete analysisDraft.value[key]; analysisQuestions.value = analysisDraft.value.open_questions.join('\n'); analysisNote.value = ''; analysisEditVisible.value = true; }
async function saveAnalysis() {
  if (analysisNote.value.trim().length < 5) { ElMessage.warning('请填写至少 5 字的复核依据'); return; }
  try { analysisDraft.value.open_questions = analysisQuestions.value.split('\n').map((text: string) => text.trim()).filter(Boolean); await request({ url: `${api}/workflows/${current.value.id}/analysis`, method: 'PUT', data: { revision: current.value.revision, analysis: analysisDraft.value, note: analysisNote.value.trim() } }); analysisEditVisible.value = false; await refresh(); activeTab.value = 'analysis'; } catch (error) { fail(error); }
}
function editJson() { draftJson.value = JSON.stringify(current.value.draft, null, 2); editVisible.value = true; }
async function saveDraft() { try { await request({ url: `${api}/workflows/${current.value.id}/draft`, method: 'PUT', data: { revision: current.value.revision, draft: JSON.parse(draftJson.value) } }); editVisible.value = false; await refresh(); await action('review'); } catch (error) { fail(error); } }
async function publish() { try { await request({ url: `${api}/workflows/${current.value.id}/approve`, method: 'POST', data: { revision: current.value.revision, case_ids: selection.value, note: approvalNote.value, acknowledge_review: acknowledge.value } }); await refresh(); activeTab.value = 'report'; } catch (error) { fail(error); } }
async function execute() { try { await request({ url: `${api}/workflows/${current.value.id}/execute`, method: 'POST', data: { revision: current.value.revision, confirm_test_environment: confirmEnvironment.value } }); historyIndex.value = -1; await refresh(); } catch (error) { fail(error); } }
function exportRun() { const url = URL.createObjectURL(new Blob([JSON.stringify(current.value, null, 2)], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = `web3-workflow-${current.value.id}.json`; link.click(); URL.revokeObjectURL(url); }
onMounted(async () => { try { const response: any = await useProjectApi().getList({ page: 1, page_size: 100 });if(!alive)return;projects.value = response.data.items || response.data.rows || [];const requested=readContext(user.userInfos.id,route.query);projectId.value = projects.value.find((item: any) => String(item.id)===requested.project)?.id || projects.value.find((item: any) => item.name.includes('Web3 QA'))?.id || projects.value[0]?.id; await loadProject();if(alive)timer = setInterval(() => { if (busy.value) void refresh(); }, 1800); } catch (error) {if(alive)fail(error); } });
onUnmounted(() => {alive=false;projectEpoch++;selectedEpoch++;requestEpoch++;if (timer) clearInterval(timer); });
</script>

<style scoped lang="scss">
.web3-page { padding: 20px; height: 100%; overflow: auto; color: var(--el-text-color-primary); }
.batch-note{margin-bottom:18px}.stage-links{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 22px}.stage-links .el-button{margin:0}.rule-sources{margin-top:26px;border-top:1px solid var(--el-border-color-lighter);padding-top:18px}
.page-heading, .run-heading, .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
.page-heading { flex-wrap: wrap; } .workbench-actions { display: flex; flex-wrap: wrap; gap: 8px; } .workbench-actions .el-button + .el-button { margin-left: 0; }
h1 { font-size: 23px; letter-spacing: -.04em; } h2 { font-size: 19px; } h3 { font-size: 15px; margin: 20px 0 12px; } h4 { margin-bottom: 12px; }
p, li { line-height: 1.8; } .page-heading p, .run-heading p, .muted { color: var(--el-text-color-secondary); font-size: 12px; }
.workspace { display: grid; grid-template-columns: 230px minmax(0, 1fr); min-height: 680px; background: var(--el-bg-color); border: 1px solid var(--el-border-color-lighter); border-radius: 12px; }
.task-sidebar { padding: 16px; border-right: 1px solid var(--el-border-color-lighter); }
.task { display: block; width: 100%; text-align: left; padding: 13px 12px; margin-top: 10px; border: 1px solid transparent; border-radius: 8px; background: transparent; color: inherit; cursor: pointer; }
.task strong { display: block; overflow-wrap: anywhere; font-size: 13px; } .task span { display: block; margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.task.active, .task:hover { background: var(--el-color-primary-light-9); border-color: var(--el-color-primary-light-7); }
.run-content { padding: 22px; min-width: 0; } .empty-main { align-content: center; }
.requirement { background: var(--el-fill-color-light); padding: 14px 18px; border-radius: 8px; margin: 12px 0; white-space: pre-wrap; }
.analysis-grid, .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 26px; } ul, ol { padding-left: 22px; } .domain-tags { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
.actions, .publish-panel, .execution-controls { margin: 20px 0; } .execution-controls { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.processing { display: flex; align-items: center; gap: 8px; color: var(--el-color-primary); padding: 14px 0; }
.case-detail { padding: 12px 24px; } pre { padding: 12px; background: var(--el-fill-color-light); font-size: 12px; line-height: 1.65; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; max-height: 400px; }
.warning { color: var(--el-color-warning-dark-2); } .review-panel { padding-bottom: 12px; } .report-summary { display: flex; flex-wrap: wrap; gap: 16px; padding: 16px; margin: 12px 0; border-radius: 8px; background: var(--el-fill-color-light); }
.evidence-step { padding: 16px 0; border-bottom: 1px solid var(--el-border-color-lighter); } details { margin-top: 12px; } summary { cursor: pointer; } .el-select { width: 100%; }
.example-buttons { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 10px; } .example-buttons .el-button + .el-button { margin-left: 0; }
@media (max-width: 900px) { .workspace { grid-template-columns: 1fr; } .task-sidebar { border-right: 0; border-bottom: 1px solid var(--el-border-color-lighter); } .task { display: inline-block; width: auto; margin-right: 8px; } .run-content { padding: 14px; } .analysis-grid, .form-grid { grid-template-columns: 1fr; } }
</style>
