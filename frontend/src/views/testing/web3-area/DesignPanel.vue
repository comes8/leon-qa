<template>
	<div class="design-page">
		<header>
			<div>
				<h1>{{ pageTitle }}</h1>
				<p>需求、业务规则与设计产物逐版关联，无需先配置接口或执行环境</p>
			</div>
			<div class="buttons">
				<el-button :disabled="submitting" @click="refreshTask">刷新设计</el-button
				><el-button @click="router.push({ path: '/web3/assets', query: context() })">知识与技能</el-button
				><el-button
					v-if="section === 'cases'"
					:disabled="!state.task"
					@click="router.push({ path: '/web3/scenarios', query: { ...context(), view: 'business' } })"
					>适配接口场景</el-button
				><el-button :disabled="!state.task || submitting" @click="exportTask">导出设计记录</el-button
				><el-button type="primary" :disabled="!state.project || submitting" @click="openTask(false)">新建业务设计</el-button>
			</div>
		</header>
		<el-alert v-if="state.error || localError" class="notice" :title="state.error || localError" type="error" :closable="false" show-icon />
		<el-alert
			v-if="pending"
			class="notice"
			title="上次模型提交结果待确认。可刷新查看，或按原请求确认；不要新建请求号反复提交。"
			type="warning"
			:closable="false"
			><el-button :loading="submitting" @click="retryPending">按原请求确认或提交</el-button></el-alert
		>
		<div class="workspace">
			<aside class="task-list">
				<el-select v-model="project" aria-label="业务设计所属项目" :disabled="submitting" @change="changeProject"
					><el-option v-for="p in projects" :key="p.id" :value="p.id" :label="p.name"
				/></el-select>
				<p class="muted">当前项目中自己的最近100条业务设计</p>
				<el-empty v-if="!state.tasks.length && !state.loading" description="暂无业务设计；可直接输入需求开始" :image-size="55" /><button
					v-for="task in state.tasks"
					:key="task.id"
					:class="{ selected: state.task?.id === task.id }"
					:aria-label="`选择业务设计 ${task.id}`"
					@click="selectTask(task.id)"
				>
					<strong>{{ task.title }}</strong
					><span>设计 #{{ task.id }} · 输入v{{ task.input_revision }}{{ task.busy_job_id ? ' · 生成中' : '' }}</span>
				</button>
			</aside>
			<main v-if="state.task" class="task-main">
				<div class="task-heading">
					<div>
						<h2>{{ state.task.title }}</h2>
						<p>
							设计 #{{ state.task.id }} · 输入v{{ state.task.input_revision }} · {{ scopeLabel(state.task.scope) }} · 资料包 #{{
								state.task.bundle_id
							}}
						</p>
					</div>
					<el-button :disabled="busy || submitting" @click="openTask(true)">更新需求与绑定</el-button>
				</div>
				<nav class="section-nav">
					<el-button v-for="link in pageLinks" :key="link.key" :type="section === link.key ? 'primary' : 'default'" @click="goPage(link.key)">{{
						link.label
					}}</el-button>
				</nav>
				<el-tabs v-model="stage" class="stage-tabs"
					><el-tab-pane v-for="key in stageKeys" :key="key" :name="key" :label="state.options.stages[key]?.title || key" :disabled="submitting"
				/></el-tabs>
				<p class="method-line">
					{{ definition?.skill }} · {{ prompt }} · {{ definition?.role === 'reviewer' ? 'Reviewer' : 'Writer' }}
					<span>设计产物不代表已经测试通过</span>
				</p>
				<el-alert
					v-if="busy"
					class="notice"
					type="info"
					:closable="false"
					show-icon
					:title="`正在处理阶段任务 #${state.task.busy_job_id}，生成后需要复核；可以切换页面，结果会保存。`"
				/>
				<el-alert v-if="blockers.length" class="notice" type="warning" :closable="false" :title="`本阶段尚不能开始：${blockers.join('；')}`" />
				<el-alert
					v-if="artifact && !artifact.fresh"
					class="notice"
					type="warning"
					:closable="false"
					title="此版与当前输入或上游不一致。保留原文与复核记录，但不能作为当前有效依据。请更新本阶段。"
				/>
				<section class="generation panel">
					<div class="settings">
						<el-form label-position="top"
							><el-form-item label="任务 Prompt"
								><el-select v-model="prompt" aria-label="本阶段任务Prompt" :disabled="busy || submitting"
									><el-option v-for="p in definition?.prompts || []" :key="p" :value="p" :label="promptLabel(p)" /></el-select></el-form-item
							><el-form-item v-if="['testpoints', 'cases'].includes(stage)" label="本批条数上限"
								><el-input-number v-model="maxItems" aria-label="本批条数上限" :min="1" :max="12" :disabled="busy || submitting" /></el-form-item
						></el-form>
					</div>
					<el-form label-position="top"
						><el-form-item label="本次范围或修订要求（可选）"
							><el-input
								v-model="instruction"
								aria-label="本次范围或修订要求"
								type="textarea"
								:rows="2"
								:maxlength="5000"
								:disabled="busy || submitting"
								placeholder="例如：仅设计串行确定路径，保留并发规则为待确认；或说明所选条目要修订什么。" /></el-form-item
						><el-form-item v-if="stage === 'cases'" label="展开哪些测试点"
							><el-select
								v-model="casePoints"
								aria-label="本批展开测试点"
								multiple
								collapse-tags
								:max-collapse-tags="3"
								:disabled="busy || submitting"
								><el-option
									v-for="point in state.task.heads.testpoints?.content.testpoints || []"
									:key="point.id"
									:value="point.id"
									:label="`${point.id} · ${point.title} · ${readinessLabel(point.design_readiness)}`" /></el-select></el-form-item
					></el-form>
					<div class="buttons">
						<el-button type="primary" :disabled="!canPrepare || !!pending" :loading="previewing" @click="previewStage(false)"
							>预览并生成本阶段</el-button
						><el-button
							v-if="['testpoints', 'cases'].includes(stage)"
							:disabled="!canPrepare || !head?.fresh || !selectedIds.length || !!pending"
							@click="previewStage(true)"
							>局部修订所选 {{ selectedIds.length }} 条</el-button
						><el-button :disabled="!canOperate || !!blockers.length" @click="openAdvanced">{{
							head ? '另存修订（高级）' : '人工录入本阶段'
						}}</el-button>
					</div>
					<p class="muted">调用前可查看材料、方法和模型；确认后会消耗所选模型额度。局部修订保留原编号和未选条目，历史版本不覆盖。</p>
				</section>
				<section v-if="artifact" class="panel artifact">
					<div class="artifact-heading">
						<div>
							<h3>
								{{ definition?.title }} · v{{ artifact.version }}
								<el-tag :type="artifact.content.readiness === 'ready' ? 'success' : 'warning'">{{
									readinessLabel(artifact.content.readiness)
								}}</el-tag>
							</h3>
							<p>
								{{ artifact.origin === 'manual' ? '人工修订' : '模型生成' }} · 输入v{{ artifact.input_revision }} · 产物 #{{ artifact.id
								}}{{ historical ? ' · 历史只读' : '' }}
							</p>
						</div>
						<el-select v-model="historyId" aria-label="阶段产物版本" @change="loadHistory"
							><el-option :value="0" label="当前版本" /><el-option
								v-for="item in state.task.history.filter((h:any)=>h.stage===stage)"
								:key="item.id"
								:value="item.id"
								:label="`v${item.version} · #${item.id} · ${item.origin === 'manual' ? '人工' : '模型'}`"
						/></el-select>
					</div>
					<p class="muted">
						上游版本：{{ parentLabel(artifact.parent_ids) }}；资料包 {{ artifact.provenance.bundle_version }}，{{ artifact.provenance.prompt_key }}。
					</p>
					<div v-if="artifact.confirmation" class="confirmation">
						<strong>本版已复核{{ artifact.fresh ? '' : '（历史记录）' }}</strong>
						<p>{{ artifact.confirmation.note }}</p>
					</div>
					<div v-else class="buttons">
						<el-button
							type="success"
							:disabled="!canOperate || !artifact.fresh || artifact.content.readiness === 'blocked'"
							@click="confirmVisible = true"
							>复核本版</el-button
						><span class="muted">生成完成后先核对来源、金额与待确认项，再用于下一阶段。</span>
					</div>
					<ArtifactView
						:content="artifact.content"
						:readonly="historical || busy || submitting || !artifact.fresh"
						@select="selectedIds = $event"
						@edit="openItem"
						@source="showSource"
					/>
					<el-collapse
						><el-collapse-item title="查看方法、来源摘要与编号变化" name="provenance">
							<pre>{{ JSON.stringify(artifact.provenance, null, 2) }}</pre>
						</el-collapse-item></el-collapse
					>
				</section>
				<el-empty v-else :description="state.loading ? '正在读取设计…' : '本阶段尚无产物。准备上游后，可预览生成或人工录入。'" />
				<section class="panel history">
					<h3>阶段调用记录</h3>
					<p class="muted">最近30次；失败不表示未计费，平台不会自动重放整个阶段。</p>
					<el-table :data="state.task.jobs" border size="small"
						><el-table-column prop="id" label="任务" width="80" /><el-table-column label="阶段" min-width="125"
							><template #default="{ row }">{{ state.options.stages[row.stage]?.title }} · {{ row.prompt_key }}</template></el-table-column
						><el-table-column label="状态" width="110"
							><template #default="{ row }">{{ jobLabel(row.status) }}</template></el-table-column
						><el-table-column label="结果 / 错误" min-width="230"
							><template #default="{ row }"
								>{{ row.error_message || `产物 #${row.artifact_id || '待生成'}`
								}}<span v-if="row.usage?.tokens"> · {{ row.usage.tokens.total_tokens }} tokens</span></template
							></el-table-column
						><el-table-column label="原始材料" width="110"
							><template #default="{ row }"><el-button link type="primary" @click="showJob(row.id)">查看记录</el-button></template></el-table-column
						></el-table
					>
				</section>
			</main>
			<main v-else class="empty-main">
				<el-empty :description="state.loading ? '正在读取项目…' : '选择业务设计，或新建一条需求。无需先录入接口。'" />
			</main>
		</div>
		<el-dialog
			v-model="taskVisible"
			:title="editingTask ? '更新需求与绑定（新输入版本）' : '新建业务设计'"
			width="min(900px,96vw)"
			destroy-on-close
			:close-on-click-modal="false"
			><el-form label-position="top"
				><el-form-item label="需求名称"><el-input v-model="form.title" aria-label="业务需求名称" :maxlength="180" /></el-form-item
				><el-form-item label="需求正文"
					><el-input v-model="form.requirement" aria-label="业务需求正文" type="textarea" :rows="7" :maxlength="24000" /></el-form-item
				><el-form-item label="背景、规则补充与本批边界"
					><el-input v-model="form.background" aria-label="业务背景与边界" type="textarea" :rows="4" :maxlength="16000"
				/></el-form-item>
				<div class="form-grid">
					<el-form-item label="适用范围"
						><el-select v-model="form.scope" aria-label="业务设计适用范围"
							><el-option label="公司项目设计（不执行）" value="project_design" /><el-option label="本地合成设计" value="local_synthetic" /><el-option
								label="外部参考设计"
								value="reference_design" /></el-select></el-form-item
					><el-form-item label="固定资料版本"
						><el-select v-model="form.bundle_id" aria-label="设计使用的资料版本"
							><el-option v-for="b in state.options.bundles" :key="b.id" :value="b.id" :label="`${b.version} · #${b.id}`" /></el-select></el-form-item
					><el-form-item label="Writer"
						><el-select v-model="form.writer_id" aria-label="业务设计Writer"
							><el-option
								v-for="m in state.options.models.filter((m:any)=>m.role==='writer')"
								:key="m.id"
								:value="m.id"
								:label="m.name" /></el-select></el-form-item
					><el-form-item label="Reviewer"
						><el-select v-model="form.reviewer_id" aria-label="业务设计Reviewer"
							><el-option
								v-for="m in state.options.models.filter((m:any)=>m.role==='reviewer')"
								:key="m.id"
								:value="m.id"
								:label="m.name" /></el-select
					></el-form-item>
				</div>
				<el-form-item label="附加专项方法（按需选择）"
					><el-checkbox-group v-model="form.specialist_keys"
						><el-checkbox value="cex-spot-matching">现货撮合</el-checkbox><el-checkbox value="cex-futures-risk">合约风险</el-checkbox
						><el-checkbox value="cex-funds-reconciliation">资金对账</el-checkbox></el-checkbox-group
					></el-form-item
				><el-form-item label="项目知识文档（可不选，先使用本次需求；来源会保存快照）"
					><el-select v-model="form.knowledge_document_ids" aria-label="设计知识文档" multiple filterable collapse-tags :max-collapse-tags="3"
						><el-option-group v-for="kb in state.options.knowledge" :key="kb.id" :label="kb.name"
							><el-option v-for="doc in kb.documents" :key="doc.id" :value="doc.id" :label="doc.title" /></el-option-group></el-select></el-form-item
				><el-form-item v-if="editingTask" label="更新原因（必填，至少5字）"
					><el-input v-model="inputNote" aria-label="更新需求原因" type="textarea" :rows="2" /></el-form-item
			></el-form>
			<p class="muted">保存不会调用模型。修改输入或资料绑定会使旧阶段产物待更新；原输入、产物与复核记录保留。</p>
			<template #footer
				><el-button @click="taskVisible = false">取消</el-button
				><el-button type="primary" :loading="submitting" @click="saveTask">保存业务设计</el-button></template
			></el-dialog
		>
		<el-dialog v-model="previewVisible" title="本阶段调用预览" width="min(1000px,96vw)" :close-on-click-modal="false"
			><template v-if="preview"
				><p>
					<strong>{{ definition?.title }} · {{ prompt }} · {{ preview.snapshot.model.name }} / {{ preview.snapshot.model.model }}</strong>
				</p>
				<p>上游版本：{{ parentLabel(preview.snapshot.parent_ids) }}；{{ preview.snapshot.methods.skills.map((s: any) => s.title).join('、') }}。</p>
				<el-alert
					type="warning"
					:closable="false"
					title="确认后会把本任务需求、选中文档、相关上游产物及所选方法发送给已配置模型，并消耗其额度。不会执行交易或接口请求。"
				/><el-table :data="preview.snapshot.methods.files" size="small"
					><el-table-column prop="path" label="实际加载的方法文件" min-width="260" /><el-table-column
						prop="sha256"
						label="原文摘要"
						min-width="220"
						show-overflow-tooltip /></el-table
				><el-collapse
					><el-collapse-item title="查看本次完整方法与业务输入" name="payload">
						<pre>{{ JSON.stringify(preview.snapshot, null, 2) }}</pre>
					</el-collapse-item></el-collapse
				>
				<p class="digest">输入摘要 {{ preview.input_hash }}</p></template
			><template #footer
				><el-button @click="previewVisible = false">返回</el-button
				><el-button type="primary" :loading="submitting" @click="submitStage">确认调用模型</el-button></template
			></el-dialog
		>
		<el-dialog v-model="confirmVisible" title="复核当前业务设计版本" width="min(680px,94vw)"
			><p>请核对原始资料与计算口径。此操作仅表示允许基于本版继续设计，不是发版批准或测试通过。</p>
			<el-input
				v-model="confirmNote"
				aria-label="设计复核说明"
				type="textarea"
				:rows="4"
				placeholder="记录本次核对范围、来源、仍待确认的分支及不采纳意见的依据，至少5字。"
			/><el-checkbox v-if="head?.content.readiness === 'partial'" v-model="acceptPartial">仅继续有依据的部分，保留待确认分支</el-checkbox
			><el-checkbox
				v-if="['revise','blocked'].includes(head?.content.decision)||head?.content.issues?.some((i:any)=>i.severity==='blocking')"
				v-model="overrideIssues"
				>有依据地不采纳修订或阻塞意见（说明至少15字）</el-checkbox
			><template #footer
				><el-button @click="confirmVisible = false">返回</el-button
				><el-button type="primary" :loading="submitting" @click="confirmCurrent">保存复核记录</el-button></template
			></el-dialog
		>
		<el-dialog v-model="advancedVisible" title="人工另存阶段产物" width="min(1000px,96vw)" :close-on-click-modal="false"
			><p>结构化业务设计，不是可执行脚本。保存会校验编号和来源；新版本需要重新复核。首次人工录入请按下方字段规范补齐结构。</p>
			<el-collapse
				><el-collapse-item title="查看本阶段字段规范" name="schema">
					<pre>{{ JSON.stringify(state.options.output_schemas?.[stage], null, 2) }}</pre>
				</el-collapse-item></el-collapse
			><el-input v-model="advancedJson" aria-label="阶段产物JSON" type="textarea" :rows="20" spellcheck="false" /><el-input
				v-model="editNote"
				class="edit-note"
				aria-label="人工修订说明"
				type="textarea"
				:rows="2"
				placeholder="修订说明（至少5字）"
			/><template #footer
				><el-button @click="advancedVisible = false">取消</el-button
				><el-button type="primary" :loading="submitting" @click="saveAdvanced">另存人工版本</el-button></template
			></el-dialog
		>
		<el-dialog v-model="itemVisible" :title="`修订 ${item?.row.id || ''}`" width="min(850px,96vw)" :close-on-click-modal="false"
			><template v-if="item"
				><el-form label-position="top"
					><el-form-item label="业务标题"><el-input v-model="item.row.title" /></el-form-item
					><el-form-item v-for="field in itemFields" :key="field.key" :label="field.label"
						><el-input v-model="item.text[field.key]" type="textarea" :rows="field.rows || 3"
					/></el-form-item>
					<div v-if="item.kind === 'cases'" class="step-editor">
						<div v-for="(step, index) in item.row.steps" :key="index">
							<h3>步骤 {{ Number(index) + 1 }}</h3>
							<el-form-item label="动作"><el-input v-model="step.action" type="textarea" :rows="2" /></el-form-item
							><el-form-item label="对应预期"><el-input v-model="step.expected" type="textarea" :rows="2" /></el-form-item
							><el-form-item label="观察位置"><el-input v-model="step.observation" type="textarea" :rows="2" /></el-form-item
							><el-button :disabled="item.row.steps.length === 1" @click="item.row.steps.splice(index, 1)">移除此步骤</el-button>
						</div>
						<el-button :disabled="item.row.steps.length >= 12" @click="item.row.steps.push({ action: '', expected: '', observation: '' })"
							>增加步骤</el-button
						>
					</div>
					<div class="form-grid">
						<el-form-item label="设计就绪度"
							><el-select v-model="item.row.design_readiness"
								><el-option v-for="s in ['ready', 'partial', 'blocked']" :key="s" :value="s" :label="readinessLabel(s)" /></el-select></el-form-item
						><el-form-item label="执行准备"
							><el-select v-model="item.row.execution_readiness"
								><el-option
									v-for="s in ['known_available', 'needs_preparation', 'capability_unknown']"
									:key="s"
									:value="s"
									:label="preparationLabel(s)" /></el-select
						></el-form-item>
					</div>
					<el-form-item label="修订说明（至少5字）"><el-input v-model="editNote" type="textarea" :rows="2" /></el-form-item></el-form></template
			><template #footer
				><el-button @click="itemVisible = false">取消</el-button
				><el-button type="primary" :loading="submitting" @click="saveItem">另存本版修订</el-button></template
			></el-dialog
		>
		<el-dialog v-model="sourceVisible" title="本版引用的原始资料" width="min(950px,96vw)"
			><template v-if="source"
				><h3>{{ source.title }}</h3>
				<p>{{ source.kind }} · {{ source.source_id }} · {{ source.sha256 }}</p>
				<pre>{{ source.content }}</pre>
			</template></el-dialog
		>
		<el-dialog v-model="jobVisible" title="阶段任务与原始材料" width="min(1100px,96vw)"
			><template v-if="jobDetail"
				><el-alert v-if="jobDetail.error_message" :title="jobDetail.error_message" type="warning" :closable="false" /><el-button
					v-if="jobDetail.candidate && canOperate"
					@click="adoptCandidate"
					>以候选稿人工修订</el-button
				>
				<pre>{{ JSON.stringify(jobDetail, null, 2) }}</pre>
			</template></el-dialog
		>
	</div>
