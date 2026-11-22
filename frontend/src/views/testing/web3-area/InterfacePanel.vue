<template>
	<div class="interface-page">
		<header>
			<div>
				<h1>{{ titles[presentation] }}</h1>
				<p>固定业务用例与接口版本，串行编排，按当次证据核对</p>
			</div>
			<div class="buttons">
				<el-button @click="refresh">刷新记录</el-button><el-button :disabled="!state.task" @click="exportPlan">导出适配与证据</el-button
				><el-button
					v-if="presentation === 'mapping'"
					type="primary"
					:disabled="!state.project || state.loading || !state.options || submitting"
					@click="openCreate"
					>新建接口适配批次</el-button
				>
			</div>
		</header>
		<el-alert v-if="state.error || error" :title="state.error || error" type="error" :closable="false" class="notice" />
		<el-alert v-if="pending" title="上次提交结果待确认，先按原请求确认；不要更换请求号重复发起。" type="warning" :closable="false" class="notice"
			><el-button :loading="submitting" @click="sendPending">按原请求确认或提交</el-button></el-alert
		>
		<div class="workspace">
			<aside>
				<el-select v-model="project" aria-label="接口适配所属项目" :disabled="submitting" @change="changeProject"
					><el-option v-for="p in projects" :key="p.id" :value="p.id" :label="p.name"
				/></el-select>
				<p class="muted">本项目自己的适配批次与修订版本</p>
				<button
					v-for="p in state.tasks"
					:key="p.id"
					:class="{ selected: state.task?.id === p.id }"
					:aria-label="`选择接口适配 ${p.id}`"
					@click="select(p.id)"
				>
					<strong>{{ p.title }}</strong
					><span>#{{ p.id }} · v{{ p.version }} · 业务设计#{{ p.task_id }}</span></button
				><el-empty v-if="!state.tasks.length && !state.loading" description="尚无适配批次" :image-size="45" />
			</aside>
			<main v-if="plan">
				<h2>{{ plan.title }}</h2>
				<p>
					适配#{{ plan.id }} · v{{ plan.version }} · 业务设计#{{ plan.task_id }} · 用例产物#{{ plan.snapshot.business_binding.cases }} / 评审#{{
						plan.snapshot.business_binding.case_review
					}}
				</p>
				<div class="buttons">
					<el-tag>{{ scopeLabel(plan.snapshot.target.scope) }}</el-tag
					><el-button @click="go('scenarios')">接口映射</el-button><el-button @click="go('execution')">执行中心</el-button
					><el-button @click="go('reports')">报告与证据</el-button
					><el-button @click="router.push({ path: '/web3/cases', query: { ...context(), view: 'business' } })">查看业务用例</el-button>
				</div>
				<el-alert v-if="plan.blockers.length" :title="plan.blockers.join('；')" type="warning" :closable="false" class="notice" />
				<el-alert
					v-if="plan.busy_job_id"
					:title="`任务 #${plan.busy_job_id} 正在处理；离开页面后记录仍保留，不自动重放请求。`"
					type="info"
					:closable="false"
					class="notice"
				/>
				<template v-if="presentation === 'mapping'">
					<section class="panel">
						<h3>接口契约与环境</h3>
						<p>
							服务#{{ plan.snapshot.target.service_id }} · 环境#{{ plan.snapshot.target.environment_id }} ·
							{{ plan.snapshot.target.target_hint || '目录使用固定地址' }}
						</p>
						<el-collapse
							><el-collapse-item title="查看已固定的接口文档与环境摘要" name="catalogue"
								><el-table :data="plan.snapshot.target.api_catalogue" border
									><el-table-column prop="api_id" label="接口ID" width="90" /><el-table-column
										prop="method"
										label="方法"
										width="85" /><el-table-column prop="name" label="接口" min-width="170" /><el-table-column
										prop="description"
										label="契约说明"
										min-width="300"
								/></el-table>
								<pre>{{ JSON.stringify(plan.snapshot.target, null, 2) }}</pre>
							</el-collapse-item></el-collapse
						><el-alert type="info" :closable="false" title="数据准备、动作、观察和收尾都作为显式步骤。只有查询可轮询；写请求不自动重试。" />
						<el-input
							v-model="instruction"
							aria-label="接口适配范围说明"
							type="textarea"
							:rows="3"
							placeholder="例如：各用例独立创建会话；对金额使用独立预期；缺少接口或观察能力时明确受阻。"
							:disabled="!!plan.busy_job_id || submitting"
						/>
						<div class="buttons">
							<el-button type="primary" :disabled="!canOperate || !!plan.content || !!pending" :loading="submitting" @click="previewGenerate"
								>预览并生成接口映射</el-button
							><el-button :disabled="!canOperate" @click="openEdit(plan.content)">{{ plan.content ? '另存接口修订' : '人工录入接口映射' }}</el-button>
						</div>
					</section>
					<section v-if="plan.content" class="panel">
						<h3>业务用例到接口步骤</h3>
						<p>{{ plan.content.summary }}</p>
						<el-alert
							v-if="plan.technical_issues.length"
							type="warning"
							:closable="false"
							:title="`${plan.technical_issues.length}项技术或业务映射阻塞；展开下方查看。`"
						/><el-table :data="plan.technical_issues" v-if="plan.technical_issues.length" border
							><el-table-column prop="case_id" label="业务用例" width="140" /><el-table-column
								prop="message"
								label="需处理问题"
								min-width="300" /></el-table
						><el-collapse
							><el-collapse-item v-for="c in plan.content.scenarios" :key="c.case_id" :name="c.case_id" :title="`${c.case_id} · ${c.name}`"
								><p><strong>业务预期：</strong>{{ c.expected }}</p>
								<p v-if="c.blocked_reason"><strong>受阻：</strong>{{ c.blocked_reason }}</p>
								<el-table :data="c.preparations" border
									><el-table-column prop="item" label="准备项" min-width="180" /><el-table-column label="状态" width="130"
										><template #default="{ row }">{{ prepLabel(row.status) }}</template></el-table-column
									><el-table-column prop="basis" label="文档依据" min-width="260"
								/></el-table>
								<ol>
									<li v-for="(s, i) in c.steps" :key="i">
										<strong>{{ s.name }}</strong>
										<p>{{ purposeLabel(s.purpose) }} · API#{{ s.api_id }} · 对应业务步骤 {{ s.business_steps.join(', ') || '辅助准备/收尾' }}</p>
										<p>{{ s.rationale }}</p>
										<pre>{{
											JSON.stringify(
												{
													请求体: s.body,
													查询: s.query,
													路径变量: s.path_variables,
													抽取: s.extracts,
													断言: s.validators,
													查询轮询: s.poll_attempts,
												},
												null,
												2
											)
										}}</pre>
									</li>
								</ol>
								<p v-for="g in c.execution_gaps" :key="g">执行缺口：{{ g }}</p>
								<p v-for="g in c.observation_limitations" :key="g">观察边界：{{ g }}</p></el-collapse-item
							></el-collapse
						>
						<div v-if="plan.approval" class="confirmation">
							<strong>本版已人工复核并发布</strong>
							<p>{{ plan.approval.note }}</p>
							<p>原生用例集#{{ plan.publication.suite_id }}；发布不表示执行通过。</p>
						</div>
						<el-button v-else type="success" :disabled="!canOperate" @click="openPublish">复核并发布可执行场景</el-button>
					</section>
				</template>
				<template v-else-if="presentation === 'execution'"
					><section class="panel">
						<h3>执行已发布版本</h3>
						<p>
							接口服务#{{ plan.snapshot.target.service_id }} · 环境#{{ plan.snapshot.target.environment_id }} ·
							{{ scopeLabel(plan.snapshot.target.scope) }}
						</p>
						<p>每条用例有自己的数据准备与变量上下文，步骤顺序执行；失败后依赖步骤受阻，其余独立用例继续。每次新运行保留独立证据。</p>
						<el-alert v-if="!plan.publication" title="尚未发布。先到接口映射核对数据、断言及观察能力。" type="warning" :closable="false" />
						<div class="buttons">
							<el-button
								type="primary"
								:disabled="!canOperate || !plan.publication || !!pending || plan.snapshot.target.scope === 'reference_only'"
								@click="runVisible = true"
								>确认环境并运行</el-button
							><el-button v-if="runningJob?.kind === 'execute'" type="warning" @click="cancelVisible = true">请求停止后续步骤</el-button>
						</div>
					</section></template
				>
				<section class="panel">
					<h3>{{ presentation === 'reports' ? '运行与生成记录' : '阶段任务记录' }}</h3>
					<p class="muted">任务完成与业务通过分开显示；失败或中断不自动重放。停止会在请求边界生效，已发出的请求可能完成。</p>
					<el-table :data="plan.jobs" border
						><el-table-column prop="id" label="任务" width="80" /><el-table-column label="动作" width="110"
							><template #default="{ row }">{{ row.kind === 'execute' ? '接口执行' : '模型适配' }}</template></el-table-column
						><el-table-column label="任务状态" width="140"
							><template #default="{ row }">{{ jobLabel(row.status) }}</template></el-table-column
						><el-table-column label="业务判定 / 错误" min-width="240"
							><template #default="{ row }">{{
								row.error_message || (row.kind === 'execute' ? interfaceVerdict(row.receipt, row.status) : '生成不是执行通过')
							}}</template></el-table-column
						><el-table-column label="证据" width="100"
							><template #default="{ row }"><el-button link type="primary" @click="showJob(row.id)">查看详情</el-button></template></el-table-column
						></el-table
					>
				</section>
				<InterfaceEvidence v-if="presentation !== 'mapping'" :jobs="plan.jobs" />
			</main>
			<main v-else><el-empty :description="state.loading ? '正在读取项目…' : '选择一个适配批次，或从接口映射新建。'" /></main>
		</div>
		<el-dialog v-model="createVisible" title="从已复核业务用例新建接口适配" width="min(840px,95vw)" :close-on-click-modal="false"
			><el-form label-position="top"
				><el-form-item label="批次名称"><el-input v-model="form.title" aria-label="接口适配批次名称" /></el-form-item
				><el-form-item label="业务设计"
					><el-select v-model="form.task_id" aria-label="适配业务设计" @change="loadBusiness"
						><el-option v-for="t in state.options.tasks" :key="t.id" :value="t.id" :label="`#${t.id} · ${t.title}`" /></el-select></el-form-item
				><el-form-item label="本批业务用例"
					><el-checkbox-group v-model="form.case_ids"
						><el-checkbox v-for="c in business?.heads.cases?.content.cases || []" :key="c.id" :value="c.id"
							>{{ c.id }} · {{ c.title }}</el-checkbox
						></el-checkbox-group
					></el-form-item
				><el-alert
					v-if="
						business &&
						(!business.heads.cases?.confirmation ||
							!business.heads.case_review?.confirmation ||
							!business.heads.cases?.fresh ||
							!business.heads.case_review?.fresh)
					"
					title="请先完成并复核最新业务用例及用例评审。"
					type="warning"
					:closable="false" /><el-form-item label="接口服务"
					><el-select v-model="form.service_id" aria-label="适配接口服务"
						><el-option v-for="s in state.options.services" :key="s.id" :value="s.id" :label="s.name" /></el-select></el-form-item
				><el-form-item label="执行环境"
					><el-select v-model="form.environment_id" aria-label="适配执行环境"
						><el-option v-for="e in state.options.environments" :key="e.id" :value="e.id" :label="e.name" /></el-select></el-form-item
				><el-form-item label="适用范围"
					><el-select v-model="form.scope" aria-label="接口适配范围"
						><el-option label="本地模拟" value="local_mock" /><el-option label="项目QA/testnet（需既有授权环境）" value="project_qa" /><el-option
							label="外部参考设计（不执行）"
							value="reference_only" /></el-select></el-form-item
			></el-form>
			<p>保存固定业务用例、评审、接口文档与环境摘要；不会调用模型或执行请求。</p>
			<template #footer
				><el-button @click="createVisible = false">返回</el-button
				><el-button type="primary" :loading="submitting" @click="createPlan">保存适配批次</el-button></template
			></el-dialog
		>
		<el-dialog v-model="previewVisible" title="接口适配调用预览" width="min(1000px,95vw)" :close-on-click-modal="false"
			><template v-if="preview"
				><p>模型：{{ preview.snapshot.model.name }} / {{ preview.snapshot.model.model }}</p>
				<p>业务用例{{ preview.snapshot.business.selected_cases.length }}条；已登记接口{{ preview.snapshot.target.api_catalogue.length }}个。</p>
				<el-alert title="确认后才调用已配置模型并消耗额度；此操作不执行接口。" type="warning" :closable="false" /><el-collapse
					><el-collapse-item title="查看完整方法、业务与接口文档">
						<pre>{{ JSON.stringify(preview.snapshot, null, 2) }}</pre>
					</el-collapse-item></el-collapse
				></template
			><template #footer
				><el-button @click="previewVisible = false">返回</el-button
				><el-button type="primary" :loading="submitting" @click="submit('generate')">确认生成接口映射</el-button></template
			></el-dialog
		>
		<el-dialog v-model="editVisible" title="另存接口映射新版本" width="min(1000px,95vw)" :close-on-click-modal="false"
			><p>原版发布及证据保留，新版本需重新复核。业务用例ID与范围不变；不可编造接口。</p>
			<el-collapse
				><el-collapse-item title="查看接口映射字段规范">
					<pre>{{ JSON.stringify(state.options.schema, null, 2) }}</pre>
				</el-collapse-item></el-collapse
			><el-input v-model="editJson" aria-label="接口映射JSON" type="textarea" :rows="18" /><el-input
				v-model="note"
				aria-label="接口修订说明"
				type="textarea"
				:rows="3"
				placeholder="修改依据（至少5字）"
			/><template #footer
				><el-button @click="editVisible = false">返回</el-button
				><el-button type="primary" :loading="submitting" @click="saveRevision">另存适配版本</el-button></template
			></el-dialog
		>
		<el-dialog v-model="publishVisible" title="复核接口映射并发布" width="min(750px,95vw)"
			><p>选择已补齐数据、接口和观察能力的用例；技术阻塞项不可发布。发布不会执行接口。</p>
			<el-checkbox-group v-model="selectedCases"
				><el-checkbox v-for="c in plan?.content?.scenarios || []" :key="c.case_id" :value="c.case_id"
					>{{ c.case_id }} · {{ c.name }}</el-checkbox
				></el-checkbox-group
			><el-input
				v-model="note"
				aria-label="接口发布复核说明"
				type="textarea"
				:rows="4"
				placeholder="记录接口映射、数据、断言与观察范围，至少8字"
			/><el-checkbox v-model="confirmMapping">已核对映射、数据准备、独立预期与观察能力</el-checkbox
			><template #footer
				><el-button @click="publishVisible = false">返回</el-button
				><el-button type="success" :loading="submitting" @click="publish">复核并发布</el-button></template
			></el-dialog
		>
		<el-dialog v-model="runVisible" title="确认本次执行环境" width="min(700px,95vw)"
			><p>
				适配#{{ plan?.id }} · 版本v{{ plan?.version }}；接口服务#{{ plan?.snapshot.target.service_id }}，环境#{{
					plan?.snapshot.target.environment_id
				}}。
			</p>
			<p>{{ scopeLabel(plan?.snapshot.target.scope) }} · {{ plan?.snapshot.target.target_hint || '使用固定接口目录地址' }}</p>
			<p>执行已发布场景的数据准备、业务动作、查询断言和约定收尾；写请求不自动重试。</p>
			<el-checkbox v-model="confirmEnvironment">已确认测试环境与本次隔离数据范围</el-checkbox
			><template #footer
				><el-button @click="runVisible = false">返回</el-button
				><el-button type="primary" :loading="submitting" @click="submit('execute')">开始本次接口执行</el-button></template
			></el-dialog
		>
		<el-dialog v-model="cancelVisible" title="请求停止后续步骤" width="min(650px,95vw)"
			><p>停止在请求边界生效；已发出的请求可能已生效，先按原标识核对，不自动回滚。</p>
			<el-input v-model="cancelNote" aria-label="停止执行原因" type="textarea" :rows="3" /><template #footer
				><el-button @click="cancelVisible = false">返回</el-button
				><el-button type="warning" :loading="submitting" @click="cancel">提交停止请求</el-button></template
			></el-dialog
		>
		<el-dialog v-model="jobVisible" title="接口任务详情与原始证据" width="min(1100px,95vw)"
			><template v-if="job"
				><el-button v-if="presentation === 'mapping' && job.candidate && canOperate" @click="adoptCandidate">以候选稿另存修订</el-button>
				<pre>{{ JSON.stringify(job, null, 2) }}</pre>
			</template></el-dialog
		>
	</div>
