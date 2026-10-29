"""Appearance tasks cannot publish backend or script changes from their copies."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Store,Problem
from task_routes import StyleRun


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.store=Store(self.directory.name,[sys.executable,str(Path(__file__).with_name('fake_harness.py'))]);self.addCleanup(self.store.close)
        p=self.store.create({'name':'路由验证','requirements':'客户管理系统'})
        self.id=p['id']
        self.store.edit(self.id,{'baseVersion':0,'plan':{key:key+' 已确认设计' for key in ('prd','frontend','backend','database')}})
        self.store.approve(self.id,{'baseVersion':1})
        self.store.start(self.id,{'kind':'build'});self.store.work_once()
        self.original=self.store.load(self.id)
        self.store.accept(self.id,{'jobId':self.original['built_job']})
        self.workspace=self.store.directory(self.id)/'workspace'
        (self.workspace/'frontend').mkdir();(self.workspace/'frontend/styles.css').write_text('body{color:red}')
        (self.workspace/'backend').mkdir();(self.workspace/'backend/main.py').write_text('BACKEND_UNCHANGED')
        (self.workspace/'.env').write_text('SYNTHETIC_NOT_A_REAL_SECRET')
        (self.workspace/'preview.html').write_text('<style>body{color:red}</style><script>original()</script>')

    def test_analysis_materializes_prd_diagram_references_and_html_protocol(self):
        self.store.start(self.id,{'kind':'revise','note':'补充客户分配流程图','target':'PRD'})
        self.store.work_once();result=self.store.load(self.id)
        self.assertEqual(result['job']['status'],'completed')
        exchange=self.workspace/'.studio'/result['job']['id']
        self.assertEqual({p.name for p in (exchange/'skills').iterdir()},{'studio-analysis','create-prd','api-design-principles','mermaid-diagrams','frontend-design'})
        self.assertTrue((exchange/'skills/mermaid-diagrams/references/FLOWCHARTS.md').is_file())
        self.assertTrue((exchange/'skills/frontend-design/LICENSE.txt').is_file())
        self.assertTrue((exchange/'skills/api-design-principles/references/details.md').is_file())
        self.assertTrue((exchange/'skills/api-design-principles/LICENSE.txt').is_file())
        self.assertIn('<h2>',result['plan']['prd'])
        self.assertIn('class="mermaid"',result['plan']['prd'])

    def start_style(self,note='颜色改为蓝色',**fields):
        return self.store.start(self.id,{'kind':'iterate','route':'style','note':note,'target':'客户窗口',**fields})

    def test_style_success_updates_only_styles_and_requires_new_acceptance(self):
        self.start_style();self.store.work_once();result=self.store.load(self.id)
        self.assertEqual(result['job']['status'],'completed')
        self.assertIn('fixture style adjustment',(self.workspace/'frontend/styles.css').read_text())
        self.assertEqual((self.workspace/'backend/main.py').read_text(),'BACKEND_UNCHANGED')
        self.assertIsNone(result['accepted']);self.assertNotEqual(result['built_job'],self.original['built_job'])
        self.assertEqual(result['versions'],self.original['versions'])

    def test_backend_and_script_changes_are_rejected_without_mutating_original(self):
        for note in ('STYLE_OUT_OF_SCOPE','STYLE_SCRIPT_CHANGE'):
            with self.subTest(note=note):
                before=(self.workspace/'preview.html').read_bytes()
                self.start_style(note);self.store.work_once();result=self.store.load(self.id)
                self.assertEqual(result['job']['status'],'failed')
                self.assertEqual((self.workspace/'preview.html').read_bytes(),before)
                self.assertFalse((self.workspace/'backend.py').exists())
                self.assertEqual(result['built_job'],self.original['built_job'])
                self.assertEqual(result['accepted'],self.original['built_job'])

    def test_request_copy_excludes_business_context_and_only_one_skill_is_discovered(self):
        result=self.start_style();spec=self.store.claim()
        with StyleContext(self.workspace,Path(spec['request']),Path(spec['result'])) as run:
            request=json.loads(run.request.read_text())
            self.assertNotIn('plan',request);self.assertNotIn('requirements',request);self.assertNotIn('references',request)
            self.assertFalse((run.root/'backend').exists());self.assertFalse((run.root/'.env').exists())
            config=json.loads(run.patch.read_text())[0]['config']
            self.assertFalse(config['includeDefaultRoots'])
            self.assertEqual([p.name for p in (run.patch.parent/'skills').iterdir()],['frontend-style'])
            self.assertFalse(run.root.is_relative_to(self.workspace.resolve()))

    def test_html_only_style_task_preserves_script_and_updates_preview(self):
        (self.workspace/'frontend/styles.css').unlink()
        self.start_style();self.store.work_once()
        result=self.store.load(self.id)
        self.assertEqual(result['job']['status'],'completed')
        content=(self.workspace/'preview.html').read_text()
        self.assertIn('body{color:blue}',content)
        self.assertIn('<script>original()</script>',content)

    def test_style_idempotency_cannot_be_reused_as_business(self):
        request=uuid.uuid4().hex
        self.start_style(requestId=request)
        with self.assertRaisesRegex(Problem,'另一条意见'):
            self.store.start(self.id,{'kind':'iterate','route':'business','note':'颜色改为蓝色','target':'客户窗口','requestId':request})

    def test_legacy_worker_cannot_receive_style_tasks(self):
        with self.store.transaction():self.store.db.execute('INSERT INTO worker(id,pid,heartbeat,stop_requested) VALUES(1,123,0,0)')
        with self.assertRaisesRegex(Problem,'重启 Worker'):self.start_style()
        self.assertEqual(self.store.pending(self.id),[])

    def test_retry_keeps_explicit_style_route(self):
        self.start_style('STYLE_OUT_OF_SCOPE');self.store.work_once()
        failed=self.store.load(self.id)['job']['id']
        retried=self.store.retry(self.id,{'jobId':failed,'requestId':uuid.uuid4().hex})
        self.assertEqual(retried['submittedJob']['route'],'style')

    def test_model_escalation_does_not_apply_styles_or_change_approval(self):
        self.start_style('STYLE_NEEDS_BUSINESS');self.store.work_once()
        result=self.store.load(self.id)
        self.assertEqual(result['job']['status'],'failed')
        self.assertIn('需要业务开发',result['job']['message'])
        self.assertEqual(result['accepted'],self.original['built_job'])
        self.assertEqual((self.workspace/'frontend/styles.css').read_text(),'body{color:red}')

    def test_html_style_attributes_are_not_editable_css(self):
        self.start_style();spec=self.store.claim()
        with StyleContext(self.workspace,Path(spec['request']),Path(spec['result'])) as run:
            (run.root/'preview.html').write_text('<style onload="changed()">body{color:blue}</style><script>original()</script>')
            with self.assertRaisesRegex(ValueError,'HTML 结构或脚本'):run.apply()
        self.assertNotIn('onload',(self.workspace/'preview.html').read_text())

    def test_style_looking_text_inside_script_is_not_editable_css(self):
        original='<style>body{color:red}</style><script>const template="<style>safe</style>";</script>'
        (self.workspace/'preview.html').write_text(original)
        self.start_style();spec=self.store.claim()
        with StyleContext(self.workspace,Path(spec['request']),Path(spec['result'])) as run:
            (run.root/'preview.html').write_text(original.replace('safe','changed'))
            with self.assertRaisesRegex(ValueError,'HTML 结构或脚本'):run.apply()
        self.assertEqual((self.workspace/'preview.html').read_text(),original)

    def test_cleanup_failure_is_terminal_and_does_not_leave_an_accepted_build(self):
        self.start_style()
        original_close=StyleRun.close
        def close_then_fail(run):
            original_close(run)
            raise OSError('fixture cleanup failure')
        with patch('server.StyleRun.close',autospec=True,side_effect=close_then_fail):
            self.store.work_once()
        result=self.store.load(self.id)
        self.assertEqual(result['job']['status'],'failed')
        self.assertIn('清理失败',result['job']['message'])
        self.assertIsNone(result['accepted']);self.assertIsNone(result['built_job'])
        self.assertEqual(self.store.pending(self.id),[])

    def test_partial_transfer_failure_restores_original_css(self):
        (self.workspace/'frontend/second.css').write_text('p{color:red}')
        self.start_style();spec=self.store.claim()
        with StyleContext(self.workspace,Path(spec['request']),Path(spec['result'])) as run:
            for name in ('frontend/styles.css','frontend/second.css'):(run.root/name).write_text('body{color:blue}')
            original=run.replace;count=0
            def replace(path,content):
                nonlocal count
                count+=1
                if count==2:raise OSError('fixture transfer failure')
                original(path,content)
            with patch.object(run,'replace',side_effect=replace):
                with self.assertRaises(OSError):run.apply()
            self.assertEqual((self.workspace/'frontend/styles.css').read_text(),'body{color:red}')
            self.assertEqual((self.workspace/'frontend/second.css').read_text(),'p{color:red}')


class StyleContext:
    """Release each temporary style copy even when an assertion fails."""
    def __init__(self,workspace,request,result):self.run=StyleRun(workspace,request,result)
    def __enter__(self):return self.run
    def __exit__(self,*args):self.run.close()


if __name__=='__main__':unittest.main()