</template>
<script setup lang="ts" name="Web3DesignPanel">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { useProjectApi } from '/@/api/v1/projects/project';
import { useUserStore } from '/@/stores/user';
import ArtifactView from './ArtifactView.vue';
import { designApi } from './design-api';
import {
	createDesignController,
	initialDesignState,
	errorText,
	readinessLabel,
	preparationLabel,
	requestUncertain,
	assertDesignExport,
} from './design-state';
import { readContext, saveContext } from './context';
const props = defineProps<{ section: 'requirements' | 'testpoints' | 'cases' }>(),
	route = useRoute(),
	router = useRouter(),
	user = useUserStore();
const state = reactive(initialDesignState()),
	controller = createDesignController(state, designApi),
	projects = ref<{ id: string; name: string }[]>([]),
	project = ref('');
const stage = ref('analysis'),
	prompt = ref('P01'),
	instruction = ref(''),
	maxItems = ref(8),
	selectedIds = ref<string[]>([]),
	casePoints = ref<string[]>([]),
	localError = ref(''),
	submitting = ref(false),
	previewing = ref(false);
const previewVisible = ref(false),
	preview = ref<any>(null),
	preparedRequest = ref<any>(null),
	pending = ref<any>(null),
	historyId = ref(0),
	historicalArtifact = ref<any>(null);