</template>
<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useProjectApi } from '/@/api/v1/projects/project';
import { useUserStore } from '/@/stores/user';
import { createDesignController, initialDesignState, errorText, requestUncertain } from './design-state';
import { designApi } from './design-api';
import { interfaceApi, interfaceVerdict, validInterfaceExport } from './interface-api';
import { readContext, saveContext } from './context';
import InterfaceEvidence from './InterfaceEvidence.vue';
const props = defineProps<{ presentation: 'mapping' | 'execution' | 'reports' }>(),
	route = useRoute(),
	router = useRouter(),
	user = useUserStore();
const state = reactive(initialDesignState()),
	controller = createDesignController(state, interfaceApi),
	plan = computed(() => state.task),
	projects = ref<any[]>([]),
	project = ref(''),
	error = ref(''),
	submitting = ref(false),
	instruction = ref('');
const titles = { mapping: '接口场景', execution: '业务设计场景执行', reports: '业务设计场景证据' };
const createVisible = ref(false),
	form = reactive<any>({}),
	business = ref<any>(null),
	createKey = ref(''),
	previewVisible = ref(false),
	preview = ref<any>(null),
	prepared = ref<any>(null),
	pending = ref<any>(null);
const editVisible = ref(false),
	editJson = ref(''),
	editKey = ref(''),
	editBody = ref<any>(null),
	note = ref(''),
	publishVisible = ref(false),
	selectedCases = ref<string[]>([]),
	confirmMapping = ref(false),
	runVisible = ref(false),
	confirmEnvironment = ref(false),
	cancelVisible = ref(false),
	cancelNote = ref(''),
	jobVisible = ref(false),
	job = ref<any>(null);
