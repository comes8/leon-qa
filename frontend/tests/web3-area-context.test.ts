import test from 'node:test';
import assert from 'node:assert/strict';
import { cleanContext, mergeContext, renderPrompt } from '../src/views/testing/web3-area/context';
import {menuSchemaVersion,validNavigationCache} from '../src/utils/menuCache';

test('nested old Web3 entry invalidates navigation cache even with a current marker',()=>{
 assert.equal(validNavigationCache([{path:'/api-automation',children:[{path:'/api-automation/web3'}]}],menuSchemaVersion),false);
 assert.equal(validNavigationCache([{path:'/web3',children:[{path:'/web3/requirements'}]}],menuSchemaVersion),true);
});
test('navigation version refresh does not require changing login state',()=>{
 assert.equal(validNavigationCache([{path:'/web3'}],undefined),false);
 assert.equal(validNavigationCache(null,menuSchemaVersion),false);
});

test('workspace context contains identifiers only, never credentials or source paths', () => {
	assert.deepEqual(
		cleanContext({ project: 1, workflow: '4', dataset: 'ds_123', token: 'secret', source: '/Users/private', job: ['ambiguous'], env: '../escape' }),
		{ project: '1', workflow: '4', dataset: 'ds_123' }
	);
});
test('switching project clears all dependent IDs before accepting explicit new identifiers', () => {
	assert.deepEqual(mergeContext({ project: '1', workflow: '4', env: 'old', dataset: 'old', job: 'old' }, { project: '2', workflow: '7' }), {
		project: '2',
		workflow: '7',
	});
});
test('navigation within a project retains the selected requirement and manual data', () => {
	assert.deepEqual(mergeContext({ project: '1', workflow: '4', env: 'e1', dataset: 'd1' }, {}), {
		project: '1',
		workflow: '4',
		env: 'e1',
		dataset: 'd1',
	});
});
test('prompt preview replaces only filled explicit variables and preserves API placeholders', () => {
	assert.equal(
		renderPrompt('分析{{需求}}，调用{{base_url}}，参考{{背景，可省略}}', { 需求: '现货撤单 $&', '背景，可省略': '' }),
		'分析现货撤单 $&，调用{{base_url}}，参考{{背景，可省略}}'
	);
});
