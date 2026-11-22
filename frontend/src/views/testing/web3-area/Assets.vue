<template>
	<div class="assets-page">
		<header>
			<div>
				<h1>知识与技能</h1>
				<p>项目业务规则、业务方法与任务 Prompt 分开维护，按版本查看原文</p>
			</div>
			<el-select v-model="project" aria-label="业务资产所属项目" :disabled="syncing" @change="changeProject"
				><el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id"
			/></el-select>
		</header>
		<el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
		<el-alert
			:title="bundle ? '第二批：业务设计已支持按阶段选择本资料包的 Skill / Prompt。具体使用版本、来源和模型调用记录保存在设计任务中；原接口资产继续使用 v1 流程。' : '此项目的个人业务资料尚未导入或正在加载。业务方法与项目知识分开保存；浏览资料不会调用模型。'"
			type="info"
			:closable="false"
			show-icon
		/>
		<div class="summary">
			<div>
				<strong>{{ bundle?.counts.skills || 0 }}</strong
				><span>业务 Skill</span>
			</div>
			<div>
				<strong>{{ bundle?.counts.prompts || 0 }}</strong
				><span>任务 Prompt</span>
			</div>
			<div>
				<strong>{{ bundle?.counts.references || 0 }}</strong
				><span>参考文档</span>
			</div>
			<div>
				<strong>{{ knowledge.length }}</strong
				><span>项目知识库</span>
			</div>
		</div>
		<div class="version-row">
			<div>
				<span>资料版本</span
				><el-select v-model="bundleId" aria-label="业务资料版本" :disabled="loading || syncing" @change="loadBundle"
					><el-option v-for="b in bundles" :key="b.id" :value="b.id" :label="`${b.version} · ${formatTime(b.imported_at)}`"
				/></el-select>
			</div>
			<el-button :disabled="!bundle || loading || syncing" :loading="checking" @click="checkSource">检查源目录更新</el-button>
		</div>
		<el-tabs v-model="tab" @tab-change="clearFile">
			<el-tab-pane label="项目知识库" name="knowledge" />
			<el-tab-pane :label="`业务 Skills (${bundle?.skills.length || 0})`" name="skills" />
			<el-tab-pane :label="`任务 Prompts (${bundle?.prompts.length || 0})`" name="prompts" />
			<el-tab-pane label="版本与来源" name="versions" />
		</el-tabs>
		<div v-if="tab === 'versions'" class="versions panel">
			<h2>只读版本快照</h2>
			<p>登记来源：{{ bundle?.source_root || '此项目尚未导入业务资料' }}</p>
			<p>原目录不随网页编辑；同步时新建版本，旧快照继续保留。评估样例留在原目录，不作为项目规则导入。</p>
			<el-table :data="bundles" border
				><el-table-column prop="version" label="版本" width="150" /><el-table-column label="导入时间" min-width="170"
					><template #default="{ row }">{{ formatTime(row.imported_at) }}</template></el-table-column
				><el-table-column label="内容" min-width="220"
					><template #default="{ row }"
						>{{ row.counts.skills }}个Skill · {{ row.counts.prompts }}份Prompt · {{ row.counts.references }}份参考</template
					></el-table-column
				><el-table-column label="状态" min-width="170"><template #default>设计阶段可选 · 以任务绑定为准</template></el-table-column></el-table
			>
			<p class="digest">完整清单摘要：{{ bundle?.manifest_sha256 || '未导入' }}</p>
		</div>
		<div v-else class="library">
			<aside class="panel catalog">
				<el-input v-model="search" aria-label="搜索业务资料" placeholder="搜索名称、阶段或内容描述" clearable />
				<template v-if="tab === 'knowledge'"
					><p class="muted">这里展示当前项目已有规则。文档是否已获业务确认，以原文和项目记录为准。</p>
					<div v-for="kb in visibleKnowledge" :key="kb.id" class="kb-group">
						<h3>{{ kb.name }}</h3>
						<p>{{ kb.description }}</p>
						<button v-for="doc in kb.documents" :key="doc.id" :class="{ selected: fileKey === `knowledge-${doc.id}` }" @click="openKnowledge(doc)">
							<strong>{{ doc.title }}</strong
							><span>{{ doc.characters }}字 · {{ doc.status }}</span>
						</button>
					</div>
					<el-empty v-if="!visibleKnowledge.length && !loading" :description="search ? '没有匹配的知识文档' : '当前项目暂无知识库'" /><el-button
						@click="router.push({ path: '/ai/knowledge', query: { project } })"
						>管理项目知识库</el-button
					></template
				>
				<template v-else
					><p class="muted">{{ tab === 'skills' ? '文档式业务方法，不调用命令或执行交易' : '任务输入模板；可填写变量并复制预览，当前不调用模型' }}</p>
					<button v-for="asset in visibleAssets" :key="asset.key" :class="{ selected: currentAsset?.key === asset.key }" @click="openAsset(asset)">
						<div class="asset-title">
							<strong>{{ asset.title }}</strong
							><el-tag size="small" effect="plain">{{ asset.stage }}</el-tag>
						</div>
						<span>{{ asset.key }}</span>
						<p v-if="asset.description">{{ asset.description }}</p></button
					><el-empty v-if="!visibleAssets.length && !loading" description="没有匹配资料；可换项目或清空搜索"
				/></template>
			</aside>
			<main class="panel reader" :aria-busy="fileLoading">
				<template v-if="content"
					><div class="reader-heading">
						<div>
							<h2>{{ fileTitle }}</h2>
							<p>{{ filePath }}</p>
						</div>
						<el-button @click="copyContent">{{ previewing ? '复制预览' : '复制原文' }}</el-button>
					</div>
					<p v-if="fileHash" class="digest">SHA256 {{ fileHash }}</p>
					<template v-if="tab === 'skills' && currentAsset"
						><div class="refs">
							<span>配套Prompt：</span
							><el-button v-for="key in currentAsset.prompt_ids" :key="key" size="small" @click="goPrompt(key)">{{ key }}</el-button>
						</div>
						<div class="refs">
							<el-button
								v-for="path in currentAsset.references"
								:key="path"
								size="small"
								:type="filePath === path ? 'primary' : 'default'"
								@click="readFile(path)"
								>{{ path.split('/').pop() }}</el-button
							><el-button v-if="filePath !== currentAsset.path" size="small" @click="readFile(currentAsset.path)">返回 Skill 正文</el-button>
						</div></template
					>
					<template v-if="tab === 'prompts' && currentAsset"
						><el-collapse
							><el-collapse-item title="填写本次任务变量（仅在浏览器预览）" name="inputs"
								><el-form label-position="top"
									><el-form-item v-for="variable in currentAsset.variables" :key="variable" :label="variable"
										><el-input v-model="inputs[variable]" type="textarea" :rows="2" /></el-form-item></el-form
								><el-switch v-model="previewing" aria-label="预览填入后的 Prompt" active-text="显示填入后的 Prompt" inactive-text="显示原文" /></el-collapse-item></el-collapse
					></template>
					<pre class="document" aria-label="业务资料原文">{{ displayContent }}</pre></template
				><el-empty v-else :description="fileLoading ? '正在读取版本原文…' : '从左侧选择一份资料查看原文与引用'" />
			</main>
		</div>
		<el-dialog v-model="previewVisible" title="检查源目录更新" width="min(720px,94vw)"
			><template v-if="sourcePreview"
				><p>当前最新导入版本 #{{ sourcePreview.baseline_id }}；源目录版本 {{ sourcePreview.version }}。</p>
				<el-alert v-if="!sourcePreview.changed" title="内容一致，无需重复导入。" type="success" :closable="false" /><template v-else
					><p>下面仅展示清单差异，尚未写入。同步后会保留旧版本。</p>
					<div v-for="(label, key) in diffLabels" :key="key">
						<h3>{{ label }} {{ sourcePreview.changes[key].length }}份</h3>
						<ul>
							<li v-for="path in sourcePreview.changes[key]" :key="path">{{ path }}</li>
						</ul>
					</div></template
				></template
			><template #footer
				><el-button @click="previewVisible = false">关闭</el-button
				><el-button v-if="sourcePreview?.changed" type="primary" :loading="syncing" @click="syncSource">确认导入新版本</el-button></template
			></el-dialog
		>
	</div>