let alive = true,
	epoch = 0,
	jobEpoch = 0,
	businessEpoch = 0,
	timer: ReturnType<typeof setTimeout> | undefined;
const canOperate = computed(() => !!plan.value && !plan.value.busy_job_id && !plan.value.blockers.length && !submitting.value),
	runningJob = computed(() => plan.value?.jobs.find((j: any) => j.id === plan.value.busy_job_id));
const scopeLabel = (s: string) => (({ local_mock: '本地合成模拟', project_qa: '项目QA/testnet', reference_only: '外部参考设计' } as any)[s] || s);
const jobLabel = (s: string) =>
	(({ queued: '等待处理', running: '处理中', succeeded: '任务完成', failed: '任务失败', cancelled: '已停止', interrupted: '已中断' } as any)[s] || s);
const prepLabel = (s: string) => (({ documented: '文档已说明', needs_preparation: '需要补齐', not_applicable: '本批不适用' } as any)[s] || s);
const purposeLabel = (s: string) => (({ setup: '数据准备', action: '业务动作', observe: '观察核对', cleanup: '隔离收尾' } as any)[s] || s);
function context() {
	return {
		...readContext(user.userInfos.id, { project: state.project }),
		project: state.project,
		...(plan.value ? { design: String(plan.value.task_id), plan: String(plan.value.id) } : {}),
	};
}
function sync() {
	if (!alive) return;
	const ctx = context();
	saveContext(user.userInfos.id, ctx);
	void router.replace({ query: { ...ctx, engine: 'design', view: 'business' } });
}
function go(page: string) {
	void router.push({ path: '/web3/' + page, query: { ...context(), engine: 'design', view: 'business' } });
}
function pendingKey() {
	return `leon.web3.interface.pending.v1.${user.userInfos.id}.${state.project}`;
}
function loadPending() {
	try {
		pending.value = JSON.parse(sessionStorage.getItem(pendingKey()) || 'null');
	} catch {
		pending.value = null;
	}
}
async function changeProject() {
	const mine = ++epoch;
	error.value = '';
	createVisible.value = false;
	editVisible.value = false;
	jobVisible.value = false;
	previewVisible.value = false;
	await controller.project(project.value, String(route.query.project) === project.value ? String(route.query.plan || '') : undefined);
	if (alive && mine === epoch) {
		loadPending();
		sync();
	}
}
async function select(id: number) {
	if (submitting.value) return;
	++epoch;
	jobVisible.value = false;
	previewVisible.value = false;
	error.value = '';
	await controller.select(id);
	sync();
}
async function refresh() {
	error.value = '';
	await controller.refresh();
	sync();
}
async function loadBusiness() {
	const mine = ++businessEpoch,
		id = form.task_id;
	business.value = null;
	try {
		const result = await designApi.detail(id);
		if (alive && mine === businessEpoch && String(result.project_id) === state.project) {
			business.value = result;
			form.case_ids = (result.heads.cases?.content.cases || []).filter((c: any) => c.design_readiness === 'ready').map((c: any) => c.id);
		}
	} catch (e) {
		if (alive && mine === businessEpoch) error.value = errorText(e);
	}
}
async function openCreate() {
	if (state.loading || !state.options?.tasks) return;
	createKey.value = crypto.randomUUID();
	const ctx = readContext(user.userInfos.id, route.query);
	Object.assign(form, {
		title: '',
		task_id: state.options.tasks.find((t: any) => String(t.id) === ctx.design)?.id || state.options.tasks[0]?.id,
		service_id: state.options.services.find((s: any) => s.name.includes('现货本地契约 v2'))?.id || state.options.services[0]?.id,
		environment_id: state.options.environments.find((e: any) => e.name.includes('本地现货隔离环境 v2'))?.id || state.options.environments[0]?.id,
		scope: 'local_mock',
		case_ids: [],
	});
	createVisible.value = true;
	if (form.task_id) await loadBusiness();
}
async function createPlan() {
	submitting.value = true;
	error.value = '';
	try {
		const result = await interfaceApi.create({ ...form, request_key: createKey.value });
		if (!alive) return;
		createVisible.value = false;
		await controller.project(state.project, String(result.id));
		sync();
	} catch (e) {
		if (alive) error.value = errorText(e);
	} finally {
		if (alive) submitting.value = false;
	}
}
async function previewGenerate() {
	if (!plan.value) return;
	const id = plan.value.id,
		mine = epoch;
	submitting.value = true;
	error.value = '';
	try {
		const body = { expected_revision: plan.value.revision, request_key: crypto.randomUUID(), instruction: instruction.value };
		const p = await interfaceApi.preview(id, body);
		if (!alive || mine !== epoch || plan.value?.id !== id) return;
		preview.value = p;
		prepared.value = { ...body, preview_hash: p.input_hash };
		previewVisible.value = true;
	} catch (e) {
		if (alive && mine === epoch) error.value = errorText(e);
	} finally {
		if (alive) submitting.value = false;
	}
}
async function submit(kind: string) {
	if (!plan.value) return;
	if (kind === 'execute' && !confirmEnvironment.value) {
		error.value = '请先确认测试环境和隔离数据范围';
		return;
	}
	const value = {
		project: state.project,
		pid: plan.value.id,
		kind,
		body:
			kind === 'generate'
				? prepared.value
				: { expected_revision: plan.value.revision, request_key: crypto.randomUUID(), confirm_test_environment: true },
	};
	try {
		sessionStorage.setItem(pendingKey(), JSON.stringify(value));
	} catch {
		error.value = '无法保存请求号，本次尚未提交；请恢复浏览器会话存储后重试。';
		return;
	}
	pending.value = value;
	await sendPending();
}
async function sendPending() {
	const value = pending.value;
	if (!value || value.project !== state.project) return;
	const mine = epoch,
		storageKey = pendingKey();
	submitting.value = true;
	error.value = '';
	try {
		await (value.kind === 'generate' ? interfaceApi.generate : interfaceApi.run)(value.pid, value.body);
		sessionStorage.removeItem(storageKey);
		pending.value = null;
		if (alive && mine === epoch && state.project === value.project) {
			previewVisible.value = false;
			runVisible.value = false;
			confirmEnvironment.value = false;
			await controller.select(value.pid);
			sync();
		}
	} catch (e) {
		if (!requestUncertain(e)) {
			sessionStorage.removeItem(storageKey);
			pending.value = null;
		}
		if (alive) error.value = errorText(e);
	} finally {
		if (alive) submitting.value = false;
	}
}
function openEdit(content: any) {
	editKey.value = crypto.randomUUID();
	editBody.value = null;
	note.value = '';
	editJson.value = JSON.stringify(content || { summary: '', scenarios: [] }, null, 2);
	editVisible.value = true;
}
async function saveRevision() {
	submitting.value = true;
	error.value = '';
	try {
		const body = {
			expected_revision: plan.value.revision,
			request_key: editKey.value,
			content: JSON.parse(editJson.value),
			note: note.value,
		};
		if (editBody.value && JSON.stringify(editBody.value) !== JSON.stringify(body)) {
			throw new Error('上次修订提交结果尚未确认，请保持内容按原请求重试，或关闭后重新打开修订。');
		}
		editBody.value = body;
		const child = await interfaceApi.revise(plan.value.id, body);
		if (alive) {
			editVisible.value = false;
			await controller.project(state.project, String(child.id));
			sync();
		}
	} catch (e) {
		if (!requestUncertain(e)) editBody.value = null;
		if (alive) error.value = errorText(e);
	} finally {
		if (alive) submitting.value = false;
	}
}
function openPublish() {
	note.value = '';
	confirmMapping.value = false;
	selectedCases.value = plan.value.content.scenarios
		.filter((c: any) => !plan.value.technical_issues.some((i: any) => i.case_id === c.case_id || i.case_id === '*'))
		.map((c: any) => c.case_id);
	publishVisible.value = true;
}
async function publish() {
	submitting.value = true;
	error.value = '';
	try {
		const result = await interfaceApi.publish(plan.value.id, {
			expected_revision: plan.value.revision,
			case_ids: selectedCases.value,
			note: note.value,
			confirm_mapping: confirmMapping.value,
		});
		if (alive) {
			controller.accept(result);
			publishVisible.value = false;
		}
	} catch (e) {
		if (alive) error.value = errorText(e);
	} finally {
		if (alive) submitting.value = false;
	}
}
async function showJob(id: number) {
	const pid = plan.value.id,
		mine = ++jobEpoch;
	try {
		const result = await interfaceApi.job(pid, id);
		if (alive && plan.value?.id === pid && mine === jobEpoch) {
			job.value = result;
			jobVisible.value = true;
		}
	} catch (e) {
		if (alive && plan.value?.id === pid) error.value = errorText(e);
	}
}
function adoptCandidate() {
	openEdit(job.value.candidate);
	jobVisible.value = false;
}
async function cancel() {
	if (!runningJob.value) return;
	submitting.value = true;
	try {
		await interfaceApi.cancel(plan.value.id, runningJob.value.id, cancelNote.value);
		cancelVisible.value = false;
		await refresh();
	} catch (e) {
		error.value = errorText(e);
	} finally {
		submitting.value = false;
	}
}
async function exportPlan() {
	try {
		const id = plan.value.id,
			data = validInterfaceExport(await interfaceApi.export(id), id),
			url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
		const a = document.createElement('a');
		a.href = url;
		a.download = `web3-interface-${id}.json`;
		a.click();
		setTimeout(() => URL.revokeObjectURL(url), 1000);
	} catch (e) {
		error.value = errorText(e);
	}
}
async function poll() {
	if (plan.value?.busy_job_id) await controller.refresh();
	if (alive) timer = setTimeout(poll, state.error ? 7000 : 1800);
}
onMounted(async () => {
	try {
		const response: any = await useProjectApi().getList({ page: 1, page_size: 100 });
		if (!alive) return;
		projects.value = (response.data.items || response.data.rows || []).map((p: any) => ({ id: String(p.id), name: p.name }));
		const ctx = readContext(user.userInfos.id, route.query);
		project.value = projects.value.find((p) => p.id === ctx.project)?.id || projects.value[0]?.id || '';
		if (project.value) {
			await controller.project(project.value, ctx.plan);
			loadPending();
			sync();
		}
		if (alive) timer = setTimeout(poll, 1800);
	} catch (e) {
		if (alive) error.value = errorText(e);
	}
});
onUnmounted(() => {
	alive = false;
	++epoch;
	++jobEpoch;
	++businessEpoch;
	if (timer) clearTimeout(timer);
	controller.dispose();
});
</script>
<style scoped>
.interface-page {
	padding: 24px;
	font-size: 15px;
	color: var(--el-text-color-primary);
}
header {
	display: flex;
	justify-content: space-between;
	gap: 20px;
	flex-wrap: wrap;
}
h1 {
	font-size: 24px;
	margin: 0 0 8px;
}
h2 {
	font-size: 20px;
}
h3 {
	font-size: 17px;
}
p,
li {
	line-height: 1.8;
	overflow-wrap: anywhere;
}
.muted {
	font-size: 14px;
	color: var(--el-text-color-secondary);
}
.buttons {
	display: flex;
	flex-wrap: wrap;
	gap: 10px;
	margin: 15px 0;
}
.buttons .el-button {
	margin: 0;
}
.notice {
	margin: 16px 0;
}
.workspace {
	display: grid;
	grid-template-columns: 240px minmax(0, 1fr);
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 12px;
	margin-top: 20px;
	overflow: hidden;
	background: var(--el-bg-color);
}
aside {
	padding: 18px;
	border-right: 1px solid var(--el-border-color-lighter);
}
aside > button {
	display: block;
	text-align: left;
	width: 100%;
	padding: 14px 10px;
	border: 1px solid transparent;
	border-radius: 8px;
	background: transparent;
	color: inherit;
	font: inherit;
	margin: 7px 0;
	cursor: pointer;
}
aside > button span {
	display: block;
	font-size: 13px;
	color: var(--el-text-color-secondary);
	margin-top: 8px;
}
aside > button.selected {
	border-color: var(--el-color-primary-light-7);
	background: var(--el-color-primary-light-9);
}
main {
	padding: 22px;
	min-width: 0;
}
.panel {
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 10px;
	padding: 20px;
	margin: 20px 0;
}
.confirmation {
	padding: 15px;
	border-radius: 8px;
	background: var(--el-fill-color-light);
}
pre {
	white-space: pre-wrap;
	overflow-wrap: anywhere;
	max-height: 60vh;
	overflow: auto;
	background: var(--el-fill-color-light);
	padding: 15px;
	font: 13px/1.8 ui-monospace, monospace;
}
.el-select {
	width: 100%;
}
.el-checkbox-group {
	display: flex;
	flex-direction: column;
	align-items: flex-start;
}
.el-checkbox {
	height: auto;
	margin: 8px 0;
	white-space: normal;
}
.el-textarea {
	margin: 12px 0;
}
li {
	margin: 16px 0;
}
@media (max-width: 1000px) {
	.workspace {
		grid-template-columns: 1fr;
	}
	aside {
		border-right: 0;
		border-bottom: 1px solid var(--el-border-color-lighter);
	}
	.interface-page {
		padding: 16px;
	}
	main,
	.panel {
		padding: 16px;
	}
}
</style>
