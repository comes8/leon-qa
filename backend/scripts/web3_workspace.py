"""Import the approved local business pack and migrate Web3 navigation once."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main  # Register existing model mappings; does not run application startup.
from sqlalchemy import select
from app.core.database import async_session_factory, engine
from app.api.v1.Ntesterc_module.Ntesterc_project.model import ProjectModel
from app.api.v1.system.menu.model import MenuModel
from app.api.v1.system.role.model import role_menu
from app.api.v1.Ntesterc_module.Ntesterc_web3.assets import SOURCE_ROOT, ensure_assets_schema, import_snapshot, scan_bundle, bundle_summary
from app.api.v1.Ntesterc_module.Ntesterc_web3.navigation import provision_navigation


async def run(args):
    snapshot = scan_bundle(SOURCE_ROOT)
    if args.check:
        print(json.dumps({'counts': snapshot['counts'], 'manifest_sha256': snapshot['manifest_sha256']}, ensure_ascii=False))
        return
    await ensure_assets_schema()
    async with async_session_factory() as db:
        project = await db.scalar(select(ProjectModel).where(ProjectModel.id == args.project,
                                                            ProjectModel.enabled_flag == 1))
        if project is None:
            raise ValueError('项目不存在')
        rows = (await db.scalars(select(MenuModel).where(MenuModel.enabled_flag == 1))).all()
        before = [{'id': r.id, 'menu_name': r.menu_name, 'parent_id': r.parent_id, 'path': r.path,
                   'component': r.component, 'order_num': r.order_num, 'menu_type': r.menu_type,
                   'icon': r.icon, 'visible': r.visible, 'status': r.status,
                   'role_ids': list((await db.scalars(select(role_menu.c.role_id).where(role_menu.c.menu_id == r.id))).all())}
                  for r in rows if r.path in ['/api-automation/web3', '/web3'] or (r.path or '').startswith('/web3/')]
        out = Path(args.report_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)
        backup = out / 'navigation-before.json'
        if not backup.exists():
            backup.write_text(json.dumps(before, ensure_ascii=False, indent=2) + '\n')
        row, created = await import_snapshot(db, project.id, project.owner_id, snapshot)
        nav = await provision_navigation(db, project.owner_id)
        await db.commit()
        await db.refresh(row)
        result = {'bundle': bundle_summary(row), 'created': created, 'navigation': nav}
        (out / 'import-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(result, ensure_ascii=False))


async def main_cli():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=int, default=1)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--report-dir', default='../.runtime/web3-area-import')
    try:
        await run(parser.parse_args())
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main_cli())
