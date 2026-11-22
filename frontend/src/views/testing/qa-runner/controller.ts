import type { Catalog, CaseBundle, CreateJob, Job, LogStream, RunnerApi, RunnerEvent, RunKind } from './types';
import { errorMessage, terminal } from './model';

export interface PendingStore { read(project: string): CreateJob | null; write(project: string, body: CreateJob | null): void }
export function initialState() {
  return {
    projectId: '', catalog: null as Catalog | null, jobs: [] as Job[], job: null as Job | null, selectedId: '',
    loading: false, submitting: false, cancelling: false, error: '', pollError: '', submitError: '', notice: '',
    pending: null as CreateJob | null, events: [] as RunnerEvent[], eventCursor: 0,
    stream: 'stderr' as LogStream, logText: '', logOffset: 0, logSize: 0, logComplete: false, logTrimmed: false,
    selectedCase: '', caseBundle: null as CaseBundle | null, caseLoading: false, caseError: '',
  };
}
export type RunnerState = ReturnType<typeof initialState>;

export function createRunnerController(state: RunnerState, api: RunnerApi, pendingStore: PendingStore,
  key = () => 'web_' + crypto.randomUUID().replaceAll('-', '')) {
  let projectEpoch = 0, selectionEpoch = 0, caseEpoch = 0, logEpoch = 0, refreshEpoch = -1, progressKey = '', disposed = false;
  const valid = (p: number, s?: number) => !disposed && p === projectEpoch && (s === undefined || s === selectionEpoch);
  function clearDetail() {
    selectionEpoch++; caseEpoch++; logEpoch++;
    state.job = null; state.selectedId = ''; state.events = []; state.eventCursor = 0;
    state.logText = ''; state.logOffset = 0; state.logSize = 0; state.logComplete = false; state.logTrimmed = false;
    state.selectedCase = ''; state.caseBundle = null; state.caseLoading = false; state.caseError = '';
  }
  function forgetPending() {
    state.pending = null;
    try { pendingStore.write(state.projectId, null); } catch { /* Replaying the same persisted key remains idempotent. */ }
  }
  async function selectCase(id: string) {
    const job = state.job, entry = job?.result?.cases.find(c => c.case_id === id);
    if (!job || !entry) return;
    const p = projectEpoch, s = selectionEpoch, c = ++caseEpoch;
    state.selectedCase = id; state.caseBundle = null; state.caseError = ''; state.caseLoading = true;
    try {
      const bundle: CaseBundle = JSON.parse(await (await api.artifact(job.id, entry.evidence_file)).text());
      if (!valid(p, s) || c !== caseEpoch) return;
      if (bundle.document_type !== 'leon.qa.case' || bundle.run_id !== job.run_id || bundle.case_id !== id) throw new Error('证据身份与所选运行不一致');
      state.caseBundle = bundle;
    } catch (error) { if (valid(p, s) && c === caseEpoch) state.caseError = errorMessage(error); }
    finally { if (valid(p, s) && c === caseEpoch) state.caseLoading = false; }
  }
  function acceptJob(job: Job) {
    if (String(job.project_id) !== state.projectId) throw new Error('任务不属于当前项目，请重新选择运行记录');
    state.job = job;
    if (job.result?.cases.length && !state.selectedCase) void selectCase(job.result.cases[0].case_id);
  }
  async function progress() {
    if (!state.job) return;
    const p = projectEpoch, s = selectionEpoch, l = logEpoch, id = state.job.id, stream = state.stream, offset = state.logOffset;
    const reading = `${s}_${l}`;
    if (progressKey === reading) return;
    progressKey = reading;
    try {
      const [events, log] = await Promise.all([
        api.events(id, state.eventCursor),
        state.logComplete && terminal(state.job.status) ? Promise.resolve(null) : api.logs(id, stream, offset),
      ]);
      if (!valid(p, s)) return;
      state.events.push(...events.items.filter(e => e.seq > state.eventCursor)); state.eventCursor = Math.max(state.eventCursor, events.next_after);
      if (log && l === logEpoch && stream === state.stream && offset === state.logOffset) {
        state.logText += log.text;
        if (state.logText.length > 300000) { state.logText = state.logText.slice(-300000); state.logTrimmed = true; }
        state.logOffset = log.next_offset; state.logSize = log.size_bytes; state.logComplete = log.complete;
      }
    } catch (error) { if (valid(p, s)) state.pollError = errorMessage(error); }
    finally { if (progressKey === reading) progressKey = ''; }
  }
  async function selectJob(id: string) {
    clearDetail(); state.selectedId = id;
    const p = projectEpoch, s = selectionEpoch;
    try {
      const job = await api.job(id);
      if (!valid(p, s)) return;
      acceptJob(job); state.error = ''; await progress();
    } catch (error) { if (valid(p, s)) { clearDetail(); state.error = errorMessage(error); } }
  }
  async function refresh() {
    const p = projectEpoch, project = state.projectId;
    if (disposed || refreshEpoch === p) return;
    refreshEpoch = p; state.loading = true;
    try {
      const [catalog, jobs] = await Promise.all([api.catalog(), project ? api.jobs(project) : Promise.resolve([])]);
      if (!valid(p)) return;
      state.catalog = catalog; state.jobs = jobs; state.pollError = ''; state.error = '';
      if (state.pending) {
        const pending = state.pending;
        const confirmed = jobs.find(j => j.request_key === pending.request_key && j.suite_id === pending.suite_id
          && j.run_kind === pending.run_kind && j.timeout_seconds === pending.timeout_seconds);
        if (confirmed) { forgetPending(); state.submitError = ''; state.notice = '已从历史记录确认上次提交，未重复创建任务'; if (!state.selectedId) await selectJob(confirmed.id); }
      }
      if (!valid(p)) return;
      if (state.selectedId) {
        const s = selectionEpoch, id = state.selectedId;
        const job = jobs.find(j => j.id === id) || await api.job(id);
        if (valid(p, s)) { acceptJob(job); await progress(); }
      }
    } catch (error) {
      if (valid(p)) {
        const status = (error as { response?: { status: number } }).response?.status;
        if (status === 403 || status === 404 || status === 401) { state.jobs = []; clearDetail(); }
        state.pollError = errorMessage(error);
      }
    } finally { if (valid(p)) state.loading = false; if (refreshEpoch === p) refreshEpoch = -1; }
  }
  async function setProject(project: string, preferred = '') {
    projectEpoch++; clearDetail(); state.projectId = project; state.jobs = []; state.error = ''; state.pollError = ''; state.submitError = ''; state.notice = '';
    try { state.pending = pendingStore.read(project); } catch { state.pending = null; }
    const p = projectEpoch;
    await refresh();
    if (!valid(p)) return;
    if (preferred && /^[a-f0-9]{32}$/.test(preferred)) await selectJob(preferred);
    else if (!state.selectedId && state.jobs.length) await selectJob(state.jobs[0].id);
  }
  async function submit(form: { suite_id: string; run_kind: RunKind; timeout_seconds: number }) {
    if (state.submitting || !state.projectId) return;
    const p = projectEpoch, project = state.projectId;
    state.submitting = true; state.submitError = ''; state.notice = '';
    try {
      if (!state.pending) {
        const projectId = Number(project);
        if (!Number.isSafeInteger(projectId) || projectId <= 0) throw new Error('项目编号超出安全范围，请检查项目配置');
        if (!Number.isInteger(form.timeout_seconds) || form.timeout_seconds < 1 || form.timeout_seconds > 900) throw new Error('执行超时必须为 1–900 秒的整数');
        const body: CreateJob = { project_id: projectId, project_key: 'leon-qa-kit', ...form, request_key: key() };
        pendingStore.write(project, body); state.pending = body;
      }
      const body = { ...state.pending };
      const result = await api.submit(body);
      // Storage is scoped to the original project even if navigation changed mid-request.
      try { pendingStore.write(project, null); } catch { /* A future replay returns this same job. */ }
      if (!valid(p)) return;
      state.pending = null; state.notice = result.duplicate ? '已找到原任务，没有重复执行' : '任务已提交，每次运行保留独立记录';
      state.jobs = [result.job, ...state.jobs.filter(j => j.id !== result.job.id)];
      await selectJob(result.job.id);
    } catch (error) {
      if (valid(p)) state.submitError = errorMessage(error) + (state.pending ? '。请求标识已保留；请刷新确认或按原请求重试。' : '');
    } finally { state.submitting = false; }
  }
  async function cancel() {
    const job = state.job;
    if (!job || state.cancelling) return;
    const p = projectEpoch, s = selectionEpoch; state.cancelling = true;
    try { const result = await api.cancel(job.id); if (valid(p, s)) { acceptJob(result); await progress(); } }
    catch (error) { if (valid(p, s)) state.error = errorMessage(error); }
    finally { state.cancelling = false; }
  }
  async function setStream(stream: LogStream) {
    state.stream = stream; state.logText = ''; state.logOffset = 0; state.logSize = 0; state.logComplete = false; state.logTrimmed = false;
    logEpoch++; await progress();
  }
  return { refresh, setProject, selectJob, selectCase, submit, cancel, progress, setStream,
    dispose: () => { disposed = true; projectEpoch++; selectionEpoch++; caseEpoch++; } };
}
