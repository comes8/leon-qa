from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
import httpx
from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.api.v1.Ntesterc_module.Ntesterc_web3 import assets as A, workspace_controller as C


class BundleSnapshotTests(unittest.TestCase):
    def pack(self, root):
        (root / 'cex-requirement-review/references').mkdir(parents=True)
        (root / 'prompts').mkdir()
        (root / 'README.md').write_text('# 本地资料\n[Skill](cex-requirement-review/SKILL.md)\n')
        (root / 'cex-requirement-review/SKILL.md').write_text(
            '---\nname: cex-requirement-review\ndescription: "业务分析方法"\n---\n# 需求分析\n[方法](references/method.md)\n')
        (root / 'cex-requirement-review/references/method.md').write_text('# 方法\n待确认不能写成已通过。\n')
        (root / 'prompts/P01-requirement.md').write_text('# 需求分析任务\n分析{{需求与资料}}，参考{{已知背景，可省略}}。\n')

    def test_root_level_skill_pack_and_all_prompt_variables_are_imported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); self.pack(root)
            result = A.scan_bundle(root)
            self.assertEqual(result['counts'], {'skills': 1, 'prompts': 1, 'references': 1, 'files': 4})
            self.assertEqual(result['prompts'][0]['variables'], ['需求与资料', '已知背景，可省略'])
            self.assertEqual(result['skills'][0]['execution_mode'], 'document_method')

    def test_snapshot_is_immutable_and_changed_source_requires_a_new_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); self.pack(root)
            first = A.scan_bundle(root)
            target = root / 'cex-requirement-review/references/method.md'
            target.write_text('# 新方法\n保留独立观察证据。\n')
            second = A.scan_bundle(root)
            self.assertNotEqual(first['manifest_sha256'], second['manifest_sha256'])
            self.assertIn('待确认', first['files']['cex-requirement-review/references/method.md']['content'])
            self.assertEqual(A.compare_snapshot(first, second)['modified'], ['cex-requirement-review/references/method.md'])

    def test_same_source_hash_is_deterministic_and_no_eval_or_script_is_imported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); self.pack(root)
            (root / 'evals').mkdir(); (root / 'evals/failure.md').write_text('historical failed example')
            (root / 'cex-requirement-review/run.sh').write_text('do not execute')
            first, second = A.scan_bundle(root), A.scan_bundle(root)
            self.assertEqual(first['manifest_sha256'], second['manifest_sha256'])
            self.assertFalse(any(p.startswith('evals/') or p.endswith('.sh') for p in first['files']))

    def test_missing_reference_is_rejected_instead_of_silently_losing_method(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); self.pack(root)
            (root / 'cex-requirement-review/references/method.md').unlink()
            with self.assertRaisesRegex(ValueError, '缺少本地引用'): A.scan_bundle(root)

    def test_file_and_reference_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); self.pack(root)
            reference = root / 'cex-requirement-review/references/method.md'
            reference.unlink(); reference.symlink_to(root / 'README.md')
            with self.assertRaisesRegex(ValueError, '符号链接'): A.scan_bundle(root)

    def test_relative_escape_in_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); self.pack(root)
            (root / 'cex-requirement-review/references/method.md').write_text('[private](../../../private.md)')
            with self.assertRaisesRegex(ValueError, '越界引用'): A.scan_bundle(root)

    def test_snapshot_lookup_never_reads_a_browser_supplied_disk_path(self):
        row = SimpleNamespace(snapshot={'files': {'allowed.md': {'content': 'only snapshot'}}})
        self.assertEqual(A.file_content(row, 'allowed.md')['content'], 'only snapshot')
        for path in ['../private', '/etc/passwd', 'a/../allowed.md', './allowed.md']:
            with self.subTest(path=path), self.assertRaises(HTTPException): A.file_content(row, path)
        with self.assertRaises(HTTPException): A.file_content(row, 'missing.md')

    def test_real_pack_counts_and_reference_contents(self):
        result = A.scan_bundle(A.SOURCE_ROOT)
        self.assertEqual(result['counts']['skills'], 9)
        self.assertEqual(result['counts']['prompts'], 14)
        self.assertEqual(result['counts']['references'], 25)
        self.assertEqual(len({s['key'] for s in result['skills']}), 9)
        self.assertTrue(all(s['integration'] == 'imported_not_bound' for s in result['skills']))


class BundleAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_project_membership_checked_before_private_bundle_query(self):
        db = SimpleNamespace(scalar=AsyncMock())
        with patch.object(A.ProjectService, '_check_project_member', new=AsyncMock(side_effect=HTTPException(403, 'denied'))):
            with self.assertRaises(HTTPException): await A.owned_bundle(db, 2, 10, 3)
        db.scalar.assert_not_awaited()

    async def test_bundle_query_is_scoped_to_user_and_project(self):
        db = SimpleNamespace(scalar=AsyncMock(return_value=None))
        with patch.object(A.ProjectService, '_check_project_member', new=AsyncMock()):
            with self.assertRaises(HTTPException) as error: await A.owned_bundle(db, 2, 10, 3)
        self.assertEqual(error.exception.status_code, 404)
        query = str(db.scalar.call_args.args[0].compile(compile_kwargs={'literal_binds': True}))
        self.assertIn('project_id = 2', query); self.assertIn('created_by = 10', query)

    async def test_source_preview_refuses_unregistered_project_and_never_scans_disk(self):
        with patch.object(A.ProjectService, '_check_project_permission', new=AsyncMock()), patch.object(A, 'list_bundles', new=AsyncMock(return_value=[])), patch.object(A, 'scan_bundle') as scan:
            with self.assertRaises(HTTPException): await A.source_preview(None, 2, 10)
            scan.assert_not_called()

    async def test_same_manifest_returns_original_bundle_without_inserting(self):
        original = SimpleNamespace(id=12)
        db = SimpleNamespace(scalar=AsyncMock(return_value=original), add=unittest.mock.Mock())
        with patch.object(A.ProjectService, '_check_project_permission', new=AsyncMock()):
            result, created = await A.import_snapshot(db, 1, 1, {'manifest_sha256': 'a' * 64})
        self.assertIs(result, original); self.assertFalse(created); db.add.assert_not_called()

    async def test_sync_rejects_changed_source_or_newer_baseline_before_writing(self):
        body = C.SyncAssets(project_id=1, baseline_id=2, manifest_sha256='a' * 64)
        with patch.object(A, 'source_preview', new=AsyncMock(return_value=(SimpleNamespace(id=3), {'manifest_sha256': 'b' * 64}, {}))), patch.object(A, 'import_snapshot', new=AsyncMock()) as write:
            with self.assertRaises(HTTPException) as error: await C.sync(body, None, 1)
            self.assertEqual(error.exception.status_code, 409); write.assert_not_awaited()

    async def test_http_route_has_authentication_and_does_not_accept_arbitrary_source(self):
        app = FastAPI(); app.include_router(C.router, prefix='/workspace')
        async def denied(): raise HTTPException(401, 'unauthorized')
        async def db(): yield None
        app.dependency_overrides[get_current_user_id] = denied; app.dependency_overrides[get_db] = db
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://local') as client:
            response = await client.get('/workspace/assets?project_id=1')
            self.assertEqual(response.status_code, 401)
        with self.assertRaises(ValueError): C.SyncAssets(project_id=1, baseline_id=2, manifest_sha256='a' * 64, source_root='/etc')


if __name__ == '__main__': unittest.main()