</template>
<script setup lang="ts" name="Web3BusinessAssets">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import request from '/@/utils/request';
import { useProjectApi } from '/@/api/v1/projects/project';
import { useUserStore } from '/@/stores/user';
import { readContext, saveContext, renderPrompt } from './context';
const api = '/v1/Ntesterc_web3/workspace',
	route = useRoute(),
	router = useRouter(),
	user = useUserStore();
const project = ref(''),
	projects = ref<{ id: string; name: string }[]>([]),
	bundles = ref<any[]>([]),
	bundleId = ref<number>(),
	bundle = ref<any>(null),
	knowledge = ref<any[]>([]);
const tab = ref('skills'),
	search = ref(''),
	error = ref(''),
	loading = ref(false),
	fileLoading = ref(false),
	checking = ref(false),
	syncing = ref(false);
const content = ref(''),
	fileTitle = ref(''),
	filePath = ref(''),
	fileHash = ref(''),
	fileKey = ref(''),
	currentAsset = ref<any>(null),
	inputs = reactive<Record<string, string>>({}),
	previewing = ref(false);
const previewVisible = ref(false),
	sourcePreview = ref<any>(null),
	diffLabels = { added: '新增', modified: '修改', removed: '移除' };
let projectEpoch = 0,
	fileEpoch = 0,
	bundleEpoch = 0,
	alive = true;
