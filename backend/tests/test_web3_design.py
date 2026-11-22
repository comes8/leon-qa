from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch
from fastapi import HTTPException
from app.api.v1.Ntesterc_module.Ntesterc_web3 import design_service as S,design_schema as D,assets as A
from tests.design_fixtures import ANALYSIS,MODEL,POINTS,CASES,REVIEW,REF

def artifact(id,parents=None,input_revision=1,confirmation=True):
 return SimpleNamespace(id=id,parent_ids=parents or {},input_revision=input_revision,confirmation={'note':'已复核'} if confirmation else None)
def snapshot(stage='testpoints'):
 return {'request':{'max_items':8,'item_ids':[],'case_testpoint_ids':[],'prompt_key':'P05'},
 'payload':{'sources':[{'source_id':'SRC-REQ','kind':'requirement'}],'upstream':{
 'analysis':{'content':deepcopy(ANALYSIS)},'modeling':{'content':deepcopy(MODEL)},'testpoints':{'content':deepcopy(POINTS)},'cases':{'content':deepcopy(CASES)}}}}

class DesignContractTests(unittest.TestCase):
 def test_design_input_needs_no_api_service_environment_or_url(self):
  body=D.CreateDesign(project_id=1,request_key='test-task-001',title='业务设计',requirement='现货部分成交后撤单，只开展业务设计',bundle_id=1,writer_id=1,reviewer_id=2)
  self.assertFalse(hasattr(body,'service_id'));self.assertFalse(hasattr(body,'environment_id'))
 def test_executable_fields_are_not_accepted_in_business_design(self):
  with self.assertRaises(ValueError):D.CreateDesign(project_id=1,request_key='test-task-001',title='业务设计',requirement='现货部分成交后撤单，只开展业务设计',bundle_id=1,writer_id=1,reviewer_id=2,command='echo unsafe')
  data=deepcopy(CASES);data['cases'][0]['steps'][0]['api_id']=1
  with self.assertRaises(ValueError):S.validate_output('cases',data,snapshot())
 def test_unknown_source_and_rule_cannot_become_valid_output(self):
  for key,value in [('source_refs',[{'source_id':'missing','locator':'not real'}]),('rule_ids',['RUL-missing']),('model_ids',['INV-missing'])]:
   data=deepcopy(POINTS);data['testpoints'][0][key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):S.validate_output('testpoints',data,snapshot())
 def test_duplicate_ids_are_rejected(self):
  data=deepcopy(POINTS);data['testpoints'][1]['id']='TP-1'
  with self.assertRaisesRegex(ValueError,'重复'):S.validate_output('testpoints',data,snapshot())
 def test_uncertain_rule_cannot_support_ready_testpoint(self):
  snap=snapshot();snap['payload']['upstream']['analysis']['content']['rules'][0]['evidence_kind']='proposed'
  with self.assertRaisesRegex(ValueError,'未确认'):S.validate_output('testpoints',POINTS,snap)
 def test_unknown_observation_is_not_implementation_evidence(self):
  data=deepcopy(ANALYSIS);data['rules'][0]['evidence_kind']='observed'
  with self.assertRaisesRegex(ValueError,'实现观察'):S.validate_output('analysis',data,snapshot())
 def test_missing_entity_in_state_transition_is_rejected(self):
  data=deepcopy(MODEL);data['transitions'][0]['entity_id']='MISSING'
  with self.assertRaisesRegex(ValueError,'业务对象'):S.validate_output('modeling',data,snapshot())
 def test_review_cannot_cite_nonexistent_target(self):
  data=deepcopy(REVIEW);data['issues']=[{'id':'REV-1','target_ids':['TP-missing'],'category':'错误预期','severity':'important','problem':'x','consequence':'x','suggestion':'x','source_refs':REF}]
  with self.assertRaisesRegex(ValueError,'目标'):S.validate_output('testpoint_review',data,snapshot())
 def test_cases_can_only_expand_selected_testpoints(self):
  snap=snapshot();snap['request']['case_testpoint_ids']=['TP-1']
  with self.assertRaisesRegex(ValueError,'未选择'):S.validate_output('cases',CASES,snap)
 def test_partial_patch_preserves_unselected_rows_and_original_input(self):
  original=deepcopy(POINTS);row=deepcopy(POINTS['testpoints'][0]);row['expected']='指定条目修订后的预期'
  result=S.merge_patch('testpoints',POINTS,{'summary':'仅修订TP-1','testpoints':[row]},['TP-1'])
  self.assertEqual(result['testpoints'][1],original['testpoints'][1]);self.assertEqual(POINTS,original);self.assertEqual(result['testpoints'][0]['id'],'TP-1')
 def test_partial_patch_cannot_rename_or_expand_selection(self):
  row=deepcopy(POINTS['testpoints'][0]);row['id']='NEW-ID'
  with self.assertRaises(ValueError):S.merge_patch('testpoints',POINTS,{'summary':'bad','testpoints':[row]},['TP-1'])
 def test_incremental_prompt_cannot_remove_prior_testpoints(self):
  snap=snapshot();snap['request']['prompt_key']='P06';snap['payload']['previous']=deepcopy(POINTS)
  data=deepcopy(POINTS);data['testpoints']=data['testpoints'][:1]
  with self.assertRaisesRegex(ValueError,'移除'):S.validate_output('testpoints',data,snap)
 def test_upstream_change_marks_descendants_stale_even_if_confirmed(self):
  task=SimpleNamespace(input_revision=1,heads={'analysis':1,'modeling':2,'testpoints':3})
  artifacts={'analysis':artifact(1),'modeling':artifact(2,{'analysis':1}),'testpoints':artifact(3,{'analysis':1,'modeling':2})}
  self.assertTrue(S.freshness(task,artifacts)['testpoints']);task.heads['analysis']=4;artifacts['analysis']=artifact(4)
  fresh=S.freshness(task,artifacts);self.assertTrue(fresh['analysis']);self.assertFalse(fresh['modeling']);self.assertFalse(fresh['testpoints']);self.assertTrue(artifacts['testpoints'].confirmation)
 def test_input_revision_change_invalidates_all_old_artifacts(self):
  task=SimpleNamespace(input_revision=2,heads={'analysis':1})
  self.assertFalse(S.freshness(task,{'analysis':artifact(1)})['analysis'])
 def test_optional_requirement_review_invalidates_modeling_when_added(self):
  task=SimpleNamespace(input_revision=1,heads={'analysis':1,'requirement_review':3,'modeling':2})
  values={'analysis':artifact(1),'requirement_review':artifact(3,{'analysis':1}),'modeling':artifact(2,{'analysis':1})}
  self.assertFalse(S.freshness(task,values)['modeling'])
 def test_regression_can_use_confirmed_old_case_baseline_with_current_analysis(self):
  task=SimpleNamespace(input_revision=2,heads={'analysis':10,'cases':5,'case_review':6,'regression':11})
  values={'analysis':artifact(10,input_revision=2),'cases':artifact(5,{'analysis':1}),
   'case_review':artifact(6,{'analysis':1,'cases':5}),
   'regression':artifact(11,{'analysis':10,'cases':5,'case_review':6},input_revision=2)}
  fresh=S.freshness(task,values)
  self.assertFalse(fresh['cases']);self.assertTrue(S.dependency_available('regression','cases',values,fresh));self.assertTrue(fresh['regression'])
  values['case_review'].parent_ids['cases']=4
  self.assertFalse(S.freshness(task,values)['regression']);self.assertFalse(S.dependency_available('regression','case_review',values,fresh))
 def test_regression_missing_case_baseline_is_a_blocker_not_server_error(self):
  self.assertFalse(S.dependency_available('regression','case_review',{'case_review':artifact(6)},{}))
 def test_method_package_loads_selected_methods_and_complete_references_only(self):
  bundle=SimpleNamespace(id=1,manifest_sha256='a'*64,snapshot=A.scan_bundle(A.SOURCE_ROOT))
  result=S.method_package(bundle,'testpoints','P05',['cex-spot-matching'])
  self.assertEqual({s['key'] for s in result['skills']},{'cex-testpoint-design','cex-spot-matching'})
  self.assertTrue(any('/references/' in f['path'] for f in result['files']));self.assertFalse(any('futures-risk/' in f['path'] for f in result['files']))
  self.assertNotIn('{{原始需求',result['system_prompt'])
 def test_corrupted_asset_snapshot_and_wrong_stage_prompt_are_rejected(self):
  snap=A.scan_bundle(A.SOURCE_ROOT);bundle=SimpleNamespace(id=1,manifest_sha256='a'*64,snapshot=snap)
  with self.assertRaises(HTTPException):S.method_package(bundle,'analysis','P09',[])
  snap['files']['cex-requirement-review/SKILL.md']['content']+='tampered'
  with self.assertRaises(HTTPException):S.method_package(bundle,'analysis','P01',[])
 def test_task_writes_require_revision_and_no_running_job(self):
  for revision,busy in [(2,None),(1,100)]:
   with self.subTest(revision=revision,busy=busy),self.assertRaises(HTTPException):S.writable(SimpleNamespace(revision=revision,busy_job_id=busy),1)