const taskVisible = ref(false),
	editingTask = ref(false),
	inputNote = ref(''),
	createKey = ref(''),
	form = reactive<any>({});
const confirmVisible = ref(false),
	confirmNote = ref(''),
	acceptPartial = ref(false),
	overrideIssues = ref(false),
	advancedVisible = ref(false),
	advancedJson = ref(''),
	editNote = ref(''),
	itemVisible = ref(false),
	item = ref<any>(null);
const sourceVisible = ref(false),
	source = ref<any>(null),
	jobVisible = ref(false),
	jobDetail = ref<any>(null);
let alive = true,
	timer: ReturnType<typeof setTimeout> | undefined,
	historyEpoch = 0,
	sourceEpoch = 0,
	jobEpoch = 0;
const pageLinks = [
	{ key: 'requirements', label: '需求与建模' },
	{ key: 'testpoints', label: '测试点设计' },
	{ key: 'cases', label: '用例与评审' },
];
const pageTitle = computed(() => pageLinks.find((p) => p.key === props.section)!.label);
const stageKeys = computed(() =>
	props.section === 'requirements'
		? ['analysis', 'requirement_review', 'modeling', 'spot', 'futures', 'funds']
		: props.section === 'testpoints'
		? ['testpoints', 'testpoint_review']
		: ['cases', 'case_review', 'regression']
);
const definition = computed(() => state.options.stages[stage.value]),
	head = computed(() => state.task?.heads[stage.value]),
	artifact = computed(() => (historyId.value ? historicalArtifact.value : head.value)),
	historical = computed(() => !!historyId.value && historyId.value !== head.value?.id);
