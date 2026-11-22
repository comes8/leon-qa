import test from 'node:test';
import assert from 'node:assert/strict';
import { createRunnerController, initialState } from '../src/views/testing/qa-runner/controller';
import { displayValue, lifecycleLabel, verdictLabel } from '../src/views/testing/qa-runner/model';
import type { CreateJob, Job, RunnerApi } from '../src/views/testing/qa-runner/types';

const idA = 'a'.repeat(32), idB = 'b'.repeat(32);
function job(id = idA, project = '1', extra: Partial<Job> = {}): Job {
  return { id, run_id: 'job_' + id, project_id: project, request_key: 'request_' + id,
    suite_id: 'funds-transfer-v1', suite_version: '1.0.0', run_kind: 'regression', timeout_seconds: 300,
    status: 'queued', result_status: null, cleanup_status: 'not_started', creation_date: '2026-11-21T00:00:00Z',
    started_at: null, finished_at: null, error_message: null, process_exit_code: null, result: null, ...extra };
}
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; }
const tick = () => new Promise(resolve => setImmediate(resolve));
const form = { suite_id: 'funds-transfer-v1', run_kind: 'regression' as const, timeout_seconds: 300 };
function fixture(overrides: Partial<RunnerApi> = {}) {
  const state = initialState(), persisted = new Map<string, CreateJob>();
  const api: RunnerApi = {
    catalog: async () => ({ catalog: { suites: [] }, worker: { status: 'idle' } }), jobs: async () => [], job: async id => job(id),
    submit: async body => ({ job: job(idA, String(body.project_id), { request_key: body.request_key }), duplicate: false }),
    cancel: async id => job(id, '1', { status: 'cancelled' }),
    events: async () => ({ items: [], next_after: 0 }), logs: async () => ({ text: '', next_offset: 0, size_bytes: 0, complete: false }),
    artifact: async () => new Blob(['{}']), ...overrides,
  };
  let keys = 0;
  const storage = { read: (project: string) => persisted.get(project) || null,
    write: (project: string, body: CreateJob | null) => { if (body) persisted.set(project, structuredClone(body)); else persisted.delete(project); } };
  const controller = createRunnerController(state, api, storage, () => 'request_' + ++keys);
  return { state, api, controller, storage, persisted };
}

