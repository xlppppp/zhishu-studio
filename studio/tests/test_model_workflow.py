"""Exercise stage routing, bounded repair, and failure containment without API calls."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Store,Problem,review_inputs
from model_workflow import model_policy,model_patch,validate_policy,validate_review,ReviewCopy


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name,[sys.executable,str(Path(__file__).with_name('fake_harness.py'))]);self.addCleanup(self.store.close)

    def project(self,requirement='fixture requirements'):
        project=self.store.create({'name':'多模型验证','requirements':requirement});self.id=project['id']
        self.store.edit(self.id,{'baseVersion':0,'plan':{key:'confirmed '+key for key in ('prd','frontend','backend','database')}})
        self.store.approve(self.id,{'baseVersion':1});return project

    def build(self,requirement='fixture requirements'):
        self.project(requirement);self.store.start(self.id,{'kind':'build'});self.store.work_once();return self.store.load(self.id)

    def stages(self,data):
        log=(self.store.directory(self.id)/('job-'+data['job']['id']+'.log')).read_text()
        return [(line['stage'],line['model']) for raw in log.splitlines() if (line:=json.loads(raw)).get('type')=='fixtureModel']

    def test_review_rounds_retain_submitted_glb_files(self):
        import base64
        self.project()
        for mode in ('focused','full'):
            policy={**model_policy(),'reviewMode':mode}
            with patch('server.model_policy',return_value=policy):
                self.store.start(self.id,{'kind':'iterate','chatMessage':True,'note':'验证原始附件','files':[{'name':'test.glb','data':base64.b64encode(b'glTF').decode()}]})
            self.store.work_once()
            data=self.store.load(self.id)
            self.assertEqual(data['job']['status'],'completed',data['job'].get('message'))
            self.assertEqual(data['job']['reviews'][-1]['verdict'],'pass')

    def test_review_receives_original_binary_attachments_in_its_own_directory(self):
        source=Path(self.temp.name)/'source';source.mkdir()
        destination=Path(self.temp.name)/'review';destination.mkdir()
        (source/'chat-file-0.glb').write_bytes(b'glTF\x00\xff')
        inputs={'attachments':[{'name':'mine.glb','file':'chat-file-0.glb','path':str(source/'chat-file-0.glb')}]}
        result=review_inputs(inputs,source,destination)
        target=Path(result['attachments'][0]['path'])
        self.assertEqual(target.parent,destination)
        self.assertEqual(target.read_bytes(),b'glTF\x00\xff')
        self.assertEqual(inputs['attachments'][0]['path'],str(source/'chat-file-0.glb'))
        with self.assertRaisesRegex(ValueError,'大小'):review_inputs({'attachments':[{**inputs['attachments'][0],'size':99}]},source,destination)
        with self.assertRaisesRegex(ValueError,'内容'):review_inputs({'attachments':[{**inputs['attachments'][0],'sha256':'0'*64}]},source,destination)
        with self.assertRaises(ValueError):review_inputs({'attachments':[{'file':'../escape.glb'}]},source,destination)

    def test_continue_after_review_cancel_skips_development_only_for_unchanged_source(self):
        self.project()
        with patch.object(self.store,'invoke_stage',side_effect=self.cancel_review_after_development):
            self.store.start(self.id,{'kind':'build'});self.store.work_once()
        self.store.start(self.id,{'kind':'build','buildMode':'continue'});self.store.work_once()
        data=self.store.load(self.id)
        self.assertEqual(data['job']['status'],'completed')
        self.assertEqual(self.stages(data),[('review','gpt-6.1-sol')])
        workspace=self.store.directory(self.id)/'workspace'
        (workspace/'changed.txt').write_text('new partial work')
        self.store.start(self.id,{'kind':'build','buildMode':'continue'});self.store.work_once()
        data=self.store.load(self.id)
        self.assertEqual(self.stages(data)[0],('development','gpt-6.1-sol'))

    def test_continuation_carries_prior_feedback_with_current_design(self):
        self.project()
        self.store.start(self.id,{'kind':'iterate','note':'保留已有矿山页面，补齐设备详情','target':'设备详情'})
        self.store.cancel(self.id)
        started=self.store.start(self.id,{'kind':'build','buildMode':'continue'})
        request=self.store.directory(self.id)/'workspace'/'.studio'/started['job']['id']/('request-'+started['job']['id']+'.json')
        data=json.loads(request.read_text())
        self.assertEqual(data['previousProgress']['feedback'],'保留已有矿山页面，补齐设备详情')
        self.assertEqual(data['plan'],self.store.load(self.id)['plan'])

    def test_continue_keeps_existing_source_and_fresh_build_retains_backup(self):
        self.project();workspace=self.store.directory(self.id)/'workspace';workspace.mkdir(exist_ok=True)
        (workspace/'existing.txt').write_text('existing implementation')
        (workspace/'preview.html').write_text('<h1>Existing preview</h1>')
        self.store.start(self.id,{'kind':'build','buildMode':'continue'});self.store.work_once()
        self.assertEqual((workspace/'existing.txt').read_text(),'existing implementation')
        self.assertTrue(self.store.load(self.id)['previewAvailable'])
        self.store.start(self.id,{'kind':'build','buildMode':'restart'});self.store.work_once()
        data=self.store.load(self.id)
        self.assertEqual(data['job']['status'],'completed')
        self.assertFalse((workspace/'existing.txt').exists())
        self.assertEqual((self.store.directory(self.id)/data['job']['workspaceBackup']/'existing.txt').read_text(),'existing implementation')
        with self.assertRaises(Problem):self.store.bundle(self.id)

    def test_build_mode_is_validated_and_part_of_submission_identity(self):
        self.project()
        with self.assertRaises(Problem):self.store.start(self.id,{'kind':'build','buildMode':'invalid'})
        with self.assertRaises(Problem):self.store.start(self.id,{'kind':'analyze','buildMode':'restart'})
        request='c'*32
        self.store.start(self.id,{'kind':'build','buildMode':'continue','requestId':request})
        with self.assertRaises(Problem):self.store.start(self.id,{'kind':'build','buildMode':'restart','requestId':request})
        with self.assertRaises(Problem):self.store.start(self.id,{'kind':'build','buildMode':'restart','enqueue':True})

    def test_preview_survives_cancelled_review_without_delivery_eligibility(self):
        self.project()
        with patch.object(self.store,'invoke_stage',side_effect=self.cancel_review_after_development):
            self.store.start(self.id,{'kind':'build'});self.store.work_once()
        data=self.store.load(self.id)
        self.assertEqual(data['job']['status'],'cancelled')
        self.assertTrue(data['previewAvailable']);self.assertTrue(data['hasWorkspaceProgress'])
        self.assertIsNone(data['built_from'])
        with self.assertRaises(Problem):self.store.accept(self.id,{'jobId':data['job']['id']})

    def cancel_review_after_development(self,*args):
        from server import ExecutionStopped
        if args[8]=='development':
            (args[3]/'preview.html').write_text('<h1>Retained preview</h1>')
            return {'summary':'fixture development completed'}
        raise ExecutionStopped('cancelled','fixture review cancelled')

    def test_fallback_config_rejects_invalid_models_and_retry_budget(self):
        for fallback in ({'from':'same','to':'same','primaryRetries':1}, {'from':'primary','to':'fallback','primaryRetries':True}, {'from':'primary','to':'fallback','primaryRetries':-1}, {'from':'primary','to':'bad model','primaryRetries':1}, {'to':'fallback'}):
            with self.subTest(fallback=fallback),self.assertRaises(ValueError):
                validate_policy({**model_policy(),'fallback':fallback})

    def test_review_report_records_actual_fallback_model(self):
        data=self.build('FALLBACK_SERVER')
        self.assertEqual(data['job']['status'],'completed')
        self.assertEqual(data['job']['reviews'][0]['model'],'gpt-6-sol')

    def test_transient_failure_resumes_same_session_with_fallback(self):
        p=self.store.create({'name':'fallback fixture','requirements':'FALLBACK_SERVER'})
        self.id=p['id'];self.store.start(self.id,{'kind':'analyze'});self.store.work_once()
        data=self.store.load(self.id)
        self.assertEqual(data['job']['status'],'completed')
        self.assertEqual(self.stages(data),[('analysis','gpt-6.1-sol'),('analysis','gpt-6-sol')])
        self.assertEqual(data['job']['modelFallback']['reason'],'SERVER')
        self.assertEqual(data['job']['activeModel'],'gpt-6-sol')

    def test_auth_and_unknown_tools_do_not_fallback_and_fallback_is_finite(self):
        for requirement,count in [('FALLBACK_AUTH',1),('FALLBACK_UNKNOWN_TOOL',1),('FALLBACK_BOTH',2)]:
            with self.subTest(requirement=requirement):
                p=self.store.create({'name':'failure fixture','requirements':requirement})
                self.id=p['id'];self.store.start(self.id,{'kind':'analyze'});self.store.work_once()
                data=self.store.load(self.id)
                self.assertEqual(data['job']['status'],'failed')
                self.assertEqual(len(self.stages(data)),count)

    def test_stage_overlays_preserve_provider_connection_and_image_support(self):
        root=Path(self.temp.name);policy=model_policy()
        base=json.loads((Path(__file__).parents[1]/'harness.patch.yml').read_text())
        for stage in ('analysis','development','review'):
            with self.subTest(stage=stage):
                overlay=json.loads(model_patch(root,policy,stage).read_text())
                route=policy['stageProviders'][stage]
                provider=overlay[0]['config']['providers'][route]
                self.assertEqual({k:v for k,v in provider.items() if k not in ('models','retryPolicy')},
                    {k:v for k,v in base[0]['config']['providers'][route].items() if k not in ('models','retryPolicy')})
                self.assertEqual(provider['api'],'openai-completions')
                self.assertEqual(provider['baseURL'],'https://api.gpt.ge/v1')
                self.assertEqual(provider['apiKeyEnv'],'GPT_GE_DEFAULT_API_KEY' if stage=='analysis' else 'GPT_GE_CODEX_API_KEY')
                self.assertEqual(overlay[1]['config']['provider'],route)
                self.assertEqual(overlay[1]['config']['reasoningEffort'],'high')
                self.assertEqual(provider['reasoning'],'high')
                self.assertTrue(all(model['reasoningEfforts']['high']=='high' for model in provider['models']))
                self.assertTrue(all(model['input']==['text','image'] for model in provider['models']))
                self.assertEqual(overlay[1]['config']['model'],policy[stage])
                self.assertIn('gpt-6-sol',[item['id'] for item in provider['models']])
                self.assertEqual(provider['retryPolicy']['maxRetries'],1)
        with self.assertRaisesRegex(ValueError,'未配置模型提供方'):
            model_patch(root,{**policy,'stageProviders':{**policy['stageProviders'],'analysis':'missing-provider'}},'analysis')

    def test_legacy_saved_policy_keeps_single_route_without_forced_reasoning(self):
        policy={'provider':'gpt-ge','analysis':'gpt-6.1-sol','development':'claude-sonnet-5-5','review':'gpt-6.1-sol','maxReviewRounds':3}
        overlay=json.loads(model_patch(Path(self.temp.name),validate_policy(policy),'development').read_text())
        self.assertEqual(overlay[1]['config'],{'provider':'gpt-ge','model':'claude-sonnet-5-5'})
        self.assertEqual(overlay[0]['config']['providers']['gpt-ge']['apiKeyEnv'],'GPT_GE_API_KEY')

    def test_stage_routes_and_reasoning_reject_invalid_saved_settings(self):
        for changes in ({'stageProviders':{}},{'stageProviders':{'analysis':'a','development':'b','review':'bad route'}},{'reasoning':'automatic'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):validate_policy({**model_policy(),**changes})

    def test_retry_wait_is_persisted_without_failure_text_and_cleared_on_resume(self):
        p=self.store.create({'name':'retry fixture','requirements':'synthetic'});self.id=p['id']
        self.store.start(self.id,{'kind':'analyze'});spec=self.store.claim();job=spec['snapshot']['job']
        self.store.progress(self.id,job,{'type':'status','phase':'retry_wait','retry':1,'maxRetries':3,'delayMs':120000,'code':'SERVER','message':'PRIVATE provider details'})
        record=self.store.load(self.id)['job'];self.assertEqual(record['status'],'running')
        self.assertEqual(record['modelRetry']['attempt'],1);self.assertEqual(record['modelRetry']['maximum'],3)
        self.assertAlmostEqual(record['modelRetry']['nextAt']-time.time(),120,delta=2)
        self.assertNotIn('PRIVATE',json.dumps(record))
        self.store.progress(self.id,job,{'type':'status','phase':'retry_started','retry':1})
        self.assertNotIn('modelRetry',self.store.load(self.id)['job'])
        self.store.progress(self.id,job,{'type':'status','phase':'retry_wait','retry':1,'maxRetries':3,'delayMs':-1})
        self.assertNotIn('modelRetry',self.store.load(self.id)['job'])
        self.store.cancel(self.id)
        self.store.progress(self.id,job,{'type':'status','phase':'retry_wait','retry':2,'maxRetries':3,'delayMs':240000})
        self.assertEqual(self.store.load(self.id)['job']['status'],'cancelling')
        self.assertNotIn('modelRetry',self.store.load(self.id)['job'])

    def test_analysis_selects_gpt_and_does_not_start_review(self):
        p=self.store.create({'name':'分析','requirements':'需求'});self.id=p['id']
        self.store.start(self.id,{'kind':'analyze'});self.store.work_once();data=self.store.load(self.id)
        self.assertEqual(data['job']['status'],'completed');self.assertEqual(self.stages(data),[('analysis','gpt-6.1-sol')]);self.assertNotIn('reviews',data['job'])

    def test_business_development_passes_review_before_becoming_acceptable(self):
        data=self.build();self.assertEqual(data['job']['status'],'completed')
        self.assertEqual(self.stages(data),[('development','gpt-6.1-sol'),('review','gpt-6.1-sol')])
        self.assertEqual(data['job']['reviews'][0]['verdict'],'pass');self.assertEqual(data['built_job'],data['job']['id']);self.assertIsNone(data['accepted'])
        self.store.accept(self.id,{'jobId':data['built_job']})

    def test_actionable_review_routes_back_to_development_then_review(self):
        data=self.build('REVIEW_FIX')
        self.assertEqual(data['job']['status'],'completed')
        self.assertEqual(self.stages(data),[('development','gpt-6.1-sol'),('review','gpt-6.1-sol'),('repair','gpt-6.1-sol'),('review','gpt-6.1-sol')])
        self.assertEqual([r['verdict'] for r in data['job']['reviews']],['changes_requested','pass'])
        self.assertTrue((self.store.directory(self.id)/'workspace/repair-marker.txt').is_file())

    def test_round_limit_stops_and_prevents_acceptance(self):
        data=self.build('REVIEW_ALWAYS');self.assertEqual(data['job']['status'],'completed');self.assertIn('验证未通过',data['job']['message'])
        self.assertEqual(len(data['job']['reviews']),2);self.assertEqual(len(self.stages(data)),4);self.assertIsNotNone(data['built_from']);self.assertEqual(data['reviewState']['status'],'blocked')
        with self.assertRaises(Problem):self.store.accept(self.id,{'jobId':data['job']['id']})

    def test_inconclusive_invalid_and_failed_reviews_never_approve(self):
        for requirement in ('REVIEW_INCONCLUSIVE','REVIEW_BAD','REVIEW_FAIL_PROCESS'):
            with self.subTest(requirement=requirement):
                data=self.build(requirement);self.assertEqual(data['job']['status'],'completed');self.assertIsNotNone(data['built_from']);self.assertEqual(len(self.stages(data)),2)
                self.assertEqual(data['reviewState']['status'],'pending')
                with self.assertRaises(Problem):self.store.accept(self.id,{'jobId':data['built_job']})

    def test_medium_findings_trigger_bounded_repair_and_block_acceptance(self):
        data=self.build('REVIEW_MEDIUM')
        self.assertEqual(data['reviewState']['status'],'blocked');self.assertEqual(len(self.stages(data)),4)
        data['reviewState']['status']='advisories';self.store.save(data)
        with self.assertRaises(Problem):self.store.accept(self.id,{'jobId':data['built_job']})

    def test_review_repair_continues_existing_source_and_cannot_use_stale_reports(self):
        data=self.build('REVIEW_ALWAYS');old=data['built_job']
        workspace=self.store.directory(self.id)/'workspace';(workspace/'existing-feature.txt').write_text('preserved')
        self.store.start(self.id,{'kind':'iterate','route':'business','reviewJobId':old,'note':'继续修复','target':'审查问题'})
        self.store.work_once();data=self.store.load(self.id)
        self.assertEqual(data['reviewState']['status'],'passed')
        self.assertEqual((workspace/'existing-feature.txt').read_text(),'preserved')
        self.assertTrue((workspace/'continued-review.txt').is_file())
        with self.assertRaises(Problem):self.store.start(self.id,{'kind':'iterate','reviewJobId':old,'note':'旧报告'})

    def test_recheck_receives_previous_findings_instead_of_restarting_full_review(self):
        data=self.build('REVIEW_FIX')
        log=(self.store.directory(self.id)/('job-'+data['job']['id']+'.log')).read_text()
        focus=[item['focus'] for raw in log.splitlines() if (item:=json.loads(raw)).get('type')=='fixtureReviewFocus']
        self.assertEqual([item['mode'] for item in focus],['full','recheck'])
        self.assertEqual(focus[1]['previousReview']['findings'][0]['id'],'bug-1')

    def test_unverified_code_cannot_be_exported_even_with_forged_acceptance(self):
        data=self.build('REVIEW_ALWAYS');data['accepted']=data['built_job'];self.store.save(data)
        with self.assertRaisesRegex(Problem,'审查'):self.store.bundle(self.id)

    def test_queued_legacy_full_mode_retains_its_original_review_limit(self):
        self.project('REVIEW_ALWAYS');policy={**model_policy(),'reviewMode':'full','maxReviewRounds':3}
        with patch('server.model_policy',return_value=policy):self.store.start(self.id,{'kind':'build'})
        self.store.work_once();data=self.store.load(self.id)
        self.assertEqual(data['job']['status'],'failed');self.assertEqual(len(data['job']['reviews']),3)

    def test_local_iteration_requires_final_audit_without_redevelopment(self):
        self.build()
        self.store.start(self.id,{'kind':'iterate','note':'局部页面改动'})
        self.store.work_once();data=self.store.load(self.id)
        self.assertFalse(data['reviewState']['full'])
        with self.assertRaisesRegex(Problem,'完整审查'):self.store.accept(self.id,{'jobId':data['built_job']})
        marker=self.store.directory(self.id)/'workspace/existing-feature.txt';marker.write_text('preserved')
        self.store.start(self.id,{'kind':'iterate','finalReview':True,'note':'交付前审查'})
        self.store.work_once();data=self.store.load(self.id)
        self.assertTrue(data['reviewState']['full']);self.assertEqual(data['reviewState']['status'],'passed')
        self.assertEqual(self.stages(data),[('review','gpt-6.1-sol')])
        self.assertEqual(marker.read_text(),'preserved')
        self.store.accept(self.id,{'jobId':data['built_job']})

    def test_basic_syntax_failures_go_to_repair_before_model_review(self):
        self.project();workspace=self.store.directory(self.id)/'workspace';workspace.mkdir(exist_ok=True)
        (workspace/'broken.py').write_text('def broken(\n')
        self.store.start(self.id,{'kind':'build'});self.store.work_once();data=self.store.load(self.id)
        self.assertEqual(data['reviewState']['status'],'blocked')
        self.assertEqual([stage for stage,model in self.stages(data)],['development','repair'])
        self.assertTrue(all(report['scope']=='basic' for report in data['job']['reviews']))

    def test_pending_review_does_not_release_dependent_queue(self):
        self.project('REVIEW_ALWAYS')
        self.store.start(self.id,{'kind':'build'})
        queued=self.store.start(self.id,{'kind':'iterate','note':'依赖前一步','enqueue':True})['submittedJob']['id']
        self.store.work_once();self.store.work_once()
        row=self.store.db.execute('SELECT state FROM jobs WHERE id=?',(queued,)).fetchone()
        self.assertEqual(row[0],'blocked')

    def test_review_changes_cannot_modify_original_application(self):
        data=self.build('REVIEW_MUTATE');self.assertEqual(data['job']['status'],'completed')
        self.assertEqual((self.store.directory(self.id)/'workspace/preview.html').read_text(),'<h1>测试预览</h1>')

    def test_queued_policy_is_immutable_and_all_stages_share_one_deadline(self):
        self.project('REVIEW_FIX');policy=model_policy();policy.pop('assistantModels',None);self.store.start(self.id,{'kind':'build'})
        deadlines=[];original=self.store.invoke_stage
        def invoke(*args,**kwargs):deadlines.append(args[10]);return original(*args,**kwargs)
        with patch('server.model_policy',side_effect=ValueError('changed later')),patch.object(self.store,'invoke_stage',side_effect=invoke):self.store.work_once()
        data=self.store.load(self.id);self.assertEqual(data['job']['status'],'completed');self.assertEqual(data['job']['models'],policy)
        self.assertEqual(len(set(deadlines)),1)

    def test_cancellation_in_review_stops_before_repairs_and_retains_source(self):
        self.project('REVIEW_FIX');root=Path(self.temp.name);ready=root/'review-ready';release=root/'review-release'
        self.store.launch_environment={'FIXTURE_REVIEW_READY':str(ready),'FIXTURE_REVIEW_RELEASE':str(release)}
        self.store.start(self.id,{'kind':'build'});thread=threading.Thread(target=self.store.work_once);thread.start()
        try:
            deadline=time.monotonic()+10
            while not ready.exists():
                if time.monotonic()>deadline:self.fail('review did not start')
                time.sleep(.01)
            self.store.cancel(self.id);thread.join(10);self.assertFalse(thread.is_alive())
            data=self.store.load(self.id);self.assertEqual(data['job']['status'],'cancelled');self.assertIsNone(data['built_from'])
            self.assertFalse((self.store.directory(self.id)/'workspace/repair-marker.txt').exists())
        finally:release.touch();thread.join(10)

    def test_review_copy_excludes_dependencies_credentials_and_symlinks(self):
        root=Path(self.temp.name)/'source';root.mkdir()
        for name in ('node_modules','.studio'):(root/name).mkdir();(root/name/'x').write_text('private')
        (root/'.env').write_text('NOT_A_REAL_KEY');(root/'app.py').write_text('app');(root/'alias').symlink_to(root/'.env')
        copy=ReviewCopy(root)
        try:self.assertEqual([path.name for path in copy.root.iterdir()],['app.py'])
        finally:copy.close()

    def test_model_policy_and_review_reject_invalid_boundaries(self):
        with self.assertRaises(ValueError):validate_review({'summary':'bad','verdict':'pass','findings':[],'checks':[]})
        root=Path(self.temp.name)/'config.json';root.write_text(json.dumps({**model_policy(),'maxReviewRounds':0}))
        with self.assertRaises(ValueError):model_policy(root)

    def test_worker_recovery_marks_active_stage_interrupted_and_preserves_reports(self):
        self.project();self.store.start(self.id,{'kind':'build'});spec=self.store.claim()
        self.store.workflow_stage(self.id,spec['snapshot']['job'],'review','gpt-6.1-sol',1)
        self.store.recover_worker();data=self.store.load(self.id)
        self.assertEqual(data['job']['status'],'interrupted');self.assertEqual(data['job']['workflowHistory'][-1]['status'],'interrupted')

    def test_existing_worker_requires_new_workflow_capability(self):
        self.project()
        with self.store.transaction():self.store.db.execute('INSERT INTO worker(id,pid,heartbeat,stop_requested) VALUES(1,123,0,0)')
        with self.assertRaisesRegex(Problem,'重启 Worker'):self.store.start(self.id,{'kind':'build'})
