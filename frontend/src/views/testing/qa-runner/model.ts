import type { Job, JobStatus } from './types';

export const terminal = (status: JobStatus) => ['completed', 'cancelled', 'timed_out', 'interrupted'].includes(status);
export const canCancel = (job: Job) => ['queued', 'running'].includes(job.status);
export const lifecycleLabel = (status: string) => ({ queued: '排队中', running: '执行中', cancelling: '取消处理中',
  completed: '已结束', cancelled: '已取消', timed_out: '已超时', interrupted: '已中断' }[status] || status);
export const workerLabel = (status: string) => ({ idle: '空闲待命', running: '正在执行', offline: '离线',
  starting: '启动中', blocked: '需处理异常', not_configured: '未配置' }[status] || status);
export function verdictLabel(job: Job) {
  if (!job.result_status) return terminal(job.status) ? '无有效测试结论' : '等待结果';
  if (job.run_kind === 'selftest' && job.result_status === 'PASS') return '自检通过 · 已检出缺陷';
  return ({ PASS: '回归通过', FAIL: '测试失败', ENV_ERROR: '环境或报告异常', NO_TESTS: '未执行有效用例' })[job.result_status];
}
export const verdictTone = (job: Job): 'success' | 'danger' | 'warning' | 'info' =>
  job.result_status === 'PASS' ? 'success' : job.result_status === 'FAIL' ? 'danger' : job.result_status ? 'warning' : 'info';
export const cleanupLabel = (value: string) => ({ clean: '已清理', not_required: '无需清理', failed: '清理失败',
  pending: '待核对', not_started: '未启动' }[value] || value);
export const caseLabel = (id: string) => ({ TestTransferNormal: '正常划转', TestReverseTransfer: '反向划转',
  TestInsufficientBalance: '余额不足', TestInvalidAmounts: '非法金额与边界', TestSequentialDuplicate: '顺序重复请求',
  TestChangedPayload: '同请求号变更参数', TestConcurrentDuplicate: '并发重复请求', TestConcurrentNoOverspend: '并发防透支',
  TestRollbackAtomicity: '事务回滚原子性', TestTimeoutAfterCommit: '提交超时后查原请求', TestCrossUserRejected: '跨用户隔离',
  TestDatasetLifecycle: '测试数据生命周期', TestMinimumUnit: '最小金额单位', TestBidirectionalConcurrency: '双向并发划转' }[id] || id);
export const displayValue = (value: unknown) => typeof value === 'string' ? value : JSON.stringify(value, null, 2) ?? '—';
export const formatTime = (value?: string | null) => value && Number.isFinite(Date.parse(value)) ?
  new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(value)) : '—';
export function errorMessage(error: unknown) {
  const e = error as { message?: unknown; response?: { data?: { detail?: unknown } } };
  const message = e.response?.data?.detail || e.message || '请求失败，请检查本地后端连接';
  return typeof message === 'string' ? message : JSON.stringify(message);
}
