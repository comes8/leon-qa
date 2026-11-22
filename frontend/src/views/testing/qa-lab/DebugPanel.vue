<template>
 <section id="qa-debug" class="debug-panel" aria-label="资金接口调试">
  <h2>资金接口调试</h2><p class="hint">固定同用户资金 ↔ 现货链路 · 仅本机 TESTUSD。先划转，再按原请求号查询，最后填写预期执行断言。账户和流水来自独立 SQL 观察。</p>
  <el-alert v-if="dataset.error_message" :title="dataset.error_message" type="warning" :closable="false" />
  <el-form label-position="top" class="debug-form">
   <el-form-item label="合成用户"><el-select v-model="form.user" aria-label="调试用户"><el-option label="alice" value="alice"/><el-option label="bob" value="bob"/></el-select></el-form-item>
   <el-form-item class="request-field" label="业务请求号（同号同载荷可重试）"><el-input v-model="form.requestId" aria-label="业务请求号" placeholder="例如：manual-001" :maxlength="80"/><el-button @click="newRequest">生成新请求号</el-button></el-form-item>
   <el-form-item label="转出账户"><el-select v-model="form.from" aria-label="转出账户"><el-option label="资金 funding" value="funding"/><el-option label="现货 spot" value="spot"/></el-select></el-form-item>
   <el-form-item label="转入账户"><el-select v-model="form.to" aria-label="转入账户"><el-option label="现货 spot" value="spot"/><el-option label="资金 funding" value="funding"/></el-select></el-form-item>
   <el-form-item label="划转金额（TESTUSD）"><el-input v-model="form.amount" aria-label="划转金额"/></el-form-item>
   <el-form-item label="预期资金余额"><el-input v-model="form.funding" aria-label="预期资金余额"/></el-form-item>
   <el-form-item label="预期现货余额"><el-input v-model="form.spot" aria-label="预期现货余额"/></el-form-item>
   <el-form-item label="预期业务状态"><el-select v-model="form.status" aria-label="预期业务状态"><el-option label="SUCCEEDED 成功" value="SUCCEEDED"/><el-option label="REJECTED 拒绝" value="REJECTED"/></el-select></el-form-item>
   <el-form-item label="需求编号（可选）"><el-input v-model="form.requirement" aria-label="需求编号" :maxlength="120"/></el-form-item>
   <el-form-item label="用例编号（可选）"><el-input v-model="form.caseId" aria-label="用例编号" :maxlength="120"/></el-form-item>
   <el-form-item class="note-field" label="评审备注（可选）"><el-input v-model="form.note" aria-label="评审备注" type="textarea" :maxlength="1000"/></el-form-item>
  </el-form>
  <p class="hint">预期是你填写的测试判据，不随当前余额自动改写。HTTP200可能为REJECTED；操作完成不等于业务断言通过。关联编号作为文本标签保存，不自动创建需求或用例。</p>
  <div class="buttons"><el-button type="primary" :disabled="!ready" @click="submit('transfer')">发起划转</el-button><el-button :disabled="!ready" @click="submit('query')">按原请求号查询</el-button><el-button type="success" :disabled="!ready" @click="submit('verify')">执行业务断言</el-button></div>
  <h3>实际业务记录与流水</h3><el-table :data="dataset.snapshot?.transfers || []" size="small" border :max-height="230"><el-table-column prop="user_id" label="用户" width="70"/><el-table-column prop="request_id" label="请求号" min-width="160"/><el-table-column prop="status" label="业务状态" width="120"/><el-table-column prop="reason" label="原因" min-width="160"/></el-table>
  <el-table :data="dataset.snapshot?.ledger || []" size="small" border :max-height="230" class="ledger"><el-table-column prop="user_id" label="用户" width="70"/><el-table-column prop="request_id" label="请求号" min-width="150"/><el-table-column prop="kind" label="账户" width="90"/><el-table-column label="变动 TESTUSD" min-width="140"><template #default="{row}">{{minorAmount(row.delta_minor)}}</template></el-table-column><el-table-column label="变动后余额" min-width="150"><template #default="{row}">{{minorAmount(row.balance_after_minor)}}</template></el-table-column></el-table>
  <h3>本数据集调试历史</h3><p class="hint">记录绑定当时的环境、Go数据集ID和代次；重建后仍保留原证据。列表来源为本人当前项目最近100次操作。</p>
  <div class="debug-history"><button v-for="op in history" :key="op.id" class="record-button" :class="{selected:op.id===selected}" :aria-label="`查看调试 ${op.id}`" @click="selected=op.id"><b>{{actionLabel(op.action)}} · {{op.inputs.business_request_id}}</b><span>{{labStatus(op.status)}} · {{formatTime(op.creation_date)}}</span></button></div>
  <section v-if="record" :key="record.id" class="receipt" aria-label="调试记录详情">
   <div class="receipt-heading"><div><h3>{{actionLabel(record.action)}} · {{record.inputs.business_request_id}}</h3><code>{{record.id}}</code></div><div class="buttons"><el-button @click="reuse">复用本记录输入</el-button><el-button v-if="receipt" @click="download">导出本条调试记录</el-button></div></div>
   <p>{{labStatus(record.status)}} <el-tag v-if="receipt" :disable-transitions="true" :type="receipt.verdict==='PASS'?'success':receipt.verdict==='FAIL'?'danger':'warning'">{{verdictLabel(receipt.verdict)}}</el-tag></p>
   <el-alert v-if="receipt?.verdict==='UNKNOWN'||record.error_message" :title="record.error_message || '结果未知。请按原请求号查询，不要换号重试。'" type="warning" :closable="false"/>
   <template v-if="receipt"><p class="hint">业务请求 {{receipt.request_id}} · Go数据集 {{receipt.dataset_id || '未取得可信回执'}} · 第{{receipt.generation || '—'}}代</p><p v-if="receipt.error_code" class="business-error">业务/传输结果：{{receipt.outcome}} · {{receipt.error_code}}</p>
    <p v-if="receipt.associations" class="associations">需求 {{receipt.associations.requirement_ref || '—'}} · 用例 {{receipt.associations.case_ref || '—'}}<br/>评审备注 {{receipt.associations.review_note || '—'}}</p>
    <h4>接口响应</h4><pre>{{JSON.stringify(receipt.response ?? null,null,2)}}</pre>
    <h4>SDK业务断言</h4><el-table :data="receipt.assertions || []" size="small" border :max-height="380"><el-table-column prop="rule_id" label="规则" min-width="150"/><el-table-column prop="subject" label="对象" min-width="180"/><el-table-column label="预期" min-width="150"><template #default="{row}">{{preview(row.expected)}}</template></el-table-column><el-table-column label="实际" min-width="150"><template #default="{row}">{{preview(row.actual)}}</template></el-table-column><el-table-column prop="status" label="结果" width="80"/></el-table>
    <details><summary>查看请求响应、前后快照与完整断言</summary><pre>{{JSON.stringify(receipt,null,2)}}</pre></details>
   </template>
  </section>
 </section>
