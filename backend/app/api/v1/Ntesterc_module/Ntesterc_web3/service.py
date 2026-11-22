"""Web3 requirement analysis, reviewed plans, native API suites and evidence."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from time import monotonic
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx
import jmespath
from fastapi import HTTPException
from jsonpath_ng import parse as parse_jsonpath
from sqlalchemy import select, update

from app.api.v1.Ntesterc_module.Ntesterc_ai.llm_config.model import LLMConfigModel
from app.api.v1.Ntesterc_module.Ntesterc_api.model import (
    ApiCaseModel, ApiEnvironmentModel, ApiMenuModel, ApiModel, ApiScriptResultListModel,
    ApiScriptResultModel, ApiServiceModel, ApiSuiteModel,
)
from app.api.v1.Ntesterc_module.Ntesterc_api.service import ApiAutomationService
from app.api.v1.Ntesterc_module.Ntesterc_api.step_executor import StepExecutor, VariableContext
from app.api.v1.Ntesterc_module.Ntesterc_intel.model import AIModelConfigModel, PromptConfigModel
from app.api.v1.Ntesterc_module.Ntesterc_project.model import KnowledgeBaseModel, KnowledgeDocumentModel
from app.api.v1.Ntesterc_module.Ntesterc_project.service import ProjectService
from app.api.v1.Ntesterc_module.Ntesterc_project.project_platform_service import query_knowledge_base
from app.core.database import async_session_factory, engine
from .model import Web3WorkflowModel
from .schema import RequirementAnalysis, ScenarioPlan, PlanReview

ROOT = Path(__file__).parent
PROMPT_NAMES = {'analysis': 'Web3 · 需求分析 v1', 'writer': 'Web3 · 接口用例生成 v1', 'reviewer': 'Web3 · 接口用例评审 v1'}
BUSY = {'analyzing', 'generating', 'executing', 'publishing'}
METHODS = {1: 'GET', 2: 'POST', 3: 'PUT', 4: 'DELETE', 5: 'PATCH', 6: 'OPTIONS'}
from app.utils.redaction import redact
VARIABLE = re.compile(r'\{\{\s*([^{}]+?)\s*\}\}|\$\{([^{}]+)\}')

def now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def analysis_content(row):
    return {key: value for key, value in (row.analysis or {}).items() if not key.startswith('_')}


def preserve_version(row, action):
    """Keep bounded revision evidence out of subsequent model prompts."""
    history = (row.analysis or {}).get('_versions', [])
    snapshot = {'revision': row.revision, 'action': action, 'captured_at': now(),
                'analysis': analysis_content(row), 'draft': row.draft, 'review': row.review}
    row.analysis = {**(row.analysis or {}), '_versions': [*history, deepcopy(snapshot)][-5:]}


def resolve_rule_sources(items, citations):
    """Resolve unique rule IDs to the provided documents; never invent sources."""
    changes = []
    known = {source['source_id'] for source in citations}
    for item in items:
        fully_resolved = bool(item.rule_ids)
        for rule in item.rule_ids:
            pattern = r'(?<![A-Za-z0-9_-])' + re.escape(rule) + r'(?![A-Za-z0-9_-])'
            matches = [source['source_id'] for source in citations if re.search(pattern, source['content'])]
            fully_resolved = fully_resolved and len(matches) == 1
            if len(matches) == 1 and matches[0] not in item.source_ids:
                item.source_ids.append(matches[0])
                changes.append({'item': getattr(item, 'case_id', getattr(item, 'id', '')), 'rule': rule, 'source_id': matches[0]})
        invalid = set(item.source_ids) - known
        if invalid and fully_resolved:
            item.source_ids = [source_id for source_id in item.source_ids if source_id in known]
            changes.append({'item': getattr(item, 'case_id', getattr(item, 'id', '')), 'removed_unresolved_ids': sorted(invalid)})
    return changes


def step_url(url, path_variables):
    """Override registered path placeholders without changing the target origin."""
    if re.match(r'^https?://', url, re.I):
        start = url.find('/', url.index('://') + 3)
        start = len(url) if start == -1 else start
    else:
        base = VARIABLE.match(url)
        if base is None or url[base.end():base.end()+1] not in {'', '/'}:
            raise ValueError('目录 URL 必须以 http(s) 或独立的基础地址变量开头')
        start = base.end()
    end = min([pos for char in '?#' if (pos := url.find(char, start)) >= 0] or [len(url)])
    path = url[start:end]
    names = {a or b for a, b in VARIABLE.findall(path)}
    if not set(path_variables).issubset(names):
        raise ValueError('path_variables 只能替换目录 URL 路径中已有的变量')
    prefix, suffix = url[:start], url[end:]
    def replace(match):
        name = match.group(1) or match.group(2)
        if name not in path_variables:
            return match.group(0)
        value = str(path_variables[name])
        # Preserve references for the native variable resolver, encode literals.
        parts, last = [], 0
        for ref in VARIABLE.finditer(value):
            parts.extend([quote(value[last:ref.start()], safe=''), ref.group(0)])
            last = ref.end()
        parts.append(quote(value[last:], safe=''))
        return ''.join(parts)
    return prefix + VARIABLE.sub(replace, path) + suffix


async def ensure_schema():
    from .assets import ensure_assets_schema
    from .design_model import ensure_design_schema
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Web3WorkflowModel.__table__.create(conn, checkfirst=True))
    await ensure_assets_schema()
    await ensure_design_schema()


async def recover_interrupted():
    from .design_service import recover_design_jobs
    await recover_design_jobs()
    async with async_session_factory() as db:
        rows = (await db.scalars(select(Web3WorkflowModel).where(Web3WorkflowModel.status.in_(BUSY)))).all()
        for row in rows:
            row.failed_stage = row.status
            row.status = 'error'
            row.last_error = '服务重启中断任务。请检查已有证据，再重新发起对应步骤。'
        await db.commit()


def serialize(row):
    fields = ['id', 'project_id', 'service_id', 'environment_id', 'writer_id', 'reviewer_id', 'title',
              'requirement', 'scope', 'knowledge_base_ids', 'status', 'analysis', 'citations', 'draft',
              'review', 'approval', 'publication', 'executions', 'usage', 'last_error', 'failed_stage', 'revision']
    return {**{name: getattr(row, name) for name in fields},
            'created_at': row.creation_date.isoformat(), 'updated_at': row.updation_date.isoformat()}


async def owned(db, run_id, user_id):
    row = await db.scalar(select(Web3WorkflowModel).where(
        Web3WorkflowModel.id == run_id, Web3WorkflowModel.created_by == user_id,
        Web3WorkflowModel.enabled_flag == 1,
    ))
    if row is None:
        raise HTTPException(404, '测试任务不存在')
    await ProjectService._check_project_member(row.project_id, user_id, db)
    return row


async def catalogue(db, service_id):
    rows = (await db.scalars(select(ApiModel).where(
        ApiModel.api_service_id == service_id, ApiModel.enabled_flag == 1,
    ).order_by(ApiModel.id))).all()
    return {row.id: row for row in rows if (row.document or {}).get('source') != 'web3_workflow'}


def public_api(row):
    req = row.req or {}
    query = {item['key']: item.get('value') for item in req.get('params', []) if item.get('key') and item.get('status')}
    return redact({'api_id': row.id, 'name': row.name, 'method': METHODS.get(req.get('method', 1), 'GET'),
                   'url': row.url, 'query': query, 'body': req.get('body'),
                   'description': row.description or '', 'specification': row.document or {}})


async def options(db, project_id, user_id):
    await ProjectService._check_project_member(project_id, user_id, db)
    services = (await db.scalars(select(ApiServiceModel).where(
        ApiServiceModel.api_project_id == project_id, ApiServiceModel.enabled_flag == 1,
        ApiServiceModel.created_by == user_id,
    ))).all()
    environments = (await db.scalars(select(ApiEnvironmentModel).where(
        ApiEnvironmentModel.created_by == user_id, ApiEnvironmentModel.enabled_flag == 1,
    ))).all()
    knowledge = (await db.scalars(select(KnowledgeBaseModel).where(
        KnowledgeBaseModel.project_id == project_id, KnowledgeBaseModel.enabled_flag == 1,
        KnowledgeBaseModel.is_active == True,
    ))).all()
    models = (await db.scalars(select(AIModelConfigModel).where(
        AIModelConfigModel.created_by == user_id, AIModelConfigModel.enabled_flag == 1,
        AIModelConfigModel.is_active == 1, AIModelConfigModel.role.in_(['writer', 'reviewer']),
    ))).all()
    return {'services': [{'id': row.id, 'name': row.name} for row in services],
            'environments': [{'id': row.id, 'name': row.name} for row in environments],
            'knowledge_bases': [{'id': row.id, 'name': row.name, 'description': row.description} for row in knowledge],
            'models': [{'id': row.id, 'name': row.name, 'role': row.role} for row in models]}


async def create_workflow(db, body, user_id):
    await ProjectService._check_project_permission(body.project_id, user_id, ['owner', 'admin', 'developer', 'tester'], db)
    available = await options(db, body.project_id, user_id)
    for key, wanted in [('services', [body.service_id]), ('environments', [body.environment_id]),
                        ('knowledge_bases', body.knowledge_base_ids)]:
        if not set(wanted).issubset({item['id'] for item in available[key]}):
            raise HTTPException(400, f'所选配置不属于当前项目或用户 {key}')
    roles = {item['id']: item['role'] for item in available['models']}
    if roles.get(body.writer_id) != 'writer' or roles.get(body.reviewer_id) != 'reviewer':
        raise HTTPException(400, '请选择启用的 Writer 和 Reviewer 配置')
    row = Web3WorkflowModel(**body.model_dump(), created_by=user_id, updated_by=user_id, executions=[], usage=[])
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def claim(db, row, expected, target, revision=None):
    if revision is not None and row.revision != revision:
        raise HTTPException(409, '内容已更新，请刷新后重试')
    if row.status not in expected:
        raise HTTPException(409, f'当前状态 {row.status} 无法执行此操作')
    result = await db.execute(update(Web3WorkflowModel).where(
        Web3WorkflowModel.id == row.id, Web3WorkflowModel.status == row.status,
        Web3WorkflowModel.revision == row.revision,
    ).values(status=target, last_error=None, failed_stage=None))
    if result.rowcount != 1:
        raise HTTPException(409, '任务正在处理，请刷新')
    await db.commit()


async def retrieve(db, row):
    citations = {}
    for kb_id in row.knowledge_base_ids:
        found = await query_knowledge_base(row.project_id, row.created_by, kb_id, db, row.requirement, top_k=6)
        for item in found['data']['results']:
            metadata = item['metadata']
            document = await db.scalar(select(KnowledgeDocumentModel).where(
                KnowledgeDocumentModel.knowledge_base_id == kb_id,
                KnowledgeDocumentModel.title == metadata['document_title'],
                KnowledgeDocumentModel.enabled_flag == 1,
            ).order_by(KnowledgeDocumentModel.id.desc()))
            if document is None:
                continue
            citations[document.id] = {'source_id': document.id, 'knowledge_base_id': kb_id,
                'title': document.title, 'content': (document.content or '')[:8000],
                'sha256': hashlib.sha256((document.content or '').encode()).hexdigest(),
                'captured_at': now()}
    return list(citations.values())[:18]


async def model_json(db, role_id, stage, payload, schema, *, method_prompt=None):
    role = await db.scalar(select(AIModelConfigModel).where(
        AIModelConfigModel.id == role_id, AIModelConfigModel.enabled_flag == 1, AIModelConfigModel.is_active == 1,
    ))
    if role is None:
        raise ValueError('模型角色配置已停用')
    config = await db.scalar(select(LLMConfigModel).where(
        LLMConfigModel.id == role.llm_config_id, LLMConfigModel.enabled_flag == 1, LLMConfigModel.is_active == True,
    ))
    if config is None or not config.api_key:
        raise ValueError('角色引用的模型连接不可用，请检查 LLM 配置')
    prompt = None
    if method_prompt is None:
        prompt = await db.scalar(select(PromptConfigModel).where(
            PromptConfigModel.name == PROMPT_NAMES[stage], PromptConfigModel.enabled_flag == 1,
            PromptConfigModel.is_active == 1, PromptConfigModel.created_by == role.created_by,
        ).order_by(PromptConfigModel.id.desc()))
        if prompt is None:
            raise ValueError(f'请配置提示词 {PROMPT_NAMES[stage]}')
    prompt_content = method_prompt if method_prompt is not None else prompt.content
    endpoint = (config.base_url or '').rstrip('/')
    if not endpoint.endswith('/chat/completions'):
        if not re.search(r'/v\d+$', endpoint):
            endpoint += '/v1'
        endpoint += '/chat/completions'
    if urlsplit(endpoint).scheme not in {'http', 'https'}:
        raise ValueError('模型连接 URL 无效')
    payload = redact(payload)
    messages = [{'role': 'system', 'content': prompt_content + '\nJSON Schema\n' + json.dumps(schema.model_json_schema(), ensure_ascii=False)},
                {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]
    request = {'model': config.model_name or config.name, 'messages': messages, 'max_tokens': 11000,
               'stream': False, 'response_format': {'type': 'json_object'}}
    if 'deepseek' in request['model'].lower():
        request['thinking'] = {'type': 'disabled'}
    started = monotonic()
    totals = {}
    parsed = None
    for attempt in range(2):
        async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=20)) as client:
            response = await client.post(endpoint, headers={'Authorization': f'Bearer {config.api_key}'}, json=request)
        if response.status_code != 200:
            raise ValueError(f'模型请求 HTTP {response.status_code}，请检查连接、额度和模型参数')
        result = response.json()
        for key, value in (result.get('usage') or {}).items():
            if isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
        choice = (result.get('choices') or [{}])[0]
        text = (choice.get('message') or {}).get('content') or ''
        if choice.get('finish_reason') == 'length':
            raise ValueError('模型输出达到长度上限，请缩小本批需求范围')
        if text.startswith('```'):
            text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
        try:
            parsed = schema.model_validate_json(text)
            break
        except ValueError as exc:
            errors = exc.errors(include_input=False, include_url=False) if hasattr(exc, 'errors') else [{'msg': str(exc)}]
            details = json.dumps(errors[:12], ensure_ascii=False, default=str)
            if attempt:
                raise ValueError(f'模型结构校验失败 {details[:600]}') from exc
            request['messages'] = [*messages, {'role': 'assistant', 'content': text},
                {'role': 'user', 'content': '请修复以下结构错误，保留业务内容，只输出符合 Schema 的 JSON。错误 ' + details}]
    usage = {'stage': stage, 'model': request['model'], 'tokens': totals,
             'seconds': round(monotonic() - started, 2), 'prompt_id': prompt.id if prompt else None,
             'prompt_sha256': hashlib.sha256(prompt_content.encode()).hexdigest()}
    return parsed, usage


async def context(db, row):
    apis = await catalogue(db, row.service_id)
    env = await ApiAutomationService._load_env_vars(db, row.environment_id)
    return {'requirement': row.requirement, 'scope': row.scope, 'citations': row.citations or [],
            'apis': [public_api(api) for api in apis.values()], 'environment_variables': list(env) + ['run_id'],
            'engine_contract': ['URL 的 {{变量}} 或 ${变量} 自动使用本场景前序 extracts 和环境变量替换；path_variables 只是可选覆盖，不填不影响替换。',
                                '完整 JSON 变量引用保留数字和布尔类型，decimal_eq 精确比较数值字符串与数值。',
                                'HTTP 非 2xx 可按显式预期断言通过；网络异常和取值失败均判失败。']}


async def process(run_id, stage, user_id):
    async with async_session_factory() as db:
        row = await owned(db, run_id, user_id)
        try:
            if stage == 'analysis':
                row.citations = await retrieve(db, row)
                if not row.citations:
                    raise ValueError('当前所选知识库未命中规则，请补充规则或调整需求')
                output, usage = await model_json(db, row.writer_id, stage, await context(db, row), RequirementAnalysis)
                usage['source_resolution'] = resolve_rule_sources(output.coverage, row.citations)
                known = {item['source_id'] for item in row.citations}
                ids = [point.id for point in output.coverage]
                invalid = {point.id: sorted(set(point.source_ids) - known) for point in output.coverage if not set(point.source_ids).issubset(known)}
                if invalid:
                    raise ValueError('需求分析引用了不存在的文档 ID ' + json.dumps(invalid, ensure_ascii=False))
                row.analysis = output.model_dump()
                row.draft = None
                row.review = None
                row.revision += 1
                row.usage = [*(row.usage or []), usage]
                row.status = 'analysis_ready'
            elif stage in {'generate', 'revise'}:
                payload = await context(db, row)
                payload['analysis'] = analysis_content(row)
                if stage == 'revise':
                    payload.update({'previous_draft': row.draft, 'previous_review': row.review,
                                    'revision_instruction': '修正评审与技术校验问题，保留已正确的覆盖，遵守用户要求的场景数量和范围。'})
                output, usage = await model_json(db, row.writer_id, 'writer', payload, ScenarioPlan)
                usage['source_resolution'] = resolve_rule_sources(output.scenarios, row.citations)
                if row.draft:
                    preserve_version(row, stage)
                row.draft = output.model_dump()
                row.revision += 1
                row.usage = [*(row.usage or []), usage]
                await db.commit()
                await review_plan(db, row, payload)
                row.status = 'review_ready'
            elif stage == 'review':
                await review_plan(db, row, {**await context(db, row), 'analysis': analysis_content(row)})
                row.status = 'review_ready'
            elif stage == 'execute':
                await execute_plan(db, row)
            row.last_error = None
            row.failed_stage = None
        except Exception as exc:
            await db.rollback()
            row = await owned(db, run_id, user_id)
            row.status = 'error'
            row.failed_stage = stage
            row.last_error = redact(str(exc))[:1000] if isinstance(exc, (ValueError, HTTPException)) else f'{type(exc).__name__}，请检查本机服务状态后重试'
        await db.commit()


async def review_plan(db, row, payload):
    technical = await validate_plan(db, row)
    review, usage = await model_json(db, row.reviewer_id, 'reviewer', {**payload, 'draft': row.draft,
                                       'technical_validation': technical}, PlanReview)
    row.review = {**review.model_dump(), 'technical_issues': technical, 'reviewed_at': now()}
    row.usage = [*(row.usage or []), usage]


async def validate_plan(db, row):
    plan = ScenarioPlan.model_validate(row.draft)
    apis = await catalogue(db, row.service_id)
    sources = {item['source_id']: item for item in (row.citations or [])}
    coverage = {item['id']: item for item in row.analysis['coverage']}
    environment = await ApiAutomationService._load_env_vars(db, row.environment_id)
    problems = []
    for case in plan.scenarios:
        reasons = []
        if not case.steps or case.blocked_reason:
            reasons.append(case.blocked_reason or '没有可执行步骤')
        if not set(case.coverage_ids).issubset(coverage):
            reasons.append('覆盖项引用不存在')
        if any(coverage[key].get('needs_confirmation') for key in case.coverage_ids if key in coverage):
            reasons.append('该用例依赖待确认的业务规则')
        if not set(case.source_ids).issubset(sources):
            reasons.append('规则文档引用不存在')
        text = '\n'.join(sources[key]['content'] for key in case.source_ids if key in sources)
        missing_rules = [rule for rule in case.rule_ids if not re.search(r'(?<![A-Za-z0-9_-])' + re.escape(rule) + r'(?![A-Za-z0-9_-])', text)]
        if missing_rules:
            reasons.append('规则编号缺少来源 ' + ', '.join(missing_rules) + '，请在 source_ids 补充对应文档')
        defined = set(environment) | {'run_id'}
        for step in case.steps:
            api = apis.get(step.api_id)
            if api is None:
                reasons.append(f'{step.name} 引用了不存在的接口')
                continue
            req = api.req or {}
            if step.poll_attempts > 1 and req.get('method', 1) != 1:
                reasons.append('只有查询 GET 步骤可以轮询')
            checks = step.validators
            if not any(v.mode == 'jmespath' and v.check == 'status_code' and v.comparator == 'eq' and type(v.expect) is int for v in checks):
                reasons.append(f'{step.name} 缺少明确的 HTTP 状态码断言')
            if not any(v.mode == 'jsonpath' or (v.mode == 'jmespath' and v.check.startswith('body.')) for v in checks):
                reasons.append(f'{step.name} 缺少业务字段断言')
            try:
                url = step_url(api.url, step.path_variables)
            except ValueError as exc:
                reasons.append(f'{step.name} {exc}')
                url = api.url
            effective = [url, step.query if step.query is not None else req.get('params'),
                         step.body if step.body is not None else req.get('body'),
                         [v.expect for v in checks], req.get('header'),
                         {key: value for key, value in req.items() if key.startswith('auth_')}]
            variables = {VariableContext._normalize_key(a or b) for a, b in VARIABLE.findall(json.dumps(effective, ensure_ascii=False))}
            if variables - defined:
                reasons.append(f'{step.name} 使用未定义变量 {", ".join(sorted(variables - defined))}')
            for item in [*checks, *step.extracts]:
                expression = item.check if hasattr(item, 'check') else item.path
                mode = item.mode if hasattr(item, 'mode') else item.extract_type
                try:
                    parse_jsonpath(expression) if mode == 'jsonpath' else jmespath.compile(expression)
                except Exception:
                    reasons.append(f'{step.name} 的取值或断言表达式无效')
            defined.update(item.name for item in step.extracts)
        if reasons:
            problems.append({'case_id': case.case_id, 'severity': 'blocking', 'message': '；'.join(dict.fromkeys(reasons))})
    return problems


async def approve(db, row, body):
    if row.status != 'review_ready' or row.revision != body.revision:
        raise HTTPException(409, '请刷新并完成用例评审')
    cases = {case['case_id']: case for case in row.draft['scenarios']}
    if not set(body.case_ids).issubset(cases):
        raise HTTPException(400, '所选用例不存在')
    issues = await validate_plan(db, row)
    if any(item['case_id'] in body.case_ids for item in issues):
        raise HTTPException(400, '所选用例有技术阻塞，请编辑用例或调整选择')
    blocking = [item for item in row.review.get('issues', []) if item['severity'] == 'blocking' and item['case_id'] in body.case_ids]
    if blocking and not body.acknowledge_review:
        raise HTTPException(400, '请先处理 Reviewer 阻塞项，或勾选已复核并填写原因')
    if blocking and not body.note.strip():
        raise HTTPException(400, '请填写对评审阻塞项的复核原因')
    await claim(db, row, {'review_ready'}, 'publishing', body.revision)
    try:
        original = await catalogue(db, row.service_id)
        audit = {'created_by': row.created_by, 'updated_by': row.created_by}
        suite = ApiSuiteModel(name=f'Web3 · {row.title}'[:250], api_service_id=row.service_id, sort=0, **audit)
        folder = ApiMenuModel(name=f'Web3 任务 {row.id}', type=1, pid=0, api_service_id=row.service_id, status=1, **audit)
        db.add_all([suite, folder])
        await db.flush()
        published = []
        for cid in dict.fromkeys(body.case_ids):
            case = cases[cid]
            steps = []
            requests = {}
            for step in case['steps']:
                source = original[step['api_id']]
                req = deepcopy(source.req or {})
                if step.get('query') is not None:
                    req['params'] = [{'key': key, 'value': value, 'status': True} for key, value in step['query'].items()]
                if step.get('body') is not None:
                    req['body'] = step['body']
                req['config'] = {**(req.get('config') or {}), 'retry': 0, 'allow_redirects': False}
                url = step_url(source.url, step.get('path_variables') or {})
                api = ApiModel(name=step['name'], url=url, req=req, api_service_id=row.service_id,
                    document={'source': 'web3_workflow', 'workflow_id': row.id, 'source_api_id': source.id}, **audit)
                db.add(api)
                await db.flush()
                requests[str(api.id)] = fingerprint({'url': url, 'req': req})
                db.add(ApiMenuModel(name=step['name'], type=2, pid=folder.id, api_id=api.id,
                                     api_service_id=row.service_id, status=1, **audit))
                steps.append({'step_type': 'api', 'name': step['name'], 'enable': True,
                              'request': {'api_id': api.id}, 'extracts': step['extracts'],
                              'validators': step['validators'], 'poll_attempts': step['poll_attempts'],
                              'poll_interval': step['poll_interval']})
            native = ApiCaseModel(name=f'{cid} · {case["name"]}'[:250], description='规则 ' + ', '.join(case['rule_ids']),
                suite_id=suite.id, script=steps, status=0, step_rely=1,
                case_type={'positive': 1, 'negative': 2, 'boundary': 3}.get(case['category'], 5), **audit)
            db.add(native)
            await db.flush()
            published.append({'case_id': cid, 'native_case_id': native.id, 'name': case['name'],
                              'script_sha256': fingerprint(steps), 'request_sha256': requests})
        row.approval = {'approved_at': now(), 'approved_by': row.created_by, **body.model_dump()}
        row.publication = {'suite_id': suite.id, 'cases': published, 'published_at': now()}
        row.status = 'suite_ready'
        await db.commit()
    except Exception:
        await db.rollback()
        await db.execute(update(Web3WorkflowModel).where(Web3WorkflowModel.id == row.id).values(status='review_ready'))
        await db.commit()
        raise


async def verify_targets(db, row):
    if row.scope == 'binance_reference':
        raise HTTPException(400, '参考资料模式用于设计，请选择本机模拟或项目测试环境后执行')
    env = await ApiAutomationService._load_env_vars(db, row.environment_id)
    allowed = {item.strip().lower() for item in str(env.get('qa_allowed_hosts') or '').split(',') if item.strip()}
    environment_kind = env.get('qa_environment')
    if row.scope == 'project_qa' and (environment_kind not in {'qa', 'testnet'} or not allowed):
        raise HTTPException(400, '请在环境变量配置 qa_environment=qa 或 testnet，以及 qa_allowed_hosts 测试域名')
    for entry in (row.publication or {}).get('cases', []):
        case = await db.get(ApiCaseModel, entry['native_case_id'])
        if case is None or not case.enabled_flag or case.suite_id != row.publication['suite_id']:
            raise HTTPException(409, '已发布用例被移除或移动，请新建任务重新评审')
        if fingerprint(case.script) != entry.get('script_sha256'):
            raise HTTPException(409, '已发布步骤发生变化，请新建任务重新评审后执行')
        for step in case.script:
            api = await db.get(ApiModel, step['request']['api_id'])
            if api is None or not api.enabled_flag or api.api_service_id != row.service_id:
                raise HTTPException(409, '已发布接口不可用，请重新评审')
            if fingerprint({'url': api.url, 'req': api.req}) != entry.get('request_sha256', {}).get(str(api.id)):
                raise HTTPException(409, '已发布接口发生变化，请重新评审后执行')
            url = VariableContext(env).resolve(api.url)
            parsed = urlsplit(url)
            if row.scope == 'local_mock':
                if parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
                    raise HTTPException(400, '本机模拟用例包含外部地址，请检查接口目录')
            elif parsed.hostname not in allowed or parsed.hostname in {'api.binance.com', 'fapi.binance.com', 'dapi.binance.com', 'papi.binance.com'}:
                raise HTTPException(400, '接口地址没有匹配所选测试环境的允许域名')
            if parsed.scheme not in {'http', 'https'}:
                raise HTTPException(400, '接口地址缺少协议或环境变量')


async def execute_plan(db, row):
    await verify_targets(db, row)
    publication = row.publication or {}
    if not publication.get('cases'):
        raise ValueError('尚未发布可执行用例集')
    result_id = uuid4().int % (10 ** 15)
    env = await ApiAutomationService._load_env_vars(db, row.environment_id)
    env['run_id'] = uuid4().hex
    summary = ApiScriptResultListModel(result_id=result_id, name=f'Web3 · {row.title}', script=[],
        config={'env_id': row.environment_id, 'workflow_id': row.id}, result={}, api_service_id=row.service_id,
        created_by=row.created_by, updated_by=row.created_by)
    db.add(summary)
    await db.flush()
    receipt = {'result_id': str(result_id), 'started_at': now(), 'environment_id': row.environment_id,
               'scope': row.scope, 'cases': [], 'total_steps': 0, 'passed_steps': 0, 'failed_steps': 0, 'blocked_steps': 0}
    row.executions = [*(row.executions or []), deepcopy(receipt)]
    await db.commit()
    native_cases = []
    for entry in publication['cases']:
        case = await db.get(ApiCaseModel, entry['native_case_id'])
        if case is None or not case.enabled_flag:
            raise ValueError('已发布用例被移除，请重新生成')
        context_vars = VariableContext(env)
        async def log(_message):
            return None
        executor = StepExecutor(db, row.environment_id, row.created_by, str(result_id), context_vars, log, lambda: False)
        case_result = {**entry, 'steps': [], 'status': 'passed'}
        menu_id = uuid4().hex
        stopped = False
        for step in case.script:
            receipt['total_steps'] += 1
            if stopped:
                case_result['steps'].append({'name': step['name'], 'status': 'blocked', 'error': '前置步骤失败'})
                receipt['blocked_steps'] += 1
                continue
            result = await executor.execute(step)
            detail = redact(result.to_dict())
            detail['status'] = 'passed' if result.success else 'failed'
            case_result['steps'].append(detail)
            receipt['passed_steps' if result.success else 'failed_steps'] += 1
            db.add(ApiScriptResultModel(name=step['name'], uuid=uuid4().hex, menu_id=menu_id, result_id=result_id,
                status=1 if result.success else 0, req=detail['request'], res=detail['response'],
                created_by=row.created_by, updated_by=row.created_by))
            if not result.success:
                stopped = True
                case_result['status'] = 'failed'
        native_cases.append({'name': case.name, 'uuid': menu_id, 'script': case.script, 'config': {'env_id': row.environment_id},
                             'status': 1 if case_result['status'] == 'passed' else 0,
                             'pass': sum(item['status'] == 'passed' for item in case_result['steps']),
                             'fail': sum(item['status'] == 'failed' for item in case_result['steps'])})
        case.status = 1 if case_result['status'] == 'passed' else 2
        receipt['cases'].append(case_result)
        row.executions = [*(row.executions or [])[:-1], deepcopy(receipt)]
        await db.commit()
    receipt['passed_cases'] = sum(case['status'] == 'passed' for case in receipt['cases'])
    receipt['failed_cases'] = len(receipt['cases']) - receipt['passed_cases']
    receipt['finished_at'] = now()
    summary.result = {'total': receipt['total_steps'], 'pass': receipt['passed_steps'],
                      'fail': receipt['failed_steps'], 'blocked': receipt['blocked_steps'],
                      'percent': round(receipt['passed_steps'] / max(receipt['total_steps'], 1) * 100, 2)}
    summary.script = native_cases
    summary.end_time = datetime.now()
    db.add(ApiScriptResultModel(name='执行结束', uuid='', menu_id='', result_id=result_id, status=1, req={}, res={},
                                created_by=row.created_by, updated_by=row.created_by))
    row.executions = [*(row.executions or [])[:-1], receipt]
    row.status = 'passed' if not receipt['failed_cases'] else 'failed'
    await db.commit()
