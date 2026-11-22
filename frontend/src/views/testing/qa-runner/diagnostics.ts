export interface HealthReport {
 overall:string;checked_at:string;worker_status:string;scope:string;
 checks:{id:string;label:string;status:string;detail:string}[];
 environments?:{id:string;status:string;cleanup_status:string;probe?:string;checked_at?:string;consecutive_failures?:number}[];
}
export const healthLabel=(v:string)=>({ready:'全部就绪',healthy:'正常',degraded:'需要处理',unknown:'待确认',idle:'空闲待命',running:'运行中',starting:'启动或恢复中',blocked:'异常阻塞',offline:'离线'}[v]||v);
export function createDiagnostics(read:(project:string)=>Promise<HealthReport>,set:(report:HealthReport|null,error:string,loading:boolean)=>void){
 let generation=0;
 return {async refresh(project:string){const current=++generation;set(null,'',true);try{const report=await read(project);if(current===generation)set(report,'',false);}catch{if(current===generation)set(null,'诊断不可用。请检查登录、项目权限及后端连接，再运行本机 doctor。',false);}},clear(){generation++;set(null,'',false);}};
}
