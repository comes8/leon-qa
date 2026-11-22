import type { LabRequest } from './model';
export type DebugAction='transfer'|'query'|'verify';
export interface DebugForm { user:'alice'|'bob'; requestId:string; from:'funding'|'spot'; to:'funding'|'spot'; amount:string; funding:string; spot:string; status:'SUCCEEDED'|'REJECTED'; requirement:string; caseId:string; note:string }
export const debugForm=():DebugForm=>({user:'alice',requestId:'',from:'funding',to:'spot',amount:'100',funding:'900',spot:'100',status:'SUCCEEDED',requirement:'',caseId:'',note:''});
export function validAmount(value:string,max:string,positive=false) {
 if(!/^[0-9]{1,8}(\.[0-9]{1,8})?$/.test(value))return false;
 const [w,f='']=value.split('.');const n=BigInt(w)*100000000n+BigInt(f.padEnd(8,'0'));
 return n<=BigInt(max)*100000000n&&(!positive||n>0n);
}
export function debugRequest(action:DebugAction,f:DebugForm,environment:string,dataset:string,revision:number):Omit<LabRequest,'project_id'|'request_key'> {
 if(!/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$/.test(f.requestId))throw new Error('请填写80位以内业务请求号，仅字母、数字及 _ . : -');
 const body:Omit<LabRequest,'project_id'|'request_key'>={action,environment_id:environment,dataset_id:dataset,expected_revision:revision,test_user:f.user,business_request_id:f.requestId};
 if(action!=='query') {
  if(f.from===f.to||!validAmount(f.amount,'10000000',true))throw new Error('请检查方向及划转金额');
  Object.assign(body,{from_account:f.from,to_account:f.to,amount:f.amount});
 }
 if(action==='verify') {
  if(!validAmount(f.funding,'20000000')||!validAmount(f.spot,'20000000'))throw new Error('请填写明确的合法预期余额');
  Object.assign(body,{expected_funding:f.funding,expected_spot:f.spot,expected_status:f.status});
 }
 for(const [key,value] of [['requirement_ref',f.requirement],['case_ref',f.caseId],['review_note',f.note]])if(value.trim())(body as any)[key]=value.trim();
 return body;
}
export interface DebugReceipt { action:DebugAction; outcome:string; verdict:string; error_code?:string; request_id:string; dataset_id?:string; generation?:number; user?:string; source_sha256?:string; response?:unknown; before?:unknown; after?:unknown;
 associations?:Record<string,string>; http_events?:{method:string;path:string;http_status:number;request?:unknown;response?:unknown;transport_error?:string}[];
 assertions?:{rule_id:string;label:string;subject:string;expected:unknown;actual:unknown;status:string;unit?:string}[] }
export const verdictLabel=(s:string)=>({PASS:'断言通过',FAIL:'断言失败',UNKNOWN:'结果未知',NOT_EVALUATED:'未执行业务断言'}[s]||s);
export const preview=(v:unknown)=>typeof v==='object'&&v!==null?'结构化数据，见完整证据':v===null?'null':String(v);
