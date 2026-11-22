import test from 'node:test';
import assert from 'node:assert/strict';
import { interfaceVerdict, validInterfaceExport } from '../src/views/testing/web3-area/interface-state';
const receipt = { finished_at: 'now', passed_cases: 3, failed_cases: 0 };
test('completed infrastructure task still reports failed business assertions', () =>
	assert.equal(interfaceVerdict({ ...receipt, failed_cases: 1 }, 'succeeded'), '存在失败用例'));
test('only completed evidence can report a passing scope', () => {
	assert.equal(interfaceVerdict(receipt, 'succeeded'), '当次范围通过');
	assert.equal(interfaceVerdict({ ...receipt, finished_at: null }), '执行未完成');
	assert.equal(interfaceVerdict(null), '尚无执行证据');
});
test('interrupted cancelled and failed tasks never inherit historical pass', () => {
	for (const status of ['interrupted', 'cancelled', 'failed']) assert.notEqual(interfaceVerdict(receipt, status), '当次范围通过');
});
test('empty completed run is not proof of pass', () => assert.equal(interfaceVerdict({ ...receipt, passed_cases: 0 }), '没有通过证明'));
test('raw export must retain matching plan id business binding and jobs', () => {
	const data = { id: 2, snapshot: { business_binding: { cases: 41, case_review: 52 } }, jobs: [] };
	assert.equal(validInterfaceExport(data, 2), data);
	for (const bad of [{ data }, undefined, { ...data, id: 1 }, { ...data, jobs: undefined }]) assert.throws(() => validInterfaceExport(bad, 2));
});
