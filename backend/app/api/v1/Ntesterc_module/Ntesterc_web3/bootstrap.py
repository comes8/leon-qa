"""Add Web3 sources, prompts, fixtures and navigation to an existing local project."""
import asyncio
from io import BytesIO
from pathlib import Path
from sqlalchemy import select
from starlette.datastructures import UploadFile

from app.api.v1.Ntesterc_module.Ntesterc_project import project_platform_service as KB
from app.api.v1.Ntesterc_module.Ntesterc_project.model import KnowledgeBaseModel, KnowledgeDocumentModel, ProjectModel
from app.api.v1.Ntesterc_module.Ntesterc_intel.model import PromptConfigModel
from app.api.v1.Ntesterc_module.Ntesterc_api.model import ApiModel, ApiServiceModel, ApiMenuModel, ApiEnvironmentModel
from app.api.v1.system.menu.model import MenuModel
from app.api.v1.system.role.model import role_menu
from app.api.v1.system.user.model import user_role
from app.core.database import async_session_factory, engine
from .service import ensure_schema, PROMPT_NAMES

ROOT = Path(__file__).parent


async def provision(db, project_id, user_id):
    await KB._check_role(project_id, user_id, ['owner', 'admin', 'developer'], db)
    grouped = [
        ('币安现货参考规则 · 2026-11-20', 'Binance Spot 官方参考。具体公司项目需确认字段和规则映射。', ['01', '02', '03', '04']),
        ('币安 USDⓈ-M 合约参考规则 · 2026-11-20', 'Binance USDⓈ-M 官方参考。按持仓模式和合约产品核对。', ['05']),
        ('Web3 多业务模拟 · 现货合约资金DEX v1', 'Leon QA 本机可重复会话模拟。每个场景独立造数，区别于币安参考规则。', ['06', '07']),
    ]
    knowledge_ids = []
    for name, description, prefixes in grouped:
        kb_id = await db.scalar(select(KnowledgeBaseModel.id).where(
            KnowledgeBaseModel.project_id == project_id, KnowledgeBaseModel.name == name,
            KnowledgeBaseModel.enabled_flag == 1,
        ))
        if kb_id is None:
            kb_id = int((await KB.create_knowledge_base(project_id, user_id, db, {'name': name, 'description': description}))['data']['id'])
        knowledge_ids.append(kb_id)
        for prefix in prefixes:
            file = next((ROOT / 'data').glob(prefix + '-*.md'))
            content = file.read_text()
            title = content.splitlines()[0].lstrip('# ') + '.md'
            present = await db.scalar(select(KnowledgeDocumentModel.id).where(
                KnowledgeDocumentModel.knowledge_base_id == kb_id,
                KnowledgeDocumentModel.title == title, KnowledgeDocumentModel.enabled_flag == 1,
            ))
            if present is None:
                await KB.upload_document(project_id, user_id, kb_id, db, UploadFile(file=BytesIO(content.encode()), filename=title))
    for stage, name in PROMPT_NAMES.items():
        present = await db.scalar(select(PromptConfigModel.id).where(
            PromptConfigModel.name == name, PromptConfigModel.created_by == user_id, PromptConfigModel.enabled_flag == 1,
        ))
        if present is None:
            db.add(PromptConfigModel(name=name, prompt_type='reviewer' if stage == 'reviewer' else 'writer',
                content=(ROOT / 'prompts' / (stage + '.md')).read_text(), is_active=1, created_by=user_id, updated_by=user_id))
    service = await db.scalar(select(ApiServiceModel).where(
        ApiServiceModel.api_project_id == project_id, ApiServiceModel.name == 'Web3 多业务模拟 · 现货合约资金DEX',
        ApiServiceModel.enabled_flag == 1,
    ))
    if service is None:
        service = ApiServiceModel(name='Web3 多业务模拟 · 现货合约资金DEX', api_project_id=project_id,
                                  created_by=user_id, updated_by=user_id, description='每条用例先创建独立模拟会话。')
        db.add(service)
        await db.flush()
    folder = await db.scalar(select(ApiMenuModel).where(ApiMenuModel.api_service_id == service.id,
        ApiMenuModel.type == 1, ApiMenuModel.name == 'Web3 模拟接口', ApiMenuModel.enabled_flag == 1))
    if folder is None:
        folder = ApiMenuModel(name='Web3 模拟接口', type=1, pid=0, api_service_id=service.id,
                               status=1, created_by=user_id, updated_by=user_id)
        db.add(folder)
        await db.flush()
    origin = 'http://127.0.0.1:18171/api/v1/Ntesterc_web3/mock'
    catalogue = [
        ('创建独立模拟会话', 2, '/sessions', {}, '返回 201，提取 $.session_id，后续 URL 使用 {{session_id}}。'),
        ('现货下单', 2, '/{{session_id}}/spot/orders', {'quantity': '5', 'price': '10'}, '返回 201，提取 $.orderId 为 order_id。'),
        ('查询现货订单', 1, '/{{session_id}}/spot/orders/{{order_id}}', None, '查询同一订单状态、executedQty、remainingFrozen。'),
        ('模拟现货成交', 2, '/{{session_id}}/spot/orders/{{order_id}}/fills', {'quantity': '2'}, '显式生成模拟成交，不涉及真实撮合。'),
        ('撤销现货余单', 4, '/{{session_id}}/spot/orders/{{order_id}}', None, '撤余并按订单查询冻结和独立流水。'),
        ('查询独立现货流水', 1, '/{{session_id}}/spot/ledger/{{order_id}}', None, '返回 tradeQuantity、spent、released、free 和 locked。'),
        ('合约只减仓', 2, '/{{session_id}}/futures/position', {'quantity': '2', 'reduceOnly': True}, '初始 LONG 5，成功减仓 2 后为 3。'),
        ('查询合约仓位', 1, '/{{session_id}}/futures/position', None, '返回 side=LONG 和 quantity。'),
        ('资金划转', 2, '/{{session_id}}/funds/transfers', {'clientId': '{{run_id}}', 'quantity': '10'}, '同 clientId 同量重试返回相同 transferId。'),
        ('查询资金余额与笔数', 1, '/{{session_id}}/funds/transfers', None, '返回 wallet、futuresWallet、transferCount。'),
        ('获取 DEX 报价', 1, '/{{session_id}}/dex/quote', None, '返回 chainId=31337、quoteId=fixture-quote、minAmountOut=900。'),
        ('提交模拟 DEX 兑换', 2, '/{{session_id}}/dex/swaps', {'quoteId': 'fixture-quote', 'chainId': 31337, 'minAmountOut': '900'}, '提取 $.transactionHash 为 tx_hash。'),
        ('查询模拟链上回执与余额变化', 1, '/{{session_id}}/dex/receipts/{{tx_hash}}', None, '返回 status=0x1、amountOut=950、balanceDelta=950。'),
    ]
    for name, method, path, body, description in catalogue:
        present = await db.scalar(select(ApiModel.id).where(ApiModel.api_service_id == service.id,
            ApiModel.name == name, ApiModel.enabled_flag == 1))
        if present is not None:
            continue
        api = ApiModel(name=name, url=origin + path, description=description, api_service_id=service.id,
            document={'source': 'web3_mock_v1', 'scope': 'local_mock'},
            req={'method': method, 'body_type': 2, 'body': body, 'params': [], 'header': [],
                 'config': {'retry': 0, 'req_timeout': 5, 'res_timeout': 5, 'allow_redirects': False}},
            created_by=user_id, updated_by=user_id)
        db.add(api)
        await db.flush()
        db.add(ApiMenuModel(name=name, type=2, pid=folder.id, api_id=api.id, api_service_id=service.id,
                            status=1, created_by=user_id, updated_by=user_id))
    env_id = await db.scalar(select(ApiEnvironmentModel.id).where(ApiEnvironmentModel.name == 'Web3 本机模拟',
        ApiEnvironmentModel.created_by == user_id, ApiEnvironmentModel.enabled_flag == 1))
    if env_id is None:
        env = ApiEnvironmentModel(name='Web3 本机模拟', config=[], variable=[], created_by=user_id, updated_by=user_id)
        db.add(env)
        await db.flush()
        env_id = env.id
    menu = await db.scalar(select(MenuModel).where(MenuModel.path.in_(['/api-automation/web3', '/web3/requirements']), MenuModel.enabled_flag == 1))
    if menu is None:
        parent = await db.scalar(select(MenuModel.id).where(MenuModel.path == '/api-automation', MenuModel.enabled_flag == 1))
        menu = MenuModel(menu_name='Web3 测试工作台', menu_type='C', parent_id=parent or 0,
                         path='/api-automation/web3', component='testing/web3-workbench/index',
                         icon='ele-Connection', order_num=0, visible=1, status=1, is_frame=1, is_cache=1,
                         created_by=user_id, updated_by=user_id)
        db.add(menu)
        await db.flush()
        roles = (await db.scalars(select(user_role.c.role_id).where(user_role.c.user_id == user_id))).all()
        for role_id in roles:
            await db.execute(role_menu.insert().values(role_id=role_id, menu_id=menu.id))
    await db.commit()
    return {'project_id': project_id, 'knowledge_base_ids': knowledge_ids, 'service_id': service.id,
            'environment_id': env_id, 'mock_api_count': len(catalogue), 'prompts': list(PROMPT_NAMES.values())}


async def main():
    import main as application
    try:
        await ensure_schema()
        async with async_session_factory() as db:
            project = (await db.execute(select(ProjectModel.id, ProjectModel.owner_id).where(
                ProjectModel.name == 'Web3 QA 个人版 · 本地样例', ProjectModel.enabled_flag == 1,
            ))).one()
            print(await provision(db, project.id, project.owner_id))
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