const busy = computed(() => !!state.task?.busy_job_id),
	blockers = computed(() => state.task?.stage_states[stage.value]?.blockers || []),
	canOperate = computed(() => !!state.task && !busy.value && !submitting.value && !historical.value),
	canPrepare = computed(() => canOperate.value && !blockers.value.length);
const scopeLabel = (s: string) =>
	(({ local_synthetic: '本地合成设计', project_design: '公司项目设计', reference_design: '外部参考设计' } as any)[s] || s);
const jobLabel = (s: string) =>
	(({ queued: '等待处理', running: '生成中', succeeded: '产物已生成', failed: '生成失败', interrupted: '已中断' } as any)[s] || s);
const promptLabel = (s: string) =>
	((
		{
			P01: 'P01 需求分析',
			P02: 'P02 需求评审',
			P03: 'P03 业务链路建模',
			P04: 'P04 规则与状态建模',
			P05: 'P05 测试点生成',
			P06: 'P06 增量补充',
			P07: 'P07 测试点评审',
			P08: 'P08 详细用例',
			P09: 'P09 用例评审',
			P10: 'P10 现货专项',
			P11: 'P11 合约专项',
			P12: 'P12 资金专项',
			P13: 'P13 变更影响',
			P14: 'P14 回归选择',
		} as any
	)[s] || s);
