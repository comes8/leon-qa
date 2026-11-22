import test from 'node:test';
import assert from 'node:assert/strict';
import {
	createDesignController,
	initialDesignState,
	requestUncertain,
	readinessLabel,
	errorText,
	assertDesignExport,
} from '../src/views/testing/web3-area/design-state';
const deferred = () => {
	let resolve!: (value: any) => void;
	const promise = new Promise<any>((r) => (resolve = r));
	return { promise, resolve };
};
test('late project response cannot reveal previous project design', async () => {
	const a = deferred(),
		state = initialDesignState();
	const c = createDesignController(state, {
		options: (p) => (p === '1' ? a.promise : Promise.resolve({ stages: {}, bundles: [] })),
		list: (p) => Promise.resolve(p === '1' ? [{ id: 1 }] : [{ id: 2 }]),
		detail: (id) => Promise.resolve({ id, project_id: id, heads: {} }),
	});
	const first = c.project('1');
	await c.project('2');
	a.resolve({ stages: {}, bundles: [] });
	await first;
	assert.equal(state.project, '2');
	assert.equal(state.task.id, 2);
});
test('late task read cannot replace new selection', async () => {
	const a = deferred(),
		state = initialDesignState();
	state.project = '1';
	const c = createDesignController(state, {
		options: async () => ({}),
		list: async () => [],
		detail: (id) => (id === 1 ? a.promise : Promise.resolve({ id, project_id: 1 })),
	});
	const first = c.select(1);
	await c.select(2);
	a.resolve({ id: 1, project_id: 1 });
	await first;
	assert.equal(state.task.id, 2);
});
test('disposed page ignores late reads', async () => {
	const a = deferred(),
		state = initialDesignState();
	state.project = '1';
	const c = createDesignController(state, { options: async () => ({}), list: async () => [], detail: () => a.promise });
	const result = c.select(1);
	c.dispose();
	a.resolve({ id: 1, project_id: 1 });
	await result;
	assert.equal(state.task, null);
});
test('network uncertainty is different from rejected input and readiness is not test pass', () => {
	assert.equal(requestUncertain(new Error('timeout')), true);
	assert.equal(requestUncertain({ response: { status: 409 } }), false);
	assert.equal(requestUncertain({ response: { status: 503 } }), true);
	assert.equal(readinessLabel('ready'), '设计就绪');
	assert.notEqual(readinessLabel('ready'), '测试通过');
});
test('deep links load a specific task beyond the recent list', async () => {
	const state = initialDesignState();
	const c = createDesignController(state, {
		options: async () => ({}),
		list: async () => [{ id: 100 }],
		detail: async (id) => ({ id, project_id: 1 }),
	});
	await c.project('1', '2');
	assert.equal(state.task.id, 2);
});
test('a task from a different project is not displayed', async () => {
	const state = initialDesignState();
	const c = createDesignController(state, { options: async () => ({}), list: async () => [], detail: async (id) => ({ id, project_id: 2 }) });
	await c.project('1', '2');
	assert.equal(state.task, null);
	assert.match(state.error, /不属于当前项目/);
});
test('validation details are readable and never expose input values', () => {
	assert.equal(
		errorText({ response: { data: { detail: [{ loc: ['body', 'note'], msg: 'too short', input: 'private' }] } } }),
		'body.note: too short'
	);
});
test('exports require a complete raw document for the requested task before download', () => {
	const document = { id: 1, all_inputs: [], all_artifacts: [{ id: 38 }] };
	assert.equal(assertDesignExport(document, 1), document);
	for (const invalid of [undefined, { data: document }, { ...document, id: 2 }, { id: 1, all_inputs: [] }]) {
		assert.throws(() => assertDesignExport(invalid, 1), /导出内容不完整/);
	}
});
