import test from 'node:test';
import assert from 'node:assert/strict';
import { createLabController, initialLabState } from '../src/views/testing/qa-lab/controller';
import { validSeed, minorAmount } from '../src/views/testing/qa-lab/model';
import type { LabApi, LabRequest, LabView, Operation } from '../src/views/testing/qa-lab/model';
const view = (): LabView => ({ environments: [], datasets: [], operations: [], worker: { status: 'idle' }, limits: { manual_environments: 2, per_project_user: 1 } });
const operation = (body: LabRequest): Operation => ({ id: body.request_key, environment_id: 'env-one', dataset_id: null,
  action: body.action, status: 'queued', request_key: body.request_key, inputs: body, creation_date: '2026-11-21T00:00:00Z' });
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; }
function fixture(overrides: Partial<LabApi> = {}) {
  const state = initialLabState(), pending = new Map<string, LabRequest>(); let count = 0;
  const api: LabApi = { state: async () => view(), submit: async body => ({ operation: operation(body), duplicate: false }), ...overrides };
  const storage = { read: (id: string) => pending.get(id) || null, write: (id: string, value: LabRequest | null) => { if (value) pending.set(id, structuredClone(value)); else pending.delete(id); } };
  const controller = createLabController(state, api, storage, () => 'request_' + ++count);
  return { state, pending, api, storage, controller };
}

test('seed validation rejects rounding, exponents, negative and overflow', () => {
  for (const value of ['0', '1000', '0.00000001', '10000000.00000000']) assert.ok(validSeed(value));
  for (const value of ['-1', '1e3', ' 1', '0.000000001', '10000000.00000001', '1;echo x']) assert.equal(validSeed(value), false);
});
test('minor-unit formatting is lossless above JavaScript safe-integer range', () => {
  assert.equal(minorAmount('900719925474099300001'), '9007199254740.99300001');
  assert.equal(minorAmount('1'), '0.00000001'); assert.equal(minorAmount('0'), '0.00000000');
  assert.equal(minorAmount('-1'), '-0.00000001');
});
test('old project state cannot overwrite another project', async () => {
  const old = deferred<LabView>(); const f = fixture({ state: id => id === '1' ? old.promise : Promise.resolve(view()) });
  const first = f.controller.project('1'); await f.controller.project('2'); old.resolve({ ...view(), environments: [{ id: 'old' } as any] }); await first;
  assert.equal(f.state.project, '2'); assert.equal(f.state.environments.length, 0);
});
test('double clicking one operation submits only once', async () => {
  const pending = deferred<{ operation: Operation; duplicate: boolean }>(); let calls = 0;
  const f = fixture({ submit: async () => { calls++; return pending.promise; } }); await f.controller.project('1');
  const first = f.controller.submit({ action: 'start' }), second = f.controller.submit({ action: 'start' });
  assert.equal(calls, 1); pending.resolve({ operation: operation({ project_id: 1, action: 'start', request_key: 'once_001' }), duplicate: false }); await Promise.all([first, second]);
  assert.equal(calls, 1);
});
test('unknown outcome keeps exactly the same request for retry', async () => {
  const bodies: LabRequest[] = []; const f = fixture({ submit: async body => {
    bodies.push(structuredClone(body)); if (bodies.length === 1) throw new Error('connection lost');
    return { operation: operation(body), duplicate: true };
  } }); await f.controller.project('1'); await f.controller.submit({ action: 'create', environment_id: 'one', name: 'A', funding: '1000', spot: '0' });
  assert.ok(f.pending.has('1')); await f.controller.submit({ action: 'delete', environment_id: 'different' });
  assert.deepEqual(bodies[0], bodies[1]); assert.equal(f.pending.size, 0);
});
test('history confirms an accepted request without posting it again', async () => {
  let known: Operation | null = null, posts = 0;
  const f = fixture({ state: async () => ({ ...view(), operations: known ? [known] : [] }),
    submit: async body => { posts++; known = operation(body); throw new Error('response lost'); } });
  await f.controller.project('1'); await f.controller.submit({ action: 'start' }); await f.controller.refresh();
  assert.equal(posts, 1); assert.equal(f.state.pending, null); assert.match(f.state.notice, /没有重复/);
});
test('known validation rejection releases pending form for correction', async () => {
  const f = fixture({ submit: async () => { throw { message: 'invalid seed', response: { status: 422 } }; } });
  await f.controller.project('1'); await f.controller.submit({ action: 'start' }); assert.equal(f.state.pending, null); assert.equal(f.pending.size, 0);
});
test('permission loss clears cached environments and snapshots', async () => {
  const f = fixture(); await f.controller.project('1'); f.state.datasets = [{ id: 'private' } as any];
  f.api.state = async () => { throw { message: 'forbidden', response: { status: 403 } }; }; await f.controller.refresh(); assert.equal(f.state.datasets.length, 0);
});
test('storage failure prevents a mutation without a durable request key', async () => {
  let calls = 0; const f = fixture({ submit: async body => { calls++; return { operation: operation(body), duplicate: false }; } });
  f.state.project = '1'; const c = createLabController(f.state, f.api, { read: () => null, write: () => { throw new Error('storage blocked'); } });
  await c.submit({ action: 'start' }); assert.equal(calls, 0);
});
test('leaving the page discards in-flight read responses', async () => {
  const pending = deferred<LabView>(); const f = fixture({ state: () => pending.promise });
  const first = f.controller.project('1'); f.controller.dispose(); pending.resolve({ ...view(), environments: [{ id: 'old' } as any] }); await first;
  assert.equal(f.state.environments.length, 0);
});
