"""Deterministic adapter contract; local synthetic regression only."""
def adapter_output(ids,cases,wrong_balance=False):
 def check(path,value,decimal=False):return {'mode':'jsonpath','check':path,'comparator':'decimal_eq' if decimal else 'eq','expect':value}
 def step(key,name,checks,body=None,extract=None,nums=None,purpose='setup'):
  return {'name':name,'api_id':ids['cancel' if key=='reject' else key],'body':body,'validators':[{'mode':'jmespath','check':'status_code','comparator':'eq','expect':201 if key in ['session','place'] else 409 if key=='reject' else 200},*checks],
   'extracts':[{'name':n,'extract_type':'jsonpath','path':p} for n,p in (extract or {}).items()],'business_steps':nums or [],'purpose':purpose,'rationale':'本地合成契约中的显式准备、观察或动作'}
 result=[]
 for index,c in enumerate(cases):
  nums=list(range(1,len(c['steps'])+1))
  steps=[step('session','本例独立会话',[check('$.environment','local_mock')],{}, {'session_id':'$.session_id'}),step('place','准备买单',[check('$.status','NEW')],{'quantity':'5','price':'10'},{'order_id':'$.orderId'}),step('fill','显式成交',[check('$.status','PARTIALLY_FILLED'),check('$.remainingFrozen','30',True)],{'quantity':'2'},{'fill_id':'$.fillId'}),step('cancel','撤余单',[check('$.status','CANCELED')],nums=nums if index==0 else [],purpose='action' if index==0 else 'setup')]
  if index:steps.append(step('reject','重复撤单拒绝',[check('$.code','ORDER_NOT_CANCELABLE')],nums=nums,purpose='action'))
  steps.extend([step('order','独立回查订单',[check('$.status','CANCELED'),check('$.executedQty','2',True),check('$.canceledQty','3',True),check('$.activeRemainingQty','0',True)],nums=nums,purpose='observe'),step('balances','查询资金截面',[check('$.free','979' if wrong_balance and index==0 else '980',True),check('$.locked','0',True)],nums=nums,purpose='observe'),step('events','核对完整事件累计',[check('$.spent','20',True),check('$.released','30',True)],nums=nums,purpose='observe'),step('cleanup','清理本例合成会话',[check('$.deleted',True)],purpose='cleanup')])
  result.append({'case_id':c['id'],'name':c['title'],'category':'business' if not index else 'negative','priority':'P0','coverage_ids':c['testpoint_ids'],'source_ids':[1],'rule_ids':c['rule_ids'],'preconditions':['每例自建合成会话'],'expected':c['expected_result'],'blocked_reason':'','steps':steps,'preparations':[{'item':'独立会话与显式成交','status':'documented','api_ids':[ids['session'],ids['place'],ids['fill']],'basis':'已登记同步本地契约'},{'item':'订单、余额、事件分别查询','status':'documented','api_ids':[ids['order'],ids['balances'],ids['events']],'basis':'三个HTTP观察接口，仅本地合成'},{'item':'证据完成后清理本例会话','status':'documented','api_ids':[ids['cleanup']],'basis':'仅清理本次session'}],'execution_gaps':[],'observation_limitations':['本地同进程合成内存，非独立生产账务或真实撮合证明']})
 return {'summary':'本地合成接口适配验收','scenarios':result}