const formatTime = (value: string) => (value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '未导入');
const visibleKnowledge = computed(() => {const q=search.value.trim().toLowerCase();return knowledge.value.map(kb=>{const all=`${kb.name} ${kb.description||''}`.toLowerCase().includes(q);return {...kb,documents:kb.documents.filter((d:any)=>all||d.title.toLowerCase().includes(q))}}).filter(kb=>!q||kb.documents.length)});
const visibleAssets = computed(() => {
	const rows = bundle.value?.[tab.value === 'prompts' ? 'prompts' : 'skills'] || [];
	const q = search.value.trim().toLowerCase();
	return rows.filter((a: any) => !q || `${a.title} ${a.key} ${a.stage} ${a.description || ''}`.toLowerCase().includes(q));
});
const displayContent = computed(() => (previewing.value ? renderPrompt(content.value, inputs) : content.value));
const fail = (e: any) => e?.response?.data?.detail || e.message || '资料读取失败';
function clearFile() {
	fileEpoch++;
	content.value = '';
	fileTitle.value = '';
	filePath.value = '';
	fileHash.value = '';
	fileKey.value = '';
	currentAsset.value = null;
	fileLoading.value = false;
	previewing.value = false;
	for (const key of Object.keys(inputs)) delete inputs[key];
}
async function changeProject() {
	const epoch = ++projectEpoch;
	bundleEpoch++;
	clearFile();
	bundle.value = null;
	bundles.value = [];
	knowledge.value = [];
	bundleId.value = undefined;
	error.value = '';
	sourcePreview.value = null;
	previewVisible.value = false;
	loading.value = true;
	checking.value = false;
	const ctx = readContext(user.userInfos.id, { project: project.value });
	saveContext(user.userInfos.id, ctx);
	void router.replace({ query: { ...ctx } });
	try {
		const results = (await Promise.all([
			request({ url: api + '/assets', params: { project_id: project.value } }),
			request({ url: api + '/knowledge', params: { project_id: project.value } }),
		])) as any[];
		if (!alive || epoch !== projectEpoch) return;
		bundles.value = results[0].data;
		knowledge.value = results[1].data;
		bundleId.value = bundles.value[0]?.id;
		await loadBundle();
	} catch (e) {
		if (alive && epoch === projectEpoch) error.value = fail(e);
	} finally {
		if (alive && epoch === projectEpoch) loading.value = false;
	}
}
async function loadBundle() {
	const epoch = ++bundleEpoch,
		p = projectEpoch;
	clearFile();
	bundle.value = null;
	if (!bundleId.value) return;
	try {
		const r: any = await request({ url: `${api}/assets/${bundleId.value}`, params: { project_id: project.value } });
		if (alive && epoch === bundleEpoch && p === projectEpoch) bundle.value = r.data;
	} catch (e) {
		if (alive && epoch === bundleEpoch && p === projectEpoch) error.value = fail(e);
	}
}
async function readFile(path: string) {
	const epoch = ++fileEpoch,
		p = projectEpoch,
		b = bundleId.value;
	content.value = '';
	fileLoading.value = true;
	try {
		const r: any = await request({ url: `${api}/assets/${b}/file`, params: { project_id: project.value, path } });
		if (!alive || epoch !== fileEpoch || p !== projectEpoch || b !== bundleId.value) return;
		content.value = r.data.content;
		filePath.value = r.data.path;
		fileHash.value = r.data.sha256;
		fileTitle.value = currentAsset.value?.title || path;
		fileKey.value = path;
	} catch (e) {
		if (alive && epoch === fileEpoch) error.value = fail(e);
	} finally {
		if (alive && epoch === fileEpoch) fileLoading.value = false;
	}
}
async function openAsset(asset: any) {
	clearFile();
	currentAsset.value = asset;
	await readFile(asset.path);
}
async function goPrompt(key: string) {
	tab.value = 'prompts';
	search.value = '';
	await nextTick();
	const asset = bundle.value?.prompts.find((p: any) => p.key === key);
	if (asset) await openAsset(asset);
}
async function openKnowledge(doc: any) {
	clearFile();
	const epoch = ++fileEpoch,
		p = projectEpoch;
	fileLoading.value = true;
	try {
		const r: any = await request({ url: `${api}/knowledge/${doc.id}`, params: { project_id: project.value } });
		if (!alive || epoch !== fileEpoch || p !== projectEpoch) return;
		content.value = r.data.content;
		fileTitle.value = doc.title;
		filePath.value = `项目文档 #${doc.id}`;
		fileHash.value = r.data.truncated ? '' : doc.sha256;
		fileKey.value = `knowledge-${doc.id}`;
		if (r.data.truncated) ElMessage.warning('文档超过预览上限，请到知识库查看完整内容');
	} catch (e) {
		if (alive && epoch === fileEpoch) error.value = fail(e);
	} finally {
		if (alive && epoch === fileEpoch) fileLoading.value = false;
	}
}
async function copyContent() {
	try {
		await navigator.clipboard.writeText(displayContent.value);
		ElMessage.success('已复制');
	} catch {
		ElMessage.warning('复制失败，请选中文本复制');
	}
}
async function checkSource() {
	const p = projectEpoch;
	checking.value = true;
	error.value = '';
	try {
		const r: any = await request({ url: api + '/source-preview', params: { project_id: project.value } });
		if (alive && p === projectEpoch) {
			sourcePreview.value = r.data;
			previewVisible.value = true;
		}
	} catch (e) {
		if (alive && p === projectEpoch) error.value = fail(e);
	} finally {
		if (alive && p === projectEpoch) checking.value = false;
	}
}
async function syncSource() {
	if (!sourcePreview.value) return;
	syncing.value = true;
	try {
		await request({
			url: api + '/sync',
			method: 'POST',
			data: { project_id: Number(project.value), baseline_id: sourcePreview.value.baseline_id, manifest_sha256: sourcePreview.value.manifest_sha256 },
		});
		previewVisible.value = false;
		await changeProject();
		ElMessage.success('新版本已导入，旧版本保留');
	} catch (e) {
		error.value = fail(e);
	} finally {
		syncing.value = false;
	}
}
onMounted(async () => {
	try {
		const r: any = await useProjectApi().getList({ page: 1, page_size: 100 });
		if (!alive) return;
		projects.value = (r.data.items || r.data.rows || []).map((p: any) => ({ id: String(p.id), name: p.name }));
		const ctx = readContext(user.userInfos.id, route.query);
		project.value = projects.value.find((p) => p.id === ctx.project)?.id || projects.value[0]?.id || '';
		if (project.value) await changeProject();
	} catch (e) {
		if (alive) error.value = fail(e);
	}
});
onUnmounted(() => {
	alive = false;
	projectEpoch++;
	fileEpoch++;
	bundleEpoch++;
});
</script>
<style scoped lang="scss">
.assets-page {
	padding: 24px;
	min-width: 0;
	color: var(--el-text-color-primary);
	font-size: 16px;
}
.assets-page header {
	display: flex;
	justify-content: space-between;
	align-items: center;
	gap: 16px;
	flex-wrap: wrap;
	margin-bottom: 20px;
}
h1 {
	font-size: 24px;
	margin: 0 0 8px;
}
h2 {
	font-size: 18px;
	margin: 0;
}
h3 {
	font-size: 16px;
}
p {
	line-height: 1.75;
}
header p,
.muted {
	color: var(--el-text-color-secondary);
	font-size: 14px;
}
.el-alert {
	margin-bottom: 14px;
}
.summary {
	display: grid;
	grid-template-columns: repeat(4, 1fr);
	gap: 14px;
	margin: 22px 0;
}
.summary > div {
	background: var(--el-bg-color);
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 10px;
	padding: 18px;
}
.summary strong {
	display: block;
	font-size: 26px;
}
.summary span {
	display: block;
	color: var(--el-text-color-secondary);
	font-size: 14px;
	margin-top: 6px;
}
.version-row,
.version-row > div {
	display: flex;
	align-items: center;
	gap: 12px;
	flex-wrap: wrap;
}
.version-row {
	justify-content: space-between;
	margin-bottom: 18px;
	font-size: 14px;
}
.version-row .el-select {
	width: 320px;
}
header .el-select {
	width: 260px;
}
.library {
	display: grid;
	grid-template-columns: minmax(270px, 340px) minmax(0, 1fr);
	gap: 18px;
	min-height: 540px;
}
.panel {
	background: var(--el-bg-color);
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 10px;
	padding: 20px;
	min-width: 0;
}
.catalog {
	max-height: 76vh;
	overflow: auto;
}
.catalog button:not(.el-button) {
	display: block;
	text-align: left;
	width: 100%;
	background: transparent;
	color: inherit;
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 8px;
	padding: 14px;
	margin: 12px 0;
	cursor: pointer;
	font: inherit;
}
.catalog button.selected {
	background: var(--el-color-primary-light-9);
	border-color: var(--el-color-primary);
}
.catalog button strong {
	font-size: 15px;
	line-height: 1.7;
}
.catalog button span,
.catalog button p {
	font-size: 14px;
	color: var(--el-text-color-secondary);
	display: block;
	margin: 7px 0 0;
	line-height: 1.65;
}
.asset-title {
	display: flex;
	flex-wrap: wrap;
	align-items: center;
	gap: 7px;
}
.reader-heading {
	display: flex;
	justify-content: space-between;
	gap: 16px;
	align-items: flex-start;
	flex-wrap: wrap;
}
.reader-heading p,
.digest {
	font-family: monospace;
	overflow-wrap: anywhere;
	font-size: 13px;
	color: var(--el-text-color-secondary);
}
.document {
	white-space: pre-wrap;
	overflow-wrap: anywhere;
	font: 14px/1.9 ui-monospace, monospace;
	background: var(--el-fill-color-light);
	border-radius: 8px;
	padding: 20px;
	max-height: 70vh;
	overflow: auto;
}
.refs {
	display: flex;
	flex-wrap: wrap;
	gap: 8px;
	margin: 16px 0;
	font-size: 14px;
}
.refs .el-button {
	margin: 0;
	max-width: 100%;
	height: auto;
	min-height: 30px;
	white-space: normal;
}
.kb-group {
	border-bottom: 1px solid var(--el-border-color-lighter);
	padding: 8px 0 16px;
}
.kb-group p {
	font-size: 14px;
	color: var(--el-text-color-secondary);
}
.versions {
	font-size: 14px;
}
@media (max-width: 960px) {
	.library {
		grid-template-columns: 1fr;
	}
	.catalog {
		max-height: 380px;
	}
	.summary {
		grid-template-columns: repeat(2, 1fr);
	}
	.assets-page {
		padding: 16px;
	}
	.version-row .el-select {
		max-width: 100%;
		width: 260px;
	}
	.document {
		max-height: 65vh;
		padding: 14px;
	}
}
</style>
