import test from 'node:test';import assert from 'node:assert/strict';
import {createDiagnostics,healthLabel} from '../src/views/testing/qa-runner/diagnostics';
import type {HealthReport} from '../src/views/testing/qa-runner/diagnostics';
const report=(id:string)=>({overall:'ready',checked_at:id,worker_status:'idle',checks:[],scope:'local'}) as HealthReport;
test('late project response cannot overwrite current diagnostics',async()=>{let resolve!:(r:HealthReport)=>void;let current:HealthReport|null=null;const first=new Promise<HealthReport>(r=>resolve=r);const c=createDiagnostics(id=>id==='1'?first:Promise.resolve(report('2')),r=>current=r);const pending=c.refresh('1');await c.refresh('2');resolve(report('1'));await pending;assert.equal((current as HealthReport|null)?.checked_at,'2')});
test('close discards in-flight diagnostics',async()=>{let resolve!:(r:HealthReport)=>void;let current:HealthReport|null=null;const c=createDiagnostics(()=>new Promise(r=>resolve=r),r=>current=r);const p=c.refresh('1');c.clear();resolve(report('1'));await p;assert.equal(current,null)});
test('connection or permission failure clears old green result',async()=>{let error='',value:HealthReport|null=null;const c=createDiagnostics(async()=>{throw new Error('offline')},(r,e)=>{value=r;error=e});await c.refresh('1');assert.equal(value,null);assert.match(error,/诊断不可用/)});
test('health labels do not claim a test verdict',()=>{assert.equal(healthLabel('ready'),'全部就绪');assert.equal(healthLabel('blocked'),'异常阻塞');assert.notEqual(healthLabel('healthy'),'断言通过')});