class DesignGuardTests(unittest.IsolatedAsyncioTestCase):
 async def test_revise_decision_requires_explicit_disposition_even_without_blocking_issue(self):
  value=artifact(1,confirmation=False);value.stage='testpoint_review';value.content={**deepcopy(REVIEW),'decision':'revise'}
  task=SimpleNamespace(id=1,heads={'testpoint_review':1},input_revision=1,revision=1,busy_job_id=None)
  body=D.ConfirmArtifact(expected_revision=1,artifact_id=1,note='需要先记录意见处置依据')
  with patch.object(S,'head_artifacts',new=AsyncMock(return_value={'testpoint_review':value})),patch.object(S,'freshness',return_value={'testpoint_review':True}):
   with self.assertRaises(HTTPException) as error:await S.confirm_artifact(None,task,body,1)
  self.assertEqual(error.exception.status_code,400);self.assertIsNone(value.confirmation)
 async def test_manual_validation_message_does_not_echo_user_input(self):
  from app.api.v1.Ntesterc_module.Ntesterc_web3.design_controller import invalid_artifact
  try:D.AnalysisOutput.model_validate({'summary':'private-value-must-not-appear'})
  except ValueError as error:
   result=invalid_artifact(error);self.assertEqual(result.status_code,400);self.assertNotIn('private-value-must-not-appear',result.detail);self.assertIn('requirements',result.detail)
 async def test_unconfirmed_upstream_cannot_generate(self):
  task=SimpleNamespace(id=1,heads={'analysis':1},input_revision=1)
  body=D.StageRequest(expected_revision=1,request_key='test-run-001',stage='modeling',prompt_key='P03')
  with patch.object(S,'head_artifacts',new=AsyncMock(return_value={'analysis':artifact(1,confirmation=False)})):
   with self.assertRaises(HTTPException) as error:await S.prepare(None,task,body,1)
  self.assertEqual(error.exception.status_code,409)
 async def test_original_confirmation_is_not_overwritten(self):
  value=artifact(1);value.stage='analysis';value.content=ANALYSIS
  task=SimpleNamespace(id=1,heads={'analysis':1},input_revision=1,revision=1,busy_job_id=None)
  body=D.ConfirmArtifact(expected_revision=1,artifact_id=1,note='试图覆盖原始复核记录')
  with patch.object(S,'head_artifacts',new=AsyncMock(return_value={'analysis':value})):
   with self.assertRaises(HTTPException):await S.confirm_artifact(None,task,body,1)
  self.assertEqual(value.confirmation,{'note':'已复核'})

if __name__=='__main__':unittest.main()
