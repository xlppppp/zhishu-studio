"""Local evidence and review scope use no model or application execution."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from review_workflow import basic_checks,source_hashes,review_scope,review_disposition


class ReviewEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)

    def test_syntax_validation_never_executes_application(self):
        (self.root/'app.py').write_text("raise RuntimeError('never execute')\n")
        (self.root/'broken.py').write_text('def broken(\n')
        checks=basic_checks(self.root,lambda:None)
        self.assertEqual({item['command']:item['status'] for item in checks},{'syntax: app.py':'passed','syntax: broken.py':'failed'})

    def test_scope_distinguishes_local_changes_from_initial_or_sensitive_work(self):
        (self.root/'page.js').write_text('const color="red";');before=source_hashes(self.root)
        (self.root/'page.js').write_text('const color="blue";')
        self.assertEqual(review_scope(self.root,before,'iterate','窗口颜色'),{'mode':'changes','changedFiles':['page.js']})
        self.assertEqual(review_scope(self.root,before,'build','')['mode'],'full')
        (self.root/'auth.py').write_text('enabled=True')
        self.assertEqual(review_scope(self.root,before,'iterate','')['mode'],'full')

    def test_missing_evidence_and_failed_checks_cannot_be_advisory_only(self):
        report={'verdict':'changes_requested','findings':[{'severity':'medium'}],'checks':[{'status':'passed'}]}
        self.assertEqual(review_disposition(report,[]),'blocked')
        self.assertEqual(review_disposition(report,[{'status':'failed'}]),'blocked')
        report['findings']=[{'severity':'low'}]
        self.assertEqual(review_disposition(report,[]),'advisories')
        report['checks']=[{'status':'not_run'}]
        self.assertEqual(review_disposition(report,[]),'pending')
        report['findings']=[{'severity':'critical'}]
        self.assertEqual(review_disposition(report,[]),'blocked')

    def test_changes_requested_without_actionable_findings_remains_unverified(self):
        report={'verdict':'changes_requested','findings':[],'checks':[{'status':'passed'}]}
        self.assertEqual(review_disposition(report,[]),'pending')

    def test_dependency_and_secret_files_are_excluded(self):
        (self.root/'node_modules').mkdir();(self.root/'node_modules/broken.py').write_text('(')
        (self.root/'.env').write_text('fixture');(self.root/'app.py').write_text('ok=True')
        (self.root/'alias.py').symlink_to(self.root/'.env')
        self.assertEqual(set(source_hashes(self.root)),{'app.py'})

    def test_browser_caches_do_not_consume_review_budget_or_enter_review_copy(self):
        from model_workflow import ReviewCopy
        for name in ('.browsers','.npm-cache'):
            directory=self.root/name;directory.mkdir()
            with (directory/'download').open('wb') as stream:stream.truncate(60*1024*1024)
        (self.root/'public').mkdir();(self.root/'public/map.svg').write_text('<svg/>')
        (self.root/'.env.example').write_text('PORT=8000')
        self.assertEqual(set(source_hashes(self.root)),{'public/map.svg','.env.example'})
        review=ReviewCopy(self.root);self.addCleanup(review.close);copy=review.root
        self.assertFalse((copy/'.browsers').exists())
        self.assertTrue((copy/'public/map.svg').is_file())
