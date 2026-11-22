from fastapi import APIRouter,BackgroundTasks,Depends,HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.common.response import success_response
from . import interface_service as S,interface_schema as C,design_service as D
from .interface_model import InterfacePlan,InterfaceJob
from .design_controller import invalid_artifact

router=APIRouter()

@router.get('/options')
async def options(project_id:int,db:AsyncSession=Depends(get_db),user:int=Depends(get_current_user_id)):
    await D.A.ProjectService._check_project_member(project_id,user,db)
    tasks=(await db.scalars(select(D.DesignTask).where(D.DesignTask.project_id==project_id,D.DesignTask.created_by==user,D.DesignTask.enabled_flag==1).order_by(D.DesignTask.id.desc()).limit(100))).all()
    choices=await S.W.options(db,project_id,user)
    return success_response({'tasks':[{'id':t.id,'title':t.title} for t in tasks],'services':choices['services'],'environments':choices['environments'],'schema':C.InterfaceOutput.model_json_schema()})

@router.get('/plans')
async def listing(project_id:int,task_id:int|None=None,db:AsyncSession=Depends(get_db),user:int=Depends(get_current_user_id)):
    await D.A.ProjectService._check_project_member(project_id,user,db)
    q=select(InterfacePlan,S.W.Web3WorkflowModel.title).join(S.W.Web3WorkflowModel,S.W.Web3WorkflowModel.id==InterfacePlan.workflow_id).where(InterfacePlan.project_id==project_id,InterfacePlan.created_by==user,InterfacePlan.enabled_flag==1)
    if task_id:q=q.where(InterfacePlan.task_id==task_id)
    rows=(await db.execute(q.order_by(InterfacePlan.id.desc()).limit(100))).all()
    return success_response([{'id':p.id,'task_id':p.task_id,'title':title,'version':p.version,'busy_job_id':p.busy_job_id} for p,title in rows])

@router.post('/plans')
async def create(body:C.CreatePlan,db:AsyncSession=Depends(get_db),user:int=Depends(get_current_user_id)):
    p=await S.create(db,body,user);p,t,w=await S.owned(db,p.id,user)
    return success_response(await S.detail(db,p,t,w))

@router.get('/plans/{pid}')
async def detail(pid:int,db:AsyncSession=Depends(get_db),user:int=Depends(get_current_user_id)):
    p,t,w=await S.owned(db,pid,user);return success_response(await S.detail(db,p,t,w))

@router.post('/plans/{pid}/preview')
async def preview(pid:int,body:C.GeneratePlan,db:AsyncSession=Depends(get_db),user:int=Depends(get_current_user_id)):
    p,t,w=await S.owned(db,pid,user);snapshot=await S.preview(db,p,t,body)
    return success_response({'snapshot':snapshot,'input_hash':S.hashof(snapshot),'calls_model':False})

@router.post('/plans/{pid}/generate')
async def generate(pid:int,body:C.GeneratePlan,background:BackgroundTasks,db:AsyncSession=Depends(get_db),user:int=Depends(get_current_user_id)):
    p,t,w=await S.owned(db,pid,user,lock=True);job,created=await S.start(db,p,t,w,body,'generate')
    if created:background.add_task(S.process,job.id)
    return success_response({'job':S.job_json(job),'created':created})

@router.post('/plans/{pid}/revisions')
async def revise(pid:int,body:C.RevisePlan,db:AsyncSession=Depends(get_db),user:int=Depends(get_current_user_id)):
    p,t,w=await S.owned(db,pid,user,lock=True)
    try:child=await S.revise(db,p,t,w,body)
    except ValueError as e:raise invalid_artifact(e) from e
    cp,ct,cw=await S.owned(db,child.id,user);return success_response(await S.detail(db,cp,ct,cw))

@router.post('/plans/{pid}/publish')
async def publish(pid:int,body:C.PublishPlan,db:AsyncSession=Depends(get_db),user:int=Depends(get_current_user_id)):
    p,t,w=await S.owned(db,pid,user,lock=True);await S.publish(db,p,t,w,body)
    return success_response(await S.detail(db,p,t,w))

@router.post('/plans/{pid}/run')
async def run(pid:int,body:C.RunPlan,background:BackgroundTasks,db:AsyncSession=Depends(get_db),user:int=Depends(get_current_user_id)):
    p,t,w=await S.owned(db,pid,user,lock=True);job,created=await S.start(db,p,t,w,body,'execute')
    if created:background.add_task(S.process,job.id)
    return success_response({'job':S.job_json(job),'created':created})

@router.get('/plans/{pid}/jobs/{jid}')
async def job(pid:int,jid:int,db:AsyncSession=Depends(get_db),user:int=Depends(get_current_user_id)):
    await S.owned(db,pid,user)
    j=await db.scalar(select(InterfaceJob).where(InterfaceJob.id==jid,InterfaceJob.plan_id==pid,InterfaceJob.created_by==user))
    if j is None:raise HTTPException(404,'适配任务记录不存在')
    return success_response(S.job_json(j,True))

@router.post('/plans/{pid}/jobs/{jid}/cancel')
async def cancel(pid:int,jid:int,body:C.CancelRun,db:AsyncSession=Depends(get_db),user:int=Depends(get_current_user_id)):
    p,t,w=await S.owned(db,pid,user,lock=True)
    j=await db.scalar(select(InterfaceJob).where(InterfaceJob.id==jid,InterfaceJob.plan_id==pid).with_for_update().execution_options(populate_existing=True))
    if j is None or j.kind!='execute':raise HTTPException(400,'只能请求停止接口执行任务')
    if j.status not in ['queued','running']:return success_response(S.job_json(j))
    j.cancel_note=body.note
    if j.status=='queued':j.status='cancelled';p.busy_job_id=None;p.revision+=1;w.status='suite_ready'
    await db.commit();return success_response(S.job_json(j))

@router.get('/plans/{pid}/export')
async def export(pid:int,db:AsyncSession=Depends(get_db),user:int=Depends(get_current_user_id)):
    p,t,w=await S.owned(db,pid,user)
    data=await S.detail(db,p,t,w,full_export=True)
    data['export_scope']='固定业务版本、接口契约、映射与当次执行证据；历史通过不继承到新版本'
    return JSONResponse(S.W.redact(data),headers={'Content-Disposition':f'attachment; filename="web3-interface-{pid}.json"'})
