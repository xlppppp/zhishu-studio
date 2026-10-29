"""Check workflow guards and process outcomes without model calls or shared state."""

import io
import os
import select
import signal
import subprocess
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Handler, Problem, Store, ThreadingHTTPServer, resolve_runtime, validate_plan
from worker import Worker


class RuntimeTests(unittest.TestCase):
    """Source selection must preserve workspace cwd and the ESM-only hook."""

    def test_disconnected_browser_does_not_trigger_a_second_error_response(self):
        from unittest.mock import Mock
        for failure in (ConnectionResetError,BrokenPipeError,ConnectionAbortedError):
            handler=object.__new__(Handler)
            handler.send_response=Mock();handler.send_header=Mock();handler.end_headers=Mock()
            handler.wfile=Mock();handler.wfile.write.side_effect=failure('client left')
            handler.send({'result':'already saved'})
            self.assertTrue(handler.close_connection)
            self.assertEqual(handler.send_response.call_count,1)

    def test_adjacent_source_uses_absolute_entry_and_tsconfig(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = root / "apps/cli/src/bin.ts"
            entry.parent.mkdir(parents=True)
            entry.write_text("// fixture")
            tsx = root / "node_modules/tsx"
            (tsx / "dist/esm").mkdir(parents=True)
            (tsx / "package.json").write_text(json.dumps({"exports": {"./esm": "./dist/esm/index.mjs"}}))
            (tsx / "dist/esm/index.mjs").write_text("// fixture")
            with patch("server.shutil.which", return_value="/test/node"):
                command, environment, source, issue = resolve_runtime(root, {})
            self.assertEqual(command, ["/test/node", "--import", str(tsx.resolve() / "dist/esm/index.mjs"), str(entry.resolve())])
            self.assertEqual(environment["TSX_TSCONFIG_PATH"], str(root.resolve() / "tsconfig.base.json"))
            self.assertEqual(source, "source")
            self.assertIsNone(issue)

    def test_source_without_dependencies_does_not_silently_use_global_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = root / "apps/cli/src/bin.ts"
            entry.parent.mkdir(parents=True)
            entry.touch()
            with patch("server.shutil.which", return_value="/test/node"):
                command, _, source, issue = resolve_runtime(root, {})
            self.assertEqual(command, [])
            self.assertEqual(source, "source")
            self.assertIn("pnpm install", issue)

    def test_explicit_command_takes_priority(self):
        with patch("server.shutil.which", return_value="/test/custom"):
            command, environment, source, issue = resolve_runtime("/unused", {"STUDIO_DSH_COMMAND": '"/custom path/dsh" --patch /config.yml'})
        self.assertEqual(command, ["/custom path/dsh", "--patch", "/config.yml"])
        self.assertEqual(environment, {})
        self.assertEqual(source, "custom")
        self.assertIsNone(issue)


class WorkflowTests(unittest.TestCase):
    """Each case owns a private store and joins its subprocess workers."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Store(self.directory.name, [sys.executable, str(Path(__file__).with_name("fake_harness.py"))])
        self.addCleanup(self.store.close)
        self.project = self.store.create({"name": "测试项目", "requirements": "需要一个客户管理系统"})
        self.id = self.project["id"]
        self.plan = {key: f"{key} 业务设计" for key in ("prd", "frontend", "backend", "database")}

    def save_plan(self):
        return self.store.edit(self.id, {"plan": self.plan, "baseVersion": 0})

    def wait(self):
        self.store.work_once()
        return self.store.load(self.id)

    def test_direct_edit_retains_history_and_invalidates_approval(self):
        self.save_plan()
        self.store.approve(self.id, {"baseVersion": 1})
        updated = dict(self.plan, prd="客户按部门隔离")
        result = self.store.edit(self.id, {"plan": updated, "baseVersion": 1})
        self.assertIsNone(result["approved"])
        self.assertEqual(result["versions"][0]["plan"], self.plan)
        self.assertEqual(result["versions"][1]["plan"], updated)

    def test_stale_editor_cannot_overwrite_newer_version(self):
        self.save_plan()
        with self.assertRaises(Problem):
            self.store.edit(self.id, {"plan": dict(self.plan, prd="旧标签页修改"), "baseVersion": 0})
        self.assertEqual(self.store.load(self.id)["plan"], self.plan)

    def test_placeholder_cannot_be_approved_or_used_by_legacy_approval(self):
        from server import fingerprint
        placeholder=dict(self.plan,prd='产品需求 PRD\n\n待填写：请点击「编辑原文」完善这一部分。')
        self.store.edit(self.id,{'plan':placeholder,'baseVersion':0})
        with self.assertRaisesRegex(Problem,'完善占位草稿'):
            self.store.approve(self.id,{'baseVersion':1})
        with self.store.transaction():
            data=self.store.load(self.id);data['approved']=fingerprint(placeholder);self.store.save(data)
        with self.assertRaisesRegex(Problem,'完善占位草稿'):
            self.store.start(self.id,{'kind':'build'})
        self.assertEqual(self.store.pending(self.id),[])

    def test_stale_review_cannot_approve(self):
        self.save_plan()
        with self.assertRaises(Problem):
            self.store.approve(self.id, {"baseVersion": 0})
        self.assertIsNone(self.store.load(self.id)["approved"])

    def test_analysis_persists_validated_result(self):
        self.store.start(self.id, {"kind": "analyze"})
        data = self.wait()
        self.assertEqual(data["job"]["status"], "completed")
        self.assertEqual(set(data["plan"]), set(self.plan))
        self.assertEqual(len(data["versions"]), 1)
        self.assertEqual(data["job"]["exitCode"], 0)

    def test_feedback_is_bound_to_target_and_version(self):
        self.save_plan()
        self.store.start(self.id, {"kind": "revise", "note": "增加部门字段", "target": "数据库设计"})
        data = self.wait()
        self.assertEqual(data["job"]["status"], "completed")
        self.assertEqual(data["feedback"][0]["target"], "数据库设计")
        self.assertEqual(data["feedback"][0]["version"], 1)
        self.assertEqual(len(data["versions"]), 2)

    def test_build_requires_approved_design(self):
        self.save_plan()
        with self.assertRaises(Problem):
            self.store.start(self.id, {"kind": "build"})

    def test_export_requires_complete_delivery_files_and_excludes_secrets(self):
        self.save_plan()
        self.store.approve(self.id, {"baseVersion": 1})
        self.store.start(self.id, {"kind": "build"})
        data = self.wait()
        self.assertEqual(data["job"]["status"], "completed")
        with self.assertRaises(Problem):
            self.store.bundle(self.id)
        with self.assertRaises(Problem):
            self.store.accept(self.id, {"jobId": "stale-job"})
        self.store.accept(self.id, {"jobId": data["job"]["id"]})
        workspace = self.store.directory(self.id) / "workspace"
        (workspace / ".env").write_text("not-for-export")
        (workspace / "server.key").write_text("not-for-export")
        (workspace / "link.txt").symlink_to(workspace / ".env")
        (workspace / "node_modules").mkdir()
        (workspace / "node_modules" / "module.js").write_text("dependency")
        databases=['customers.db','customers.sqlite','customers.sqlite3','customers.db-wal','customers.db-shm','customers.db-journal','customers.sqlite3-wal','CUSTOMERS.SQLITE3-SHM']
        for name in databases:(workspace/name).write_text('SYNTHETIC_QA_ONLY')
        (workspace/'database.py').write_text('# schema implementation')
        with zipfile.ZipFile(io.BytesIO(self.store.bundle(self.id))) as archive:
            files = archive.namelist()
        self.assertIn('source/database.py',files)
        for name in databases:self.assertNotIn('source/'+name,files)
        self.assertIn("source/.env.example", files)
        self.assertNotIn("source/.env", files)
        self.assertNotIn("source/server.key", files)
        self.assertNotIn("source/link.txt", files)
        self.assertNotIn("source/node_modules/module.js", files)
        self.assertFalse(any("/.studio/" in name for name in files))
        (workspace / "compose.yaml").unlink()
        with self.assertRaises(Problem):
            self.store.bundle(self.id)

    def test_edited_design_invalidates_old_build(self):
        self.save_plan()
        self.store.approve(self.id, {"baseVersion": 1})
        self.store.start(self.id, {"kind": "build"})
        self.wait()
        self.store.edit(self.id, {"plan": dict(self.plan, prd="新的需求"), "baseVersion": 1})
        with self.assertRaises(Problem):
            self.store.bundle(self.id)
        self.assertIsNone(self.store.load(self.id)["built_from"])

    def test_missing_command_leaves_project_idle(self):
        self.store.command = ["/no-such-studio-test-executable"]
        with self.assertRaises(Problem):
            self.store.start(self.id, {"kind": "analyze"})
        self.assertEqual(self.store.load(self.id)["job"]["status"], "idle")

    def test_nonzero_process_cannot_complete_or_export(self):
        self.store.command = [sys.executable, "-c", "import sys;sys.stdin.read();sys.exit(9)"]
        self.store.start(self.id, {"kind": "analyze"})
        data = self.wait()
        self.assertEqual(data["job"]["status"], "failed")
        self.assertEqual(data["job"]["exitCode"], 9)
        self.assertIsNone(data["plan"])
        with self.assertRaises(Problem):
            self.store.bundle(self.id)

    def test_exit_zero_without_result_is_failure(self):
        self.store.command = [sys.executable, "-c", "import sys;sys.stdin.read()"]
        self.store.start(self.id, {"kind": "analyze"})
        data = self.wait()
        self.assertEqual(data["job"]["status"], "failed")
        self.assertIsNone(data["plan"])

    def test_deleting_queued_chat_hides_both_messages_and_preserves_running_task(self):
        active=self.store.start(self.id,{'kind':'chat','note':'当前问题'})['submittedJob'];self.store.claim()
        queued=self.store.start(self.id,{'kind':'chat','note':'不再需要的引导','enqueue':True})['submittedJob']
        body={'jobId':queued['id'],'dismissMessage':True}
        result=self.store.cancel(self.id,body)
        self.assertEqual(result['job']['id'],active['id'])
        self.assertEqual(result['job']['status'],'running')
        self.assertFalse(any(item['id'].startswith(queued['id']) for item in result['chatHistory']))
        self.assertEqual(self.store.cancel(self.id,body)['chatHistory'],result['chatHistory'])
        self.assertIsNone(self.store.claim())
        with self.assertRaises(Problem):self.store.cancel(self.id,{'jobId':active['id'],'dismissMessage':True})
        self.assertEqual(self.store.db.execute('SELECT cancel_requested FROM jobs WHERE id=?',(active['id'],)).fetchone()[0],0)
        with self.assertRaises(Problem):self.store.cancel(self.id,{'jobId':active['id'],'dismissMessage':'true'})
        self.assertEqual(self.store.load(self.id)['chatHistory'],result['chatHistory'])

    def test_build_and_iteration_receive_preview_transport_diagnostics(self):
        self.save_plan();self.store.approve(self.id,{'baseVersion':1})
        for kind in ('build','iterate'):
            result=self.store.start(self.id,{'kind':kind,'note':'检查预览链路','enqueue':True})
            spec=json.loads(self.store.db.execute('SELECT spec FROM jobs WHERE id=?',(result['submittedJob']['id'],)).fetchone()[0])
            self.assertIn('previewDiagnostics',json.loads(Path(spec['request']).read_text()))

    def test_code_question_receives_preview_diagnostics_without_reading_unbounded_logs(self):
        runtime=self.store.directory(self.id)/'preview-runtime';runtime.mkdir()
        (runtime/'runtime.log').write_text('x'*10000+' response-too-large')
        (runtime/'active.json').write_text(json.dumps({'channel':'f'*32,'url':'http://127.0.0.1:54321/','proxyLimits':{'maxResponseBytes':67108864}}))
        result=self.store.start(self.id,{'kind':'chat','note':'导入失败','autoScope':'code'})
        spec=json.loads(self.store.db.execute('SELECT spec FROM jobs WHERE id=?',(result['submittedJob']['id'],)).fetchone()[0])
        diagnostics=json.loads(Path(spec['request']).read_text())['previewDiagnostics']
        self.assertLessEqual(len(diagnostics['runtimeLogTail']),8192)
        self.assertIn('response-too-large',diagnostics['runtimeLogTail'])
        self.assertIn('不在本次应用工作区',diagnostics['note'])
        self.assertEqual(diagnostics['publishedPreview']['url'],'http://127.0.0.1:54321/')
        self.assertIn('不是本轮修改草稿',diagnostics['publishedPreviewNote'])

    def test_arbitrary_file_formats_keep_original_bytes_and_names(self):
        import base64
        names=['terrain.glb','document.pdf','archive.zip','binary']
        content=b'glTF\x00\xff\x01'
        result=self.store.start(self.id,{'kind':'chat','note':'读取附件','files':[{'name':name,'data':base64.b64encode(content).decode()} for name in names]})
        record=result['submittedJob']
        self.assertEqual([item['name'] for item in record['chatMessage']['files']],names)
        for attachment in record['chatMessage']['files']:
            self.assertEqual((self.store.directory(self.id)/'chat-files'/record['id']/attachment['file']).read_bytes(),content)
        self.store.work_once()
        self.assertEqual(self.store.load(self.id)['job']['status'],'completed')

    def test_steering_cancels_only_same_conversation_and_prioritizes_continuation(self):
        first=self.store.start(self.id,{'kind':'chat','note':'修复导入','autoScope':'code'})['submittedJob']
        self.store.claim()
        other=self.store.start(self.id,{'kind':'chat','note':'稍后说明部署','enqueue':True})['submittedJob']
        queued=self.store.start(self.id,{'kind':'chat','note':'先处理大文件','enqueue':True})['submittedJob']
        body={'jobId':first['id'],'messageId':queued['id']}
        result=self.store.steer(self.id,body)
        new=result['submittedJob']
        self.assertEqual(self.store.steer(self.id,body)['submittedJob']['id'],new['id'])
        self.assertEqual([item['status'] for item in result['queue'] if item['id']==first['id']],['cancelling'])
        spec=json.loads(self.store.db.execute('SELECT spec FROM jobs WHERE id=?',(new['id'],)).fetchone()[0])
        inputs=json.loads(Path(spec['request']).read_text())
        self.assertEqual(inputs['steering']['originalGoal'],'修复导入')
        self.assertIn('先处理大文件',inputs['question'])
        self.assertFalse(any(item['id']==queued['id'] for item in result['chatHistory']))
        self.assertIsNone(self.store.claim())
        record=json.loads(self.store.db.execute('SELECT record FROM jobs WHERE id=?',(first['id'],)).fetchone()[0])
        record.update(status='cancelled');self.store.job_record(self.id,record)
        self.assertEqual(self.store.claim()['snapshot']['job']['id'],new['id'])
        self.assertEqual(self.store.db.execute('SELECT state FROM jobs WHERE id=?',(other['id'],)).fetchone()[0],'queued')

    def test_steering_modification_runs_before_older_queued_messages(self):
        self.save_plan();self.store.approve(self.id,{'baseVersion':1})
        first=self.store.start(self.id,{'kind':'chat','note':'调整界面','autoScope':'code'})['submittedJob'];self.store.claim()
        self.store.start(self.id,{'kind':'chat','note':'稍后回答','enqueue':True})
        queued=self.store.start(self.id,{'kind':'chat','note':'AUTO_MODIFY 保留布局','enqueue':True})['submittedJob']
        guided=self.store.steer(self.id,{'jobId':first['id'],'messageId':queued['id']})['submittedJob']
        original=json.loads(self.store.db.execute('SELECT record FROM jobs WHERE id=?',(first['id'],)).fetchone()[0]);original['status']='cancelled';self.store.job_record(self.id,original)
        self.store.work_once()
        record=json.loads(self.store.db.execute('SELECT record FROM jobs WHERE id=?',(guided['id'],)).fetchone()[0])
        self.assertIn('followupJob',record)
        child=self.store.claim()['snapshot']['job']
        self.assertEqual(child['id'],record['followupJob'])
        self.assertEqual(child['kind'],'iterate')
        self.assertEqual(child['steering']['jobId'],first['id'])

    def test_steering_submission_failure_rolls_back_cancellation(self):
        first=self.store.start(self.id,{'kind':'chat','note':'原目标'})['submittedJob'];self.store.claim()
        queued=self.store.start(self.id,{'kind':'chat','note':'补充','enqueue':True})['submittedJob']
        with patch.object(self.store,'start',side_effect=Problem('队列不可用')):
            with self.assertRaises(Problem):self.store.steer(self.id,{'jobId':first['id'],'messageId':queued['id']})
        self.assertEqual([(row[0],row[1]) for row in self.store.db.execute('SELECT state,cancel_requested FROM jobs ORDER BY created')],[('running',0),('queued',0)])

    def test_steering_waits_for_owned_child_exit_before_executing_new_question(self):
        ready=Path(self.directory.name)/'ready';release=Path(self.directory.name)/'release'
        self.store.launch_environment={'FIXTURE_READY':str(ready),'FIXTURE_RELEASE':str(release)}
        first=self.store.start(self.id,{'kind':'chat','note':'说明原问题'})['submittedJob']
        worker=threading.Thread(target=self.store.work_once);worker.start()
        try:
            deadline=time.monotonic()+10
            while not ready.exists() and worker.is_alive() and time.monotonic()<deadline:time.sleep(.02)
            self.assertTrue(ready.exists(),'Harness did not reach the barrier')
            self.store.launch_environment={}
            queued=self.store.start(self.id,{'kind':'chat','note':'只解释错误','enqueue':True})['submittedJob']
            result=self.store.steer(self.id,{'jobId':first['id'],'messageId':queued['id']})
            worker.join(timeout=10)
            self.assertFalse(worker.is_alive())
            self.assertEqual(self.store.db.execute('SELECT state FROM jobs WHERE id=?',(first['id'],)).fetchone()[0],'cancelled')
            self.assertTrue(self.store.work_once())
            current=self.store.load(self.id)
            self.assertEqual(current['job']['id'],result['submittedJob']['id'])
            self.assertEqual(current['job']['status'],'completed')
            self.assertIn('只解释错误',current['job']['message'])
        finally:
            release.touch();worker.join(timeout=10)

    def test_invalid_steering_keeps_original_tasks_and_rejects_finished_or_other_conversation(self):
        first=self.store.start(self.id,{'kind':'chat','note':'说明问题'})['submittedJob'];self.store.claim()
        queued=self.store.start(self.id,{'kind':'chat','note':'补充','enqueue':True})['submittedJob']
        with self.assertRaises(Problem):self.store.steer(self.id,{'jobId':'f'*32,'messageId':queued['id']})
        record=dict(queued,conversationId='other')
        self.store.db.execute('UPDATE jobs SET record=? WHERE id=?',(json.dumps(record),queued['id']))
        with self.assertRaises(Problem):self.store.steer(self.id,{'jobId':first['id'],'messageId':queued['id']})
        self.assertEqual(self.store.db.execute('SELECT cancel_requested FROM jobs WHERE id=?',(first['id'],)).fetchone()[0],0)
        self.assertEqual(len(self.store.pending(self.id)),2)

    def test_busy_store_rejects_competing_edits_and_cancels_queue(self):
        self.store.start(self.id, {"kind": "analyze"})
        with self.assertRaises(Problem):
            self.store.edit(self.id, {"plan": self.plan, "baseVersion": 0})
        with self.assertRaises(Problem):
            self.store.start(self.id, {"kind": "analyze"})
        self.store.cancel(self.id)
        data = self.wait()
        self.assertEqual(data["job"]["status"], "cancelled")
        self.assertIsNone(data["plan"])

    def test_timeout_remains_failure_even_if_process_exits(self):
        self.store.timeout = .05
        self.store.command = [sys.executable, "-c", "import sys,time;sys.stdin.read();time.sleep(60)"]
        self.store.start(self.id, {"kind": "analyze"})
        data = self.wait()
        self.assertTrue(data["job"]["timedOut"])
        self.assertEqual(data["job"]["status"], "failed")

    def test_api_reopen_preserves_pending_task(self):
        self.store.start(self.id, {"kind": "analyze"})
        recovered = Store(self.directory.name, [])
        self.addCleanup(recovered.close)
        self.assertEqual(recovered.load(self.id)["job"]["status"], "queued")
        recovered.work_once()
        self.assertEqual(self.store.load(self.id)["job"]["status"], "completed")

    def test_bad_images_and_incomplete_plan_are_rejected(self):
        with self.assertRaises(Problem):
            self.store.create({"name": "bad", "requirements": "bad", "images": [{"name": "bad.png", "data": "data:image/png;base64,aGVsbG8="}]})
        with self.assertRaises(Problem):
            validate_plan({"prd": "only one section"})
        with self.assertRaises(Problem):
            self.store.load("../elsewhere")


class QueueTests(unittest.TestCase):
    """Persistent claims, cancellation and replay use temporary roots and real children."""

    setUp = WorkflowTests.setUp
    save_plan = WorkflowTests.save_plan

    def test_idempotency_survives_reopen_and_rejects_changed_request(self):
        body = {"kind": "analyze", "requestId": "a" * 32}
        first = self.store.start(self.id, body)
        second = Store(self.directory.name, [])
        self.addCleanup(second.close)
        repeated = second.start(self.id, body)
        self.assertEqual(first["job"]["id"], repeated["job"]["id"])
        self.assertEqual(len(repeated["queue"]), 1)
        with self.assertRaises(Problem):
            second.start(self.id, {**body, "kind": "build"})

    def test_cancelling_before_claim_preserves_accepted_build(self):
        self.save_plan()
        self.store.approve(self.id, {"baseVersion": 1})
        self.store.start(self.id, {"kind": "build"})
        self.store.work_once()
        completed = self.store.load(self.id)
        self.store.accept(self.id, {"jobId": completed["job"]["id"]})
        self.store.start(self.id, {"kind": "iterate", "note": "暂不执行"})
        self.store.cancel(self.id)
        data = self.store.load(self.id)
        self.assertEqual(data["built_from"], completed["approved"])
        self.assertEqual(data["accepted"], completed["job"]["id"])
        self.assertTrue(self.store.bundle(self.id))

    def test_stale_queued_revision_stops_without_model_call(self):
        self.save_plan()
        self.store.start(self.id, {"kind": "revise", "note": "意见一"})
        self.store.start(self.id, {"kind": "revise", "note": "意见二", "enqueue": True})
        self.store.work_once()
        self.store.work_once()
        data = self.store.load(self.id)
        self.assertEqual(len(data["versions"]), 2)
        self.assertEqual(data["job"]["status"], "blocked")
        self.assertEqual(len(data["queue"]), 0)

    def test_failed_dependency_blocks_followup_until_explicit_retry(self):
        self.save_plan()
        self.store.command = [sys.executable, "-c", "import sys;sys.stdin.read();sys.exit(9)"]
        self.store.start(self.id, {"kind": "revise", "note": "修改一"})
        queued = self.store.start(self.id, {"kind": "revise", "note": "修改二", "enqueue": True})
        followup = queued["queue"][-1]["id"]
        self.store.work_once()
        self.store.work_once()
        self.assertEqual(self.store.load(self.id)["job"]["status"], "blocked")
        self.store.command = [sys.executable, str(Path(__file__).with_name("fake_harness.py"))]
        self.store.retry(self.id, {"jobId": followup})
        self.store.work_once()
        self.assertEqual(self.store.load(self.id)["job"]["status"], "completed")

    def test_two_consumers_cannot_claim_one_task_twice(self):
        self.store.start(self.id, {"kind": "analyze"})
        other = Store(self.directory.name, [])
        self.addCleanup(other.close)
        barrier = threading.Barrier(2)
        claims = []
        def claim(store):
            barrier.wait()
            claims.append(store.claim())
        threads = [threading.Thread(target=claim, args=(store,)) for store in (self.store, other)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sum(value is not None for value in claims), 1)

    def test_worker_recovery_does_not_replay_abandoned_task(self):
        self.store.start(self.id, {"kind": "analyze"})
        self.assertIsNotNone(self.store.claim())
        self.store.recover_worker()
        self.assertEqual(self.store.load(self.id)["job"]["status"], "interrupted")
        self.assertFalse(self.store.work_once())

    def test_legacy_migration_keeps_json_and_generated_files(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / self.id
            project.mkdir()
            data = self.store.load(self.id)
            data["job"] = {"status": "running"}
            original = json.dumps(data).encode()
            (project / "project.json").write_bytes(original)
            (project / "workspace").mkdir()
            (project / "workspace" / "keep.txt").write_text("keep")
            imported = Store(root, [])
            self.assertEqual(imported.load(self.id)["job"]["status"], "interrupted")
            imported.edit(self.id, {"plan": self.plan, "baseVersion": 0})
            imported.close()
            reopened = Store(root, [])
            try:
                self.assertEqual(reopened.load(self.id)["plan"], self.plan)
                self.assertEqual((project / "project.json").read_bytes(), original)
                self.assertEqual((project / "workspace" / "keep.txt").read_text(), "keep")
            finally:
                reopened.close()

    def test_progress_is_replayable_and_omits_private_reasoning(self):
        self.store.start(self.id, {"kind": "analyze"})
        before = self.store.event_batch(self.id, 0)[-1]["id"]
        self.store.work_once()
        events = self.store.event_batch(self.id, before)
        messages = [json.loads(event["payload"])["job"].get("message", "") for event in events]
        self.assertIn("正在请求模型", messages)
        self.assertNotIn("PRIVATE_REASONING_NOT_FOR_UI", json.dumps(events))
        self.assertEqual(json.loads(events[-1]["payload"])["job"]["status"], "completed")

    def wait_until(self, condition, message):
        deadline = time.monotonic() + 10
        while not condition():
            if time.monotonic() > deadline:
                self.fail(message)
            time.sleep(.02)

    def test_independent_worker_survives_api_close_and_cancels_running_child(self):
        ready = Path(self.directory.name) / "ready"
        release = Path(self.directory.name) / "release"
        self.store.launch_environment = {"FIXTURE_READY": str(ready), "FIXTURE_RELEASE": str(release)}
        self.store.start(self.id, {"kind": "analyze"})
        worker_log = (Path(self.directory.name) / "worker-test.log").open("wb")
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve().parents[1] / "server.py"), "--worker"], env={**os.environ, "STUDIO_DATA_DIR": self.directory.name}, stdout=worker_log, stderr=worker_log)
        try:
            self.wait_until(ready.exists, "Worker did not reach the fixture barrier")
            # This API handle is independent of the running executor process.
            api = Store(self.directory.name, [])
            api.close()
            self.assertIsNone(process.poll())
            self.assertEqual(self.store.load(self.id)["job"]["status"], "running")
            self.store.cancel(self.id)
            self.wait_until(lambda: self.store.load(self.id)["job"]["status"] == "cancelled", "Worker did not acknowledge cancellation")
            self.assertIsNone(self.store.load(self.id)["plan"])
        finally:
            with self.store.transaction():
                self.store.db.execute("UPDATE worker SET stop_requested=1 WHERE id=1")
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            worker_log.close()
        self.assertEqual(process.returncode, 0)


    def test_http_process_restart_does_not_stop_independent_worker(self):
        ready = Path(self.directory.name) / "ready"
        release = Path(self.directory.name) / "release"
        self.store.launch_environment = {"FIXTURE_READY": str(ready), "FIXTURE_RELEASE": str(release)}
        self.store.start(self.id, {"kind": "analyze"})
        environment = {**os.environ, "STUDIO_DATA_DIR": self.directory.name}
        script = str(Path(__file__).resolve().parents[1] / "server.py")
        servers = []
        def launch(extra=()):
            process = subprocess.Popen([sys.executable, script, "--port", "0", *extra], env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            servers.append(process)
            self.assertTrue(select.select([process.stdout], [], [], 10)[0], "HTTP process did not report readiness")
            line = process.stdout.readline().decode()
            self.assertIn("Harness Studio: http://127.0.0.1:", line)
            return process, int(line.strip().rsplit(":", 1)[1])
        try:
            first, _ = launch()
            self.wait_until(ready.exists, "Independent worker did not start")
            first.send_signal(signal.SIGINT)
            first.wait(timeout=5)
            second, port = launch(("--no-worker",))
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            try:
                connection.request("GET", "/api/projects/" + self.id)
                response = connection.getresponse()
                self.assertEqual(json.loads(response.read())["job"]["status"], "running")
            finally:
                connection.close()
            release.touch()
            self.wait_until(lambda: self.store.load(self.id)["job"]["status"] == "completed", "Task did not complete across HTTP restart")
            self.assertTrue(self.store.load(self.id)["plan"])
        finally:
            for process in servers:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                    process.wait(timeout=5)
                process.stdout.close()
            with self.store.transaction():
                self.store.db.execute("UPDATE worker SET stop_requested=1 WHERE id=1")
            self.wait_until(lambda: not self.store.worker_status()["online"], "Worker did not stop")



class HTTPTests(unittest.TestCase):
    """Own an OS-assigned loopback port and stop the server before data cleanup."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Store(self.directory.name, [])
        self.addCleanup(self.store.close)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.store = self.store
        self.server.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.stop_event.set()
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def request(self, method, path, body=None, origin=None, host=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            headers = {"Content-Type": "application/json"}
            if origin is not None:
                headers["Origin"] = origin
            if host is not None:
                headers["Host"] = host
            connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            result = connection.getresponse()
            return result.status, dict(result.getheaders()), result.read()
        finally:
            connection.close()

    def test_chat_image_history_uses_project_owned_files_and_rejects_other_projects(self):
        import base64
        from test_document_cache import PNG
        project=self.store.create({'name':'聊天附件','requirements':'测试图片'})
        self.store.command=[sys.executable,str(Path(__file__).with_name('fake_harness.py'))]
        result=self.store.start(project['id'],{'kind':'chat','note':'解释','images':[{'name':'fixture.png','data':'data:image/png;base64,'+base64.b64encode(PNG).decode()}],'files':[{'name':'error.log','data':base64.b64encode(b'original error').decode()}]})
        message=result['chatHistory'][0];url=message['images'][0]['url']
        status,headers,body=self.request('GET',url)
        self.assertEqual(status,200);self.assertEqual(body,PNG)
        self.assertIn('image/png',headers['Content-Type'])
        file_url=message['files'][0]['url']
        status,headers,body=self.request('GET',file_url)
        self.assertEqual(status,200);self.assertEqual(body,b'original error')
        self.assertIn('application/octet-stream',headers['Content-Type'])
        other=self.store.create({'name':'其他项目','requirements':'隔离'})
        self.assertEqual(self.request('GET',url.replace(project['id'],other['id']))[0],404)
        self.assertEqual(self.request('GET',file_url.replace(project['id'],other['id']))[0],404)

    def test_foreign_and_absent_origins_cannot_create_projects(self):
        body = {"name": "拒绝请求", "requirements": "不应写入"}
        for origin in (None, "null", "https://example.com"):
            status, _, _ = self.request("POST", "/api/projects", body, origin)
            self.assertEqual(status, 403)
        self.assertEqual(self.store.listing(), [])

    def test_same_origin_create_and_read_persisted_requirements(self):
        origin = f"http://127.0.0.1:{self.server.server_port}"
        status, _, body = self.request("POST", "/api/projects", {"name": "API 项目", "requirements": "实际保存需求"}, origin)
        self.assertEqual(status, 200)
        project = json.loads(body)
        status, _, body = self.request("GET", "/api/projects/" + project["id"])
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["requirements"], "实际保存需求")

    def test_foreign_host_and_traversal_are_rejected(self):
        self.assertEqual(self.request("GET", "/api/status", host="example.com")[0], 403)
        self.assertEqual(self.request("GET", "/../server.py")[0], 404)

    def test_large_requirements_upload_exceeds_generic_request_limit(self):
        import base64
        raw=b'Requirements'+b' '*(14*1024*1024)
        body={'name':'large.txt','data':base64.b64encode(raw).decode()}
        origin=f'http://127.0.0.1:{self.server.server_port}'
        status,_,payload=self.request('POST','/api/import-requirements',body,origin)
        self.assertEqual(status,200);self.assertEqual(json.loads(payload)['text'],'Requirements')

    def test_requirements_import_uses_same_origin_and_persists_only_reviewed_text(self):
        import base64
        body={'name':'需求.md','data':base64.b64encode('# 客户需求'.encode()).decode()}
        self.assertEqual(self.request('POST','/api/import-requirements',body)[0],403)
        origin=f'http://127.0.0.1:{self.server.server_port}'
        status,_,raw=self.request('POST','/api/import-requirements',body,origin)
        self.assertEqual(status,200);result=json.loads(raw);self.assertEqual(result['text'],'# 客户需求')
        self.assertEqual(self.store.listing(),[])
        status,_,raw=self.request('POST','/api/projects',{'name':'导入测试','requirements':result['text']},origin)
        self.assertEqual(status,200);self.assertEqual(json.loads(raw)['requirements'],'# 客户需求')

    def test_document_libraries_are_local_and_asset_routes_remain_explicit(self):
        for path in ('/documents.js','/lib/purify.js','/lib/marked.js','/lib/mermaid.js'):
            status,headers,body=self.request('GET',path)
            self.assertEqual(status,200,path);self.assertTrue(body,path)
            self.assertIn('script-src \'self\'',headers['Content-Security-Policy'])
            self.assertNotIn('unsafe-eval',headers['Content-Security-Policy'])
        self.assertEqual(self.request('GET','/lib/../../server.py')[0],404)
        self.assertEqual(self.request('GET','/lib/unknown.js')[0],404)

    def test_static_preview_cannot_access_network_or_parent_origin(self):
        project = self.store.create({"name": "preview", "requirements": "preview"})
        workspace = self.store.directory(project["id"]) / "workspace"
        (workspace / "preview.html").write_text("<button id='add'>新增客户</button>")
        status, headers, body = self.request("GET", f"/api/projects/{project['id']}/preview")
        self.assertEqual(status, 200)
        policy = headers["Content-Security-Policy"]
        self.assertIn("sandbox allow-scripts", policy)
        self.assertNotIn("allow-same-origin", policy)
        self.assertIn("connect-src 'none'", policy)
        self.assertIn("studio-select", body.decode())

    def test_enqueue_ack_is_idempotent_and_stream_disconnect_keeps_task(self):
        project = self.store.create({"name": "提交确认", "requirements": "持久任务"})
        self.store.command = [sys.executable, str(Path(__file__).with_name("fake_harness.py"))]
        origin = f"http://127.0.0.1:{self.server.server_port}"
        path = f"/api/projects/{project['id']}/jobs"
        body = {"kind": "analyze", "requestId": "b" * 32}
        status, _, payload = self.request("POST", path, body, origin)
        self.assertEqual(status, 202)
        job_id = json.loads(payload)["submittedJob"]["id"]
        status, _, payload = self.request("POST", path, body, origin)
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(payload)["submittedJob"]["id"], job_id)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request("GET", f"/api/projects/{project['id']}/events")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertTrue(response.readline().startswith(b"id: "))
        finally:
            connection.close()
        queued = self.store.load(project["id"])["queue"]
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["status"], "queued")

    def test_sse_reconnect_replays_committed_state_by_event_id(self):
        project = self.store.create({"name": "SSE", "requirements": "重连"})
        project_id = project["id"]
        cursor = self.store.event_batch(project_id, 0)[-1]["id"]
        project["job"] = {"status": "idle", "message": "重连后的状态"}
        self.store.save(project)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request("GET", f"/api/projects/{project_id}/events", headers={"Last-Event-ID": str(cursor)})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"), "text/event-stream; charset=utf-8")
            line = response.readline()
            while line and not line.startswith(b"id: "):
                line = response.readline()
            self.assertTrue(line, "SSE did not deliver the committed event")
            self.assertGreater(int(line.decode().strip().split(": ")[1]), cursor)
            self.assertEqual(response.readline(), b"event: state\n")
            self.assertIn("重连后的状态", response.readline().decode())
        finally:
            connection.close()



if __name__ == "__main__":
    unittest.main()