</template>
<script setup lang="ts">
import {computed,reactive,ref,watch} from 'vue';
import {ElMessage,ElMessageBox} from 'element-plus';
import type {Dataset,LabRequest,Operation} from './model';
import {minorAmount,actionLabel,labStatus} from './model';
import {formatTime} from '../qa-runner/model';
import {debugForm,debugRequest,verdictLabel,preview} from './debug';
import type {DebugAction,DebugReceipt} from './debug';
const props=defineProps<{dataset:Dataset;environmentId:string;ready:boolean;operations:Operation[]}>();
const emit=defineEmits<{(e:'submit',body:Omit<LabRequest,'project_id'|'request_key'>):void}>();
const form=reactive(debugForm()), selected=ref(''), confirming=ref(false);
const history=computed(()=>props.operations.filter(o=>o.dataset_id===props.dataset.id&&['transfer','query','verify'].includes(o.action)));
watch(()=>[props.dataset.id,history.value[0]?.id],()=>{selected.value=history.value[0]?.id||'';},{immediate:true});
const record=computed(()=>history.value.find(o=>o.id===selected.value));
const receipt=computed(()=>record.value?.result as DebugReceipt|undefined);
function newRequest(){form.requestId='manual-'+crypto.randomUUID().slice(0,12);}
async function submit(action:DebugAction){
 if(confirming.value||!props.ready)return;confirming.value=true;
 try{
  const body=debugRequest(action,form,props.environmentId,props.dataset.id,props.dataset.revision);
  if(action==='transfer')await ElMessageBox.confirm(`仅本机合成数据：${form.user} ${form.from} → ${form.to}，金额 ${form.amount} TESTUSD，请求号 ${form.requestId}。同号改载荷会冲突。`,'确认调试划转',{confirmButtonText:'提交本次划转',cancelButtonText:'返回',type:'warning'});
  emit('submit',body);
 }catch(e){if(e!=='cancel'&&e!=='close')ElMessage.warning(e instanceof Error?e.message:'操作取消');}finally{confirming.value=false;}
}
function reuse(){const i=record.value?.inputs;if(!i)return;Object.assign(form,{user:i.test_user||'alice',requestId:i.business_request_id||'',from:i.from_account||form.from,to:i.to_account||form.to,amount:i.amount||form.amount,funding:i.expected_funding||form.funding,spot:i.expected_spot||form.spot,status:i.expected_status||form.status,requirement:i.requirement_ref||'',caseId:i.case_ref||'',note:i.review_note||''});ElMessage.info('已复用输入，尚未执行；请核对当前数据集代次');}
function download(){if(!record.value)return;const url=URL.createObjectURL(new Blob([JSON.stringify(record.value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`leon-debug-${record.value.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
</script>
<style scoped>
.debug-panel{margin-top:26px;border-top:1px solid var(--el-border-color-lighter);padding-top:24px;scroll-margin-top:90px}h2{font-size:18px;margin:0 0 10px}h3{font-size:15px;margin:22px 0 12px}h4{margin:20px 0 10px}.hint{font-size:12px;color:var(--el-text-color-secondary);line-height:1.8}.debug-form{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0 16px;margin-top:20px}.request-field,.note-field{grid-column:span 2}.request-field :deep(.el-form-item__content){gap:8px}.el-select{width:100%}.buttons,.receipt-heading{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.buttons .el-button+.el-button{margin-left:0}.receipt-heading{justify-content:space-between}.ledger{margin-top:14px}.debug-history{display:flex;gap:8px;flex-wrap:wrap;max-height:220px;overflow:auto}.record-button{background:var(--el-bg-color);border:1px solid var(--el-border-color);border-radius:6px;padding:10px 12px;text-align:left;cursor:pointer;color:var(--el-text-color-primary)}.record-button b,.record-button span{display:block;line-height:1.7;overflow-wrap:anywhere}.record-button span{font-size:11px}.record-button.selected{border-color:var(--el-color-primary);background:var(--el-color-primary-light-9)}.receipt{margin-top:18px;padding-top:6px}code{font-size:11px;overflow-wrap:anywhere}.associations,.business-error{font-size:12px;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow:auto;max-height:420px;background:var(--el-fill-color-light);padding:14px;font-size:12px;overflow-wrap:anywhere}summary{cursor:pointer;font-size:13px;margin-top:18px;color:var(--el-color-primary)}@media(max-width:1100px){.debug-form{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.debug-form{grid-template-columns:1fr}.request-field,.note-field{grid-column:auto}}
</style>
