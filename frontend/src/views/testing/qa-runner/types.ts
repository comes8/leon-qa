export type Verdict = 'PASS' | 'FAIL' | 'ENV_ERROR' | 'NO_TESTS';
export type RunKind = 'regression' | 'selftest';
export type JobStatus = 'queued' | 'running' | 'cancelling' | 'completed' | 'cancelled' | 'timed_out' | 'interrupted';
export type LogStream = 'stderr' | 'stdout' | 'supervisor';
export interface Suite {
  suite_id: string; name: string; suite_version: string; profile: string;
  required_tests: string[]; supported_run_kinds: RunKind[]; selftest_target: string;
}
export interface Catalog {
  catalog: { suites: Suite[] } | null;
  worker: { status: string; active_job_id?: string | null; heartbeat_age_seconds?: number; last_error?: string | null };
}
export interface CaseSummary {
  case_id: string; status: 'PASS' | 'FAIL'; evidence_file: string; assertions_passed: number; assertions_failed: number;
}
export interface RunReport {
  schema_version: string; run_id: string; suite_id: string; suite_version: string; run_kind: RunKind;
  status: Verdict; reason: string; profile: string; cases: CaseSummary[]; artifacts: string[];
  source: { commit: string; dirty: boolean; sha256: string };
  gate_result: { status: Verdict; passed: string[]; failed: string[]; missing_mandatory: string[] };
  selftest?: { mutation_detected: boolean; mutation: string; evidence_rules: string[] };
}
export interface Job {
  id: string; run_id: string; project_id: string; request_key: string; suite_id: string; suite_version: string;
  run_kind: RunKind; timeout_seconds: number; status: JobStatus; result_status: Verdict | null;
  cleanup_status: string; creation_date: string; started_at: string | null; finished_at: string | null;
  error_message: string | null; process_exit_code: number | null; result: RunReport | null;
}
export interface CreateJob {
  project_id: number; project_key: 'leon-qa-kit'; suite_id: string; run_kind: RunKind;
  request_key: string; timeout_seconds: number;
}
export interface RunnerEvent { seq: number; level: string; code: string; message: string; at: string }
export interface LogPage { text: string; next_offset: number; size_bytes: number; complete: boolean }
export interface CaseBundle {
  document_type: 'leon.qa.case'; run_id: string; case_id: string; status: 'PASS' | 'FAIL';
  dataset_id: string; before: unknown; after: unknown; http_events: unknown[]; service_logs: string[];
  assertions: { id: string; rule_id: string; label: string; subject: string; operator: string;
    expected: unknown; actual: unknown; status: 'PASS' | 'FAIL'; unit?: string }[];
}
export interface RunnerApi {
  catalog(): Promise<Catalog>;
  jobs(project: string): Promise<Job[]>;
  job(id: string): Promise<Job>;
  submit(body: CreateJob): Promise<{ job: Job; duplicate: boolean }>;
  cancel(id: string): Promise<Job>;
  events(id: string, after: number): Promise<{ items: RunnerEvent[]; next_after: number }>;
  logs(id: string, stream: LogStream, offset: number): Promise<LogPage>;
  artifact(id: string, relative: string): Promise<Blob>;
}
