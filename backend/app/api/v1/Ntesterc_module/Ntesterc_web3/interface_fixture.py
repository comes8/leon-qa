"""Add a separate, documented local v2 catalogue; never rewrite prior API assets."""
from sqlalchemy import select
from . import service as W

CATALOGUE=[
 ('session', '创建隔离合成会话',2,'/sessions',{},'201; session_id:string, environment=local_mock。初始QUOTE free=1000, locked=0。每例独立创建，数据两小时过期。'),
 ('balances','查询现货初始/当前余额',1,'/{{session_id}}/spot/balances',None,'200; asset=QUOTE, free/locked是八位小数字符串，profile=local-synthetic-spot-v1。与订单查询分别读取，同属一个本地模拟进程，非独立生产账务。'),
 ('place','现货限价买单',2,'/{{session_id}}/spot/orders',{'quantity':'5','price':'10'},'201; orderId:string,status=NEW,origQty=5,executedQty=0,remainingFrozen=50,canceledQty=0,activeRemainingQty=5（数值按quantity=5 price=10）。费用0仅限示例，0.01步长，失败400/code；仅合成单向买单，无真实撮合。'),
 ('order','查询同一现货订单',1,'/{{session_id}}/spot/orders/{{order_id}}',None,'200; orderId,status,origQty,executedQty,remainingFrozen,canceledQty,activeRemainingQty。NEW=5/0/50/0/5；填2后PARTIALLY_FILLED=5/2/30/0/3；撤余后CANCELED=5/2/0/3/0。未知订单404/code=ORDER_NOT_FOUND。'),
 ('fill','显式合成成交控制',2,'/{{session_id}}/spot/orders/{{order_id}}/fills',{'quantity':'2'},'200; 返回订单全部字段和fillId:string。本地显式串行控制，响应返回前订单、余额和spent事件已同步生效。quantity=2 price=10则PARTIALLY_FILLED,executedQty=2,remainingFrozen=30，free950/locked30。不是实际撮合/异步结算证明。非法成交400/code=INVALID_FILL。'),
 ('cancel','撤销现货余单',4,'/{{session_id}}/spot/orders/{{order_id}}',None,'200; 返回订单字段。部分成交2后撤余，CANCELED,executedQty=2,canceledQty=3,activeRemainingQty=0,remainingFrozen=0；QUOTE free980/locked0。重复撤单409/code=ORDER_NOT_CANCELABLE，订单余额及事件不变。'),
 ('events','查询完整合成资金事件',1,'/{{session_id}}/spot/events/{{order_id}}',None,'200; orderId, records:[{eventId,orderId,kind,amount,asset,freeAfter,lockedAfter}],spent,released,observation。每个经济效果保留全部记录，不按orderId去重。下单frozen50；成交2后spent20/released0；撤余后spent20/released30。聚合由事件记录累计，不由订单filled/released字段反推。与余额同进程内存，非独立生产账务源。'),
 ('cleanup','清理本例合成会话',4,'/{{session_id}}/session',None,'200; deleted=true,session_id,scope=local_synthetic_only。仅清除本例session，所有断言取证完成后调用；无真实资产或生产数据。已清理会话再次读取404/detail。'),
]

async def provision(db,project,user):
 await W.ProjectService._check_project_permission(project,user,['owner','admin','developer','tester'],db)
 name='Leon QA · 现货本地契约 v2'
 service=await db.scalar(select(W.ApiServiceModel).where(W.ApiServiceModel.api_project_id==project,W.ApiServiceModel.created_by==user,W.ApiServiceModel.name==name,W.ApiServiceModel.enabled_flag==1))
 if service is None:
  service=W.ApiServiceModel(name=name,api_project_id=project,created_by=user,updated_by=user,description='第三批本地合成现货契约；独立API目录，不改原v1资产。');db.add(service);await db.flush()
 for key,title,method,path,body,contract in CATALOGUE:
  exists=await db.scalar(select(W.ApiModel).where(W.ApiModel.api_service_id==service.id,W.ApiModel.name==title,W.ApiModel.enabled_flag==1))
  if exists:continue
  db.add(W.ApiModel(name=title,api_service_id=service.id,url='http://127.0.0.1:18171/api/v1/Ntesterc_web3/mock'+path,
   description=contract,document={'source':'web3_mock_v2','operation_key':key,'scope':'local_mock','contract':contract,'evidence_limit':'Synthetic only; not independent production ledger'},
   req={'method':method,'body_type':2,'body':body,'params':[],'header':[],'config':{'retry':0,'req_timeout':5,'res_timeout':5,'allow_redirects':False}},created_by=user,updated_by=user))
 envname='Leon QA · 本地现货隔离环境 v2'
 env=await db.scalar(select(W.ApiEnvironmentModel).where(W.ApiEnvironmentModel.created_by==user,W.ApiEnvironmentModel.name==envname,W.ApiEnvironmentModel.enabled_flag==1))
 if env is None:
  env=W.ApiEnvironmentModel(name=envname,config=[],variable=[],description='固定本机127.0.0.1:18171；每例独立session；无凭据',created_by=user,updated_by=user);db.add(env)
 await db.commit();return {'service_id':service.id,'environment_id':env.id,'interfaces':len(CATALOGUE)}