function context() {
	return {
		...readContext(user.userInfos.id, { project: state.project }),
		project: state.project,
		...(state.task ? { design: String(state.task.id) } : {}),
	};
}
function sync() {
	if (!alive || !state.project) return;
	const ctx = context();
	saveContext(user.userInfos.id, ctx);
	void router.replace({ query: { ...ctx, view: 'business', stage: stage.value } });
}
function goPage(page: string) {
	sync();
	void router.push({ path: '/web3/' + page, query: { ...context(), view: 'business' } });
}
function parentLabel(parents: any) {
	return (
		Object.entries(parents || {})
			.map(([s, id]) => {
				const version = state.task?.history.find((h: any) => h.id === id)?.version;
				return `${state.options.stages[s]?.title || s} v${version || '?'} #${id}`;
			})
			.join('；') || '本次原始资料'
	);
}
function pendingKey(p = state.project) {
	return `leon.web3.design.pending.v1.${user.userInfos.id}.${p}`;
}
function loadPending() {
	try {
		const value = JSON.parse(sessionStorage.getItem(pendingKey()) || 'null');
		pending.value = value && String(value.project) === state.project && typeof value.body?.request_key === 'string' ? value : null;
	} catch {
		pending.value = null;
	}
}
function clearPending(p: string, key: string) {
	try {
		const value = JSON.parse(sessionStorage.getItem(pendingKey(p)) || 'null');
		if (value?.body?.request_key === key) sessionStorage.removeItem(pendingKey(p));
	} catch {}
	if (alive && p === state.project) loadPending();
}
async function changeProject() {
	localError.value = '';
	historyId.value = 0;
	historicalArtifact.value = null;
	previewVisible.value = false;
	sourceVisible.value = false;
	jobVisible.value = false;
	const ctx = readContext(user.userInfos.id, {
		project: project.value,
		...(String(route.query.project) === project.value ? { design: route.query.design } : {}),
	});
	await controller.project(project.value, ctx.design);
	if (alive) {
		loadPending();
		sync();
	}
}
async function refreshTask() {
	localError.value = '';
	await controller.refresh();
	sync();
}
async function selectTask(id: number) {
	if (submitting.value) return;
	historyId.value = 0;
	historicalArtifact.value = null;
	localError.value = '';
	await controller.select(id);
	sync();
}
watch(
	() => [state.task?.id, stage.value],
	() => {
		historyEpoch++;
		historyId.value = 0;
		historicalArtifact.value = null;
		selectedIds.value = [];
		instruction.value = '';
		confirmNote.value = '';
		acceptPartial.value = false;
		overrideIssues.value = false;
		previewVisible.value = false;
		prompt.value = definition.value?.prompts[0] || '';
		casePoints.value = (state.task?.heads.testpoints?.content.testpoints || [])
			.filter((p: any) => p.design_readiness === 'ready')
			.map((p: any) => p.id);
		sync();
	}
);
watch(
	() => head.value?.id,
	() => {
		selectedIds.value = [];
	}
);
function openTask(edit: boolean) {
	editingTask.value = edit;
	inputNote.value = '';
	createKey.value = crypto.randomUUID();
	const t = state.task;
	Object.assign(
		form,
		edit
			? Object.fromEntries(
					['title', 'requirement', 'background', 'scope', 'bundle_id', 'writer_id', 'reviewer_id', 'specialist_keys', 'knowledge_document_ids'].map(
						(k) => [k, JSON.parse(JSON.stringify(t[k]))]
					)
			  )
			: {
					title: '',
					requirement: '',
					background: '',
					scope: 'project_design',
					bundle_id: state.options.bundles[0]?.id,
					writer_id: state.options.models.find((m: any) => m.role === 'writer')?.id,
					reviewer_id: state.options.models.find((m: any) => m.role === 'reviewer')?.id,
					specialist_keys: [],
					knowledge_document_ids: [],
			  }
	);
	taskVisible.value = true;
}
async function saveTask() {
	submitting.value = true;
	localError.value = '';
	try {
		const result = editingTask.value
			? await designApi.update(state.task.id, { ...form, expected_revision: state.task.revision, note: inputNote.value })
			: await designApi.create({ ...form, project_id: Number(state.project), request_key: createKey.value });
		if (!alive) return;
		taskVisible.value = false;
		await controller.project(state.project, String(result.id));
		sync();
	} catch (e) {
		if (alive) {
			localError.value = errorText(e);
			ElMessage.error(localError.value);
		}
	} finally {
		if (alive) submitting.value = false;
	}
}
async function previewStage(partial: boolean) {
	if (!state.task) return;
	localError.value = '';
	previewing.value = true;
	const id = state.task.id,
		requestedStage = stage.value;
	const body = {
		expected_revision: state.task.revision,
		request_key: crypto.randomUUID(),
		stage: stage.value,
		prompt_key: prompt.value,
		instruction: instruction.value,
		item_ids: partial ? selectedIds.value : [],
		case_testpoint_ids: stage.value === 'cases' ? casePoints.value : [],
		max_items: maxItems.value,
	};
	try {
		const result = await designApi.preview(id, body);
		if (!alive || state.task?.id !== id || stage.value !== requestedStage) return;
		preview.value = result;
		preparedRequest.value = { ...body, preview_hash: result.input_hash };
		previewVisible.value = true;
	} catch (e) {
		if (alive) localError.value = errorText(e);
	} finally {
		if (alive) previewing.value = false;
	}
}
async function sendStage(value: any) {
	submitting.value = true;
	localError.value = '';
	try {
		await designApi.generate(value.task_id, value.body);
		clearPending(value.project, value.body.request_key);
		if (alive) {
			previewVisible.value = false;
			if (state.task?.id !== value.task_id) await controller.select(value.task_id);
			await controller.refresh();
			sync();
		}
	} catch (e) {
		if (!requestUncertain(e)) clearPending(value.project, value.body.request_key);
		if (alive) localError.value = errorText(e);
	} finally {
		if (alive) submitting.value = false;
	}
}
async function submitStage() {
	if (!preparedRequest.value || !state.task) return;
	const value = { project: state.project, task_id: state.task.id, body: JSON.parse(JSON.stringify(preparedRequest.value)) };
	try {
		sessionStorage.setItem(pendingKey(), JSON.stringify(value));
	} catch {
		localError.value = '浏览器无法保存本次请求号，请恢复会话存储后重试；本次尚未提交模型任务。';
		return;
	}
	pending.value = value;
	await sendStage(value);
}
async function retryPending() {
	if (pending.value) await sendStage(pending.value);
}
async function confirmCurrent() {
	if (!head.value) return;
	submitting.value = true;
	try {
		const result = await designApi.confirm(state.task.id, {
			expected_revision: state.task.revision,
			artifact_id: head.value.id,
			note: confirmNote.value,
			accept_partial: acceptPartial.value,
			override_review_issues: overrideIssues.value,
		});
		if (alive) {
			controller.accept(result);
			confirmVisible.value = false;
			confirmNote.value = '';
			acceptPartial.value = false;
			overrideIssues.value = false;
		}
	} catch (e) {
		if (alive) {
			localError.value = errorText(e);
			ElMessage.error(localError.value);
		}
	} finally {
		if (alive) submitting.value = false;
	}
}
async function loadHistory() {
	const epoch = ++historyEpoch,
		id = state.task?.id;
	historicalArtifact.value = null;
	if (!historyId.value || !id) return;
	try {
		const result = await designApi.artifact(id, historyId.value);
		if (alive && epoch === historyEpoch && id === state.task?.id) historicalArtifact.value = result;
	} catch (e) {
		if (alive && epoch === historyEpoch) localError.value = errorText(e);
	}
}
function openAdvanced() {
	editNote.value = '';
	advancedJson.value = JSON.stringify(head.value?.content || { summary: '', readiness: 'partial', notes: [], questions: [] }, null, 2);
	advancedVisible.value = true;
}
async function saveAdvanced() {
	submitting.value = true;
	try {
		const result = await designApi.manual(state.task.id, {
			expected_revision: state.task.revision,
			stage: stage.value,
			prompt_key: prompt.value,
			content: JSON.parse(advancedJson.value),
			note: editNote.value,
		});
		if (alive) {
			controller.accept(result);
			advancedVisible.value = false;
			historyId.value = 0;
		}
	} catch (e) {
		if (alive) {
			localError.value = errorText(e);
			ElMessage.error(localError.value);
		}
	} finally {
		if (alive) submitting.value = false;
	}
}
const itemFields = computed(() =>
	item.value?.kind === 'testpoints'
		? [
				{ key: 'conditions', label: '前提与初态（一行一项）' },
				{ key: 'trigger', label: '触发动作' },
				{ key: 'expected', label: '明确预期' },
				{ key: 'verification', label: '独立核对方法' },
				{ key: 'unresolved', label: '待确认部分（一行一项）' },
		  ]
		: [
				{ key: 'preconditions', label: '前置条件（一行一项）' },
				{ key: 'data', label: '测试数据（一行一项）' },
				{ key: 'expected_result', label: '整体判据' },
				{ key: 'cleanup', label: '收尾（一行一项）' },
				{ key: 'unresolved', label: '待确认部分（一行一项）' },
		  ]
);
function openItem(value: any) {
	const row = JSON.parse(JSON.stringify(value.row));
	item.value = { kind: value.kind, row, text: {} };
	for (const [key, value] of Object.entries(row))
		if (typeof value === 'string' || (Array.isArray(value) && value.every((v) => typeof v === 'string')))
			item.value.text[key] = Array.isArray(value) ? value.join('\n') : value;
	editNote.value = '';
	itemVisible.value = true;
}
async function saveItem() {
	if (!item.value || !head.value) return;
	const row = item.value.row;
	for (const field of itemFields.value) {
		const old = row[field.key];
		row[field.key] = Array.isArray(old)
			? item.value.text[field.key]
					.split('\n')
					.map((s: string) => s.trim())
					.filter(Boolean)
			: item.value.text[field.key];
	}
	const content = JSON.parse(JSON.stringify(head.value.content));
	content[item.value.kind] = content[item.value.kind].map((r: any) => (r.id === row.id ? row : r));
	const readiness = content[item.value.kind].map((r: any) => r.design_readiness);
	content.readiness =
		readiness.every((s: string) => s === 'ready') && !content.questions?.length
			? 'ready'
			: readiness.every((s: string) => s === 'blocked')
			? 'blocked'
			: 'partial';
	submitting.value = true;
	try {
		const result = await designApi.revise(state.task.id, {
			expected_revision: state.task.revision,
			artifact_id: head.value.id,
			content,
			note: editNote.value,
		});
		if (alive) {
			controller.accept(result);
			itemVisible.value = false;
			historyId.value = 0;
		}
	} catch (e) {
		if (alive) {
			localError.value = errorText(e);
			ElMessage.error(localError.value);
		}
	} finally {
		if (alive) submitting.value = false;
	}
}
async function showSource(sourceId: string) {
	if (!artifact.value) return;
	const epoch = ++sourceEpoch,
		id = state.task.id,
		artifactId = artifact.value.id,
		version = artifact.value.input_revision;
	try {
		const historicalSource = artifact.value.provenance?.historical_sources?.find((s: any) => s.source_id === sourceId);
		const result = historicalSource ? null : await designApi.input(id, version);
		if (!alive || epoch !== sourceEpoch || state.task?.id !== id || artifact.value?.id !== artifactId) return;
		source.value = historicalSource || result.sources.find((s: any) => s.source_id === sourceId);
		if (!source.value) throw new Error('本输入版本没有此来源');
		sourceVisible.value = true;
	} catch (e) {
		if (alive && epoch === sourceEpoch && state.task?.id === id) localError.value = errorText(e);
	}
}
async function showJob(id: number) {
	const taskId = state.task.id,
		epoch = ++jobEpoch;
	try {
		const result = await designApi.job(taskId, id);
		if (alive && state.task?.id === taskId && epoch === jobEpoch) {
			jobDetail.value = result;
			jobVisible.value = true;
		}
	} catch (e) {
		if (alive && state.task?.id === taskId && epoch === jobEpoch) localError.value = errorText(e);
	}
}
async function adoptCandidate() {
	if (!jobDetail.value?.candidate) return;
	const candidate = jobDetail.value;
	stage.value = candidate.stage;
	await nextTick();
	prompt.value = candidate.prompt_key;
	advancedJson.value = JSON.stringify(candidate.candidate, null, 2);
	editNote.value = '';
	jobVisible.value = false;
	advancedVisible.value = true;
}
async function exportTask() {
	try {
		const taskId = state.task.id;
		const data = assertDesignExport(await designApi.export(taskId), taskId);
		const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
		const a = document.createElement('a');
		a.href = url;
		a.download = `web3-design-${state.task.id}.json`;
		a.click();
		setTimeout(() => URL.revokeObjectURL(url), 1000);
	} catch (e) {
		localError.value = errorText(e);
	}
}
async function poll() {
	if (state.task?.busy_job_id) await controller.refresh();
	if (alive) timer = setTimeout(poll, state.error ? 8000 : 1800);
}
onMounted(async () => {
	try {
		const response: any = await useProjectApi().getList({ page: 1, page_size: 100 });
		if (!alive) return;
		projects.value = (response.data.items || response.data.rows || []).map((p: any) => ({ id: String(p.id), name: p.name }));
		const ctx = readContext(user.userInfos.id, route.query);
		project.value = projects.value.find((p) => p.id === ctx.project)?.id || projects.value[0]?.id || '';
		stage.value = stageKeys.value.includes(String(route.query.stage)) ? String(route.query.stage) : stageKeys.value[0];
		if (project.value) {
			await controller.project(project.value, ctx.design);
			loadPending();
			sync();
		}
		if (alive) timer = setTimeout(poll, 1800);
	} catch (e) {
		if (alive) localError.value = errorText(e);
	}
});
onUnmounted(() => {
	alive = false;
	++historyEpoch;
	++sourceEpoch;
	if (timer) clearTimeout(timer);
	controller.dispose();
});
</script>
<style scoped lang="scss">
.design-page {
	padding: 24px;
	min-width: 0;
	color: var(--el-text-color-primary);
	font-size: 15px;
}
header,
.task-heading,
.artifact-heading {
	display: flex;
	gap: 18px;
	justify-content: space-between;
	align-items: flex-start;
	flex-wrap: wrap;
	margin-bottom: 20px;
}
h1 {
	font-size: 24px;
	margin: 0 0 8px;
}
h2 {
	font-size: 20px;
	margin: 0;
}
h3 {
	font-size: 17px;
	margin: 0 0 14px;
}
p {
	line-height: 1.8;
}
header p,
.task-heading p,
.artifact-heading p,
.muted {
	font-size: 14px;
	color: var(--el-text-color-secondary);
}
header p {
	margin: 0;
}
.buttons,
.section-nav {
	display: flex;
	gap: 10px;
	flex-wrap: wrap;
	align-items: center;
}
.buttons .el-button,
.section-nav .el-button {
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
	background: var(--el-bg-color);
	min-height: 600px;
	overflow: hidden;
}
.task-list {
	padding: 18px;
	border-right: 1px solid var(--el-border-color-lighter);
}
.task-list > button {
	width: 100%;
	text-align: left;
	color: inherit;
	font: inherit;
	background: transparent;
	border: 1px solid transparent;
	border-radius: 8px;
	padding: 14px 12px;
	cursor: pointer;
	margin: 7px 0;
}
.task-list > button strong {
	font-size: 14px;
	line-height: 1.7;
}
.task-list > button span {
	display: block;
	font-size: 13px;
	color: var(--el-text-color-secondary);
	margin-top: 7px;
}
.task-list > button.selected {
	border-color: var(--el-color-primary-light-7);
	background: var(--el-color-primary-light-9);
}
.task-main {
	padding: 22px;
	min-width: 0;
}
.section-nav {
	margin: 16px 0;
}
.method-line {
	font-size: 14px;
	overflow-wrap: anywhere;
}
.method-line span {
	display: block;
	color: var(--el-text-color-secondary);
	margin-top: 6px;
}
.panel {
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 10px;
	padding: 20px;
	margin: 18px 0;
	min-width: 0;
}
.settings .el-form,
.form-grid {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 0 20px;
}
.settings .el-form {
	max-width: 600px;
}
.el-select {
	width: 100%;
}
.artifact-heading > .el-select {
	max-width: 260px;
}
.confirmation {
	padding: 14px 18px;
	background: var(--el-fill-color-light);
	border-radius: 8px;
	font-size: 14px;
}
.confirmation p {
	margin: 6px 0;
	white-space: pre-wrap;
}
pre {
	font: 14px/1.8 ui-monospace, monospace;
	white-space: pre-wrap;
	overflow-wrap: anywhere;
	max-height: 65vh;
	overflow: auto;
	padding: 18px;
	border-radius: 8px;
	background: var(--el-fill-color-light);
}
.digest {
	font: 13px/1.8 monospace;
	overflow-wrap: anywhere;
	color: var(--el-text-color-secondary);
}
.edit-note {
	margin-top: 18px;
}
.step-editor > div {
	border-top: 1px solid var(--el-border-color-lighter);
	padding: 18px 0;
}
.empty-main {
	padding: 60px 20px;
}
@media (max-width: 1000px) {
	.workspace {
		grid-template-columns: 1fr;
	}
	.task-list {
		border-right: 0;
		border-bottom: 1px solid var(--el-border-color-lighter);
	}
	.task-list > button {
		max-width: 300px;
		display: inline-block;
		vertical-align: top;
	}
	.task-main {
		padding: 16px;
	}
	.design-page {
		padding: 16px;
	}
}
@media (max-width: 620px) {
	.settings .el-form,
	.form-grid {
		grid-template-columns: 1fr;
	}
	.panel {
		padding: 14px;
	}
	.task-list > button {
		max-width: 100%;
	}
}
</style>
