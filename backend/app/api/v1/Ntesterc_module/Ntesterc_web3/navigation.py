"""Idempotent Web3 navigation migration, preserving existing role scope."""
from sqlalchemy import select
from app.api.v1.system.menu.model import MenuModel
from app.api.v1.system.role.model import role_menu


PAGES = [
    ('requirements', '需求与建模', 'Requirements', 'ele-Document'),
    ('testpoints', '测试点设计', 'Testpoints', 'ele-Aim'),
    ('cases', '用例与评审', 'Cases', 'ele-Checked'),
    ('scenarios', '接口场景', 'Scenarios', 'ele-Connection'),
    ('data', '测试数据', 'Data', 'ele-Coin'),
    ('debug', '接口调试', 'Debug', 'ele-Monitor'),
    ('execution', '执行中心', 'Execution', 'ele-Cpu'),
    ('reports', '报告与证据', 'Reports', 'ele-DataAnalysis'),
    ('assets', '知识与技能', 'Assets', 'ele-Collection'),
]


async def provision_navigation(db, user_id):
    legacy = await db.scalar(select(MenuModel).where(
        MenuModel.path == '/api-automation/web3', MenuModel.enabled_flag == 1))
    first = await db.scalar(select(MenuModel).where(
        MenuModel.path == '/web3/requirements', MenuModel.enabled_flag == 1))
    source = first or legacy
    if source is None:
        raise ValueError('缺少既有Web3菜单，不能推断角色授权范围')
    role_ids = set((await db.scalars(select(role_menu.c.role_id).where(role_menu.c.menu_id == source.id))).all())
    root = await db.scalar(select(MenuModel).where(MenuModel.path == '/web3', MenuModel.enabled_flag == 1))
    if root is None:
        root = MenuModel(menu_name='Web3 测试', menu_type='M', parent_id=0, path='/web3',
                         component='layout/routerView/parent', icon='ele-Connection', order_num=-1,
                         visible=1, status=1, is_frame=1, is_cache=1, created_by=user_id, updated_by=user_id)
        db.add(root)
        await db.flush()
    targets = [root]
    for index, (slug, title, component, icon) in enumerate(PAGES):
        row = first if slug == 'requirements' else await db.scalar(select(MenuModel).where(
            MenuModel.path == '/web3/' + slug, MenuModel.enabled_flag == 1))
        if row is None and slug == 'requirements':
            row = legacy
        if row is None:
            row = MenuModel(menu_type='C', visible=1, status=1, is_frame=1, is_cache=1,
                            created_by=user_id, updated_by=user_id)
            db.add(row)
        row.menu_name, row.parent_id, row.path = title, root.id, '/web3/' + slug
        row.component, row.icon, row.order_num = 'testing/web3-area/' + component, icon, index
        targets.append(row)
    await db.flush()
    for row in targets:
        present = set((await db.scalars(select(role_menu.c.role_id).where(role_menu.c.menu_id == row.id))).all())
        for role_id in sorted(role_ids - present):
            await db.execute(role_menu.insert().values(role_id=role_id, menu_id=row.id))
    return {'root_id': root.id, 'page_count': len(PAGES), 'inherited_role_ids': sorted(role_ids),
            'paths': [row.path for row in targets]}
