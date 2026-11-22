export interface Environment {
  id: string; status: string; session_id: string; creation_date: string; source_sha256?: string;
  cleanup_status: string; error_message?: string;
}
export interface Transfer { dataset_id: string; user_id: string; request_id: string; from: string; to: string; amount_minor: string; status: string; reason?: string }
export interface Ledger { id: number; user_id: string; request_id: string; kind: string; asset: string; delta_minor: string; balance_after_minor: string }
export interface Snapshot { dataset_id: string; accounts: { user_id: string; kind: string; asset: string; balance_minor: string }[]; transfers: Transfer[]; ledger: Ledger[] }
export interface Dataset {
  id: string; environment_id: string; name: string; funding: string; spot: string; status: string;
  revision: number; generation: number; native_id: string | null; snapshot: Snapshot | null; error_message?:string;
  history: { generation: number; native_id: string; snapshot: Snapshot | null; reason: string; operation_id: string; at: string }[];
}
export type LabAction = 'start' | 'stop' | 'create' | 'inspect' | 'rebuild' | 'delete' | 'transfer' | 'query' | 'verify';
export interface LabRequest { project_id: number; action: LabAction; request_key: string;
  environment_id?: string; dataset_id?: string; expected_revision?: number; name?: string; funding?: string; spot?: string;
  test_user?: 'alice'|'bob'; business_request_id?: string; from_account?: 'funding'|'spot'; to_account?: 'funding'|'spot'; amount?: string;
  expected_funding?: string; expected_spot?: string; expected_status?: 'SUCCEEDED'|'REJECTED'; requirement_ref?: string; case_ref?: string; review_note?: string }
export interface Operation { id: string; environment_id: string; dataset_id: string | null; action: LabAction;
  status: string; request_key: string; creation_date: string; inputs: LabRequest; error_message?: string; result?: unknown }
export interface LabView { environments: Environment[]; datasets: Dataset[]; operations: Operation[]; worker: { status: string }; limits: { manual_environments: number; per_project_user: number } }
export interface LabApi { state(project: string): Promise<LabView>; submit(body: LabRequest): Promise<{ operation: Operation; duplicate: boolean }> }
export const labStatus = (status: string) => ({ queued: '排队中', starting: '启动中', running: '运行中', stopping: '停止中', stopped: '已停止',
  interrupted: '已中断', error: '异常', creating: '准备中', ready: '已就绪', inspecting: '读取中', rebuilding: '重建中', deleting: '清理中',
  deleted: '已清理', unavailable: '环境已关闭', completed: '已完成', debugging:'调试中' }[status] || status);
export const actionLabel = (action: string) => ({ start: '启动环境', stop: '停止环境', create: '创建数据集', inspect: '读取快照', rebuild: '按初值重建', delete: '清理数据集',transfer:'发起划转',query:'按原号查询',verify:'业务断言' }[action] || action);
export function validSeed(value: string) {
  if (!/^[0-9]{1,8}(\.[0-9]{1,8})?$/.test(value)) return false;
  const [whole, fraction = ''] = value.split('.');
  return BigInt(whole) * 100000000n + BigInt(fraction.padEnd(8, '0')) <= 1000000000000000n;
}
export function minorAmount(value: string) {
  if (!/^-?[0-9]+$/.test(value)) return '—';
  const n = BigInt(value), abs = n < 0 ? -n : n;
  return `${n < 0 ? '-' : ''}${abs / 100000000n}.${(abs % 100000000n).toString().padStart(8, '0')}`;
}
