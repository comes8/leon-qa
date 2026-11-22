"""Synthetic design documents for deterministic contract checks, never execution evidence."""
from copy import deepcopy

REF=[{'source_id':'SRC-REQ','locator':'合成需求：撤单与余额守恒'}]
COMMON={'summary':'合成业务设计，不是执行结果','readiness':'ready','notes':[],'questions':[]}
ANALYSIS={**COMMON,'requirements':[{'id':'REQ-1','goal':'撤单后余额守恒','source_refs':REF}],
 'rules':[{'id':'RUL-1','statement':'未成交部分只能释放一次','scope':'本地合成设计','evidence_kind':'stated','source_refs':REF,'unresolved':[]}],
 'risks':[],'acceptance':[]}
MODEL={**COMMON,'entities':[{'id':'MOD-1','name':'订单','states':['NEW','CANCELED'],'observation':'待准备的独立订单观察','source_refs':REF}],
 'transitions':[{'id':'TR-1','entity_id':'MOD-1','from_state':'NEW','event':'撤单生效','guard':'订单有效','to_state':'CANCELED','effect':'活动余量归零','observation':'订单与资金分别观察','rule_ids':['RUL-1'],'source_refs':REF}],
 'invariants':[{'id':'INV-1','condition':'合成金额1000、支出20','formula_or_property':'980+20=1000','units_and_phase':'QUOTE / 资金释放完成后','independent_evidence':'独立账户与流水观察能力需准备','rule_ids':['RUL-1'],'source_refs':REF}]}
def point(id,title):return {'id':id,'title':title,'rule_ids':['RUL-1'],'model_ids':['INV-1'],'source_refs':deepcopy(REF),
 'conditions':['本地合成数据、原量5、已成交2'],'trigger':'撤余单','expected':'支出20，释放30，最终980/0','verification':'分别核对订单、独立余额和流水','priority':'P0',
 'design_readiness':'ready','execution_readiness':'needs_preparation','unresolved':[]}
POINTS={**COMMON,'testpoints':[point('TP-1','部分成交后撤余单'),point('TP-2','重复撤单不重复释放')]}
def case(id,tp):return {'id':id,'title':'业务用例 '+id,'testpoint_ids':[tp],'rule_ids':['RUL-1'],'source_refs':deepcopy(REF),
 'preconditions':['独立合成数据'],'data':['数量5，已成交2，价格10'],'steps':[{'action':'撤余单','expected':'订单终态CANCELED，资金完成后980/0','observation':'订单、余额及独立流水'}],
 'expected_result':'无重复释放','cleanup':['仅清理本次隔离夹具'],'priority':'P0','design_readiness':'ready','execution_readiness':'needs_preparation','unresolved':[]}
CASES={**COMMON,'cases':[case('TC-1','TP-1'),case('TC-2','TP-2')]}
REVIEW={**COMMON,'decision':'continue','reviewed_scope':'仅本次合成业务设计','issues':[],'missing_coverage':[],'execution_gaps':['执行环境与观察接口待准备']}
SPECIAL={**COMMON,'findings':[{'id':'FIND-1','risk':'重复解冻风险','impact':'金额错误','source_refs':REF}],'invariants':MODEL['invariants']}
REGRESSION={**COMMON,'impacts':[{'id':'IMP-1','risk':'解冻规则变化','impact':'资金核对范围变化','source_refs':REF}],
 'selection':[{'case_id':'TC-1','disposition':'reuse','reason':'覆盖原资金判据','prerequisites':['确认新旧规则差异'],'source_refs':REF}], 'remaining_risks':['缺少真实执行环境']}
OUTPUTS={'analysis':ANALYSIS,'modeling':MODEL,'testpoints':POINTS,'cases':CASES,'regression':REGRESSION,
 **{s:REVIEW for s in ['requirement_review','testpoint_review','case_review']},**{s:SPECIAL for s in ['spot','futures','funds']}}