test('completed and cancelled do not imply a passing verdict', () => {
  assert.equal(lifecycleLabel('completed'), '已结束');
  assert.equal(verdictLabel(job(idA, '1', { status: 'completed' })), '无有效测试结论');
  assert.notEqual(verdictLabel(job(idA, '1', { status: 'cancelled' })), '回归通过');
  assert.equal(verdictLabel(job(idA, '1', { status: 'completed', result_status: 'NO_TESTS' })), '未执行有效用例');
});
test('selftest success is explicitly different from regression success', () => {
  assert.equal(verdictLabel(job(idA, '1', { result_status: 'PASS', run_kind: 'selftest' })), '自检通过 · 已检出缺陷');
  assert.equal(verdictLabel(job(idA, '1', { result_status: 'FAIL' })), '测试失败');
});
test('financial values preserve exact strings and zero is visible', () => {
  assert.equal(displayValue('100000000000000000000000001'), '100000000000000000000000001');
  assert.equal(displayValue('0.00000001'), '0.00000001'); assert.equal(displayValue(0), '0');
});
test('late history from an old project cannot replace the current project', async () => {
  const old = deferred<Job[]>();
  const f = fixture({ jobs: project => project === '1' ? old.promise : Promise.resolve([job(idB, '2')]),
    job: async id => job(id, id === idB ? '2' : '1') });
  const first = f.controller.setProject('1'); await f.controller.setProject('2');
  old.resolve([job(idA)]); await first;
  assert.equal(f.state.projectId, '2'); assert.equal(f.state.job?.id, idB); assert.equal(f.state.jobs[0].project_id, '2');
});
test('late job selection cannot replace a newer selection', async () => {
  const old = deferred<Job>(); const f = fixture({ job: id => id === idA ? old.promise : Promise.resolve(job(idB)) });
  await f.controller.setProject('1'); const first = f.controller.selectJob(idA); await f.controller.selectJob(idB);
  old.resolve(job()); await first; assert.equal(f.state.job?.id, idB);
});
test('a rapid double submit creates one request', async () => {
  const submitted = deferred<{ job: Job; duplicate: boolean }>(); let calls = 0;
  const f = fixture({ submit: () => { calls++; return submitted.promise; } }); await f.controller.setProject('1');
  const first = f.controller.submit(form), second = f.controller.submit(form);
  assert.equal(calls, 1); submitted.resolve({ job: job(), duplicate: false }); await Promise.all([first, second]);
  assert.equal(calls, 1); assert.equal(f.state.pending, null);
});
test('an ambiguous submit retries the original immutable payload and key', async () => {
  const bodies: CreateJob[] = []; const f = fixture({ submit: async body => {
    bodies.push(structuredClone(body)); if (bodies.length === 1) throw new Error('network timeout');
    return { job: job(idA, '1', { request_key: body.request_key }), duplicate: true };
  } });
  await f.controller.setProject('1'); await f.controller.submit(form);
  assert.ok(f.persisted.has('1')); assert.match(f.state.submitError, /原请求重试/);
  await f.controller.submit({ ...form, run_kind: 'selftest', timeout_seconds: 1 });
  assert.deepEqual(bodies[0], bodies[1]); assert.equal(f.persisted.size, 0);
});
test('history reconciles an accepted request after its HTTP response was lost', async () => {
  let created: Job | null = null, posts = 0;
  const f = fixture({ submit: async body => { posts++; created = job(idA, '1', { request_key: body.request_key }); throw new Error('response lost'); },
    jobs: async () => created ? [created] : [] });
  await f.controller.setProject('1'); await f.controller.submit(form); await f.controller.refresh();
  assert.equal(posts, 1); assert.equal(f.state.pending, null); assert.equal(f.state.job?.id, idA); assert.match(f.state.notice, /未重复创建/);
});
test('reload can restore and confirm a pending request', async () => {
  const f = fixture(); const body: CreateJob = { ...form, project_id: 1, project_key: 'leon-qa-kit', request_key: 'reload_001' };
  f.storage.write('1', body); await f.controller.setProject('1'); assert.deepEqual(f.state.pending, body);
  let observed: CreateJob | undefined; f.api.submit = async request => { observed = request; return { job: job(), duplicate: true }; };
  await f.controller.submit({ ...form, timeout_seconds: 1 }); assert.deepEqual(observed, body);
});
test('a new confirmed run gets a fresh key instead of overwriting history', async () => {
  const keys: string[] = []; const f = fixture({ submit: async body => { keys.push(body.request_key); return { job: job(keys.length === 1 ? idA : idB), duplicate: false }; } });
  await f.controller.setProject('1'); await f.controller.submit(form); await f.controller.submit(form);
  assert.equal(new Set(keys).size, 2); assert.equal(f.state.jobs.length, 2);
});
test('invalid timeouts are blocked before a task is created', async () => {
  let calls = 0; const f = fixture({ submit: async () => { calls++; return { job: job(), duplicate: false }; } });
  await f.controller.setProject('1'); for (const timeout of [0, 901, 1.5, NaN]) await f.controller.submit({ ...form, timeout_seconds: timeout });
  assert.equal(calls, 0); assert.equal(f.persisted.size, 0);
});
test('unavailable browser storage cannot lose the request identity during creation', async () => {
  const state = initialState(); state.projectId = '1'; let calls = 0;
  const f = fixture({ submit: async () => { calls++; return { job: job(), duplicate: false }; } });
  const c = createRunnerController(state, f.api, { read: () => null, write: () => { throw new Error('storage unavailable'); } });
  await c.submit(form); assert.equal(calls, 0); assert.match(state.submitError, /storage unavailable/);
});
test('evidence from another run is rejected rather than displayed', async () => {
  const f = fixture({ artifact: async () => new Blob([JSON.stringify({ document_type: 'leon.qa.case', run_id: 'foreign', case_id: 'A' })]) });
  await f.controller.setProject('1'); f.state.job = job(); f.state.job.result = { cases: [{ case_id: 'A', evidence_file: 'cases/A.json' }] } as any;
  await f.controller.selectCase('A'); assert.equal(f.state.caseBundle, null); assert.match(f.state.caseError, /身份/);
});
test('late case evidence is discarded after selecting another job', async () => {
  const pending = deferred<Blob>(), f = fixture({ artifact: () => pending.promise });
  await f.controller.setProject('1'); f.state.job = job(); f.state.job.result = { cases: [{ case_id: 'A', evidence_file: 'cases/A.json' }] } as any;
  const first = f.controller.selectCase('A'); await f.controller.selectJob(idB);
  pending.resolve(new Blob([JSON.stringify({ document_type: 'leon.qa.case', run_id: 'job_' + idA, case_id: 'A' })])); await first;
  assert.equal(f.state.caseBundle, null); assert.equal(f.state.caseLoading, false);
});
test('switching log streams discards old bytes without duplicating events', async () => {
  const old = deferred<any>(); let stderrReads = 0;
  const event = { seq: 1, code: 'started', level: 'info', at: '2026-11-21T00:00:00Z', message: 'started' };
  const f = fixture({ events: async () => ({ items: [event], next_after: 1 }), logs: async (_id, stream) => {
    if (stream === 'stderr' && ++stderrReads === 1) return old.promise;
    return { text: 'new-stream', next_offset: 10, size_bytes: 10, complete: true };
  } });
  await f.controller.setProject('1'); const first = f.controller.selectJob(idA); await tick();
  await f.controller.setStream('stdout'); old.resolve({ text: 'stale', next_offset: 5, size_bytes: 5, complete: false }); await first;
  assert.equal(f.state.logText, 'new-stream'); assert.equal(f.state.logOffset, 10); assert.equal(f.state.events.length, 1);
});
test('permission loss clears cached job and evidence', async () => {
  const f = fixture(); await f.controller.setProject('1'); await f.controller.selectJob(idA);
  f.state.caseBundle = { dataset_id: 'previous-private-data' } as any;
  f.api.jobs = async () => { throw { response: { status: 403 }, message: 'forbidden' }; }; await f.controller.refresh();
  assert.equal(f.state.job, null); assert.equal(f.state.caseBundle, null); assert.equal(f.state.jobs.length, 0);
});
test('leaving the page prevents an in-flight response from restoring old state', async () => {
  const pending = deferred<Job>(), f = fixture({ job: () => pending.promise });
  await f.controller.setProject('1'); const first = f.controller.selectJob(idA); f.controller.dispose(); pending.resolve(job()); await first;
  assert.equal(f.state.job, null);
});
