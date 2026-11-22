import type { Dataset, Environment, LabApi, LabRequest, Operation } from './model';
import { errorMessage } from '../qa-runner/model';
export function initialLabState() {
  return { project: '', environments: [] as Environment[], datasets: [] as Dataset[], operations: [] as Operation[],
    worker: 'offline', selectedEnvironment: '', selectedDataset: '', pending: null as LabRequest | null,
    submitting: false, loading: false, error: '', notice: '' };
}
export function createLabController(state: ReturnType<typeof initialLabState>, api: LabApi,
  storage: { read(project: string): LabRequest | null; write(project: string, body: LabRequest | null): void },
  key = () => 'lab_' + crypto.randomUUID().replaceAll('-', '')) {
  let epoch = 0, reading = -1, disposed = false;
  const current = (p: number) => !disposed && p === epoch;
  function selections() {
    if (!state.environments.some(e => e.id === state.selectedEnvironment)) state.selectedEnvironment = state.environments[0]?.id || '';
    if (!state.datasets.some(d => d.id === state.selectedDataset && d.environment_id === state.selectedEnvironment))
      state.selectedDataset = state.datasets.find(d => d.environment_id === state.selectedEnvironment)?.id || '';
  }
  async function refresh() {
    const p = epoch;
    if (disposed || !state.project || reading === p) return;
    reading = p; state.loading = true;
    try {
      const view = await api.state(state.project);
      if (!current(p)) return;
      state.environments = view.environments; state.datasets = view.datasets; state.operations = view.operations; state.worker = view.worker.status; state.error = '';
      if (state.pending) {
        const known = view.operations.find(o => o.request_key === state.pending?.request_key);
        if (known) {
          state.pending = null; storage.write(state.project, null); state.selectedEnvironment = known.environment_id;
          if (known.dataset_id) state.selectedDataset = known.dataset_id;
          state.notice = '已确认原操作记录，没有重复创建或重建';
        }
      }
      selections();
    } catch (error) {
      if (current(p)) {
        state.error = errorMessage(error);
        const status = (error as { response?: { status: number } }).response?.status;
        if ([401, 403, 404].includes(status || 0)) { state.environments = []; state.datasets = []; state.operations = []; selections(); }
      }
    } finally { if (current(p)) state.loading = false; if (reading === p) reading = -1; }
  }
  async function project(id: string) {
    epoch++; state.project = id; state.environments = []; state.datasets = []; state.operations = []; state.selectedEnvironment = ''; state.selectedDataset = ''; state.error = ''; state.notice = '';
    try { state.pending = storage.read(id); } catch { state.pending = null; }
    await refresh();
  }
  async function submit(fields?: Omit<LabRequest, 'project_id' | 'request_key'>) {
    if (state.submitting || !state.project) return;
    const p = epoch, project = state.project; state.submitting = true; state.error = ''; state.notice = '';
    try {
      if (!state.pending) {
        if (!fields) return;
        const id = Number(project); if (!Number.isSafeInteger(id) || id <= 0) throw new Error('项目编号不正确');
        const body: LabRequest = { project_id: id, request_key: key(), ...fields };
        storage.write(project, body); state.pending = body;
      }
      const result = await api.submit({ ...state.pending });
      try { storage.write(project, null); } catch { /* Replaying the original key stays idempotent. */ }
      if (!current(p)) return;
      state.pending = null; state.selectedEnvironment = result.operation.environment_id;
      if (result.operation.dataset_id) state.selectedDataset = result.operation.dataset_id;
      state.operations = [result.operation, ...state.operations.filter(o => o.id !== result.operation.id)];
      state.notice = result.duplicate ? '已找到原操作，不重复执行' : '操作已登记，结果会自动更新';
      await refresh();
    } catch (error) {
      if (current(p)) {
        const status = (error as { response?: { status: number } }).response?.status;
        if (status && status >= 400 && status < 500) { state.pending = null; try { storage.write(project, null); } catch {} }
        state.error = errorMessage(error) + (state.pending ? '。结果待确认，已保留原请求标识；请刷新或按原请求重试。' : '');
      }
    } finally { state.submitting = false; }
  }
  return { refresh, project, submit, selections, dispose: () => { disposed = true; epoch++; } };
}
