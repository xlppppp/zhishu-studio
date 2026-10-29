"""Project questions retain source and delivery state while using persisted history."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Store,Problem


class ProjectChatTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.store=Store(temporary.name,[sys.executable,str(Path(__file__).with_name('fake_harness.py'))]);self.addCleanup(self.store.close)
        self.project=self.store.create({'name':'问答','requirements':'测试需求'})
        self.id=self.project['id'];self.root=self.store.directory(self.id)/'workspace'
        self.root.mkdir(exist_ok=True);(self.root/'preview.html').write_text('original source')
        (self.root/'.env').write_text('private fixture')

    def test_question_preserves_source_design_and_accepted_build(self):
        data=self.store.load(self.id);data.update(built_from='design',built_job='build',accepted='build',reviewState={'status':'passed','sourceJob':'build'});self.store.save(data)
        self.store.start(self.id,{'kind':'chat','note':'页面为什么报错？','model':'gpt-6-sol','requestId':'a'*32})
        self.store.work_once();data=self.store.load(self.id)
        self.assertEqual(data['job']['status'],'completed',data['job']['message'])
        self.assertEqual((self.root/'preview.html').read_text(),'original source')
        self.assertEqual((data['built_from'],data['built_job'],data['accepted']),('design','build','build'))
        self.assertEqual(data['reviewState']['status'],'passed');self.assertIsNone(data['plan'])
        self.assertEqual(data['job']['models']['analysis'],'gpt-6-sol')
        self.assertEqual(data['job']['models']['stageProviders']['analysis'],'gpt-ge-default')
        self.assertEqual(data['job']['models']['reasoning'],'high')
        transcript=[{key:message[key] for key in ('role','text')} for message in data['chatHistory']]
        self.assertEqual(transcript,json.loads(Path(__file__).with_name('project-chat.expected.json').read_text()))
        self.store.start(self.id,{'kind':'chat','note':'继续解释','requestId':'b'*32});self.store.work_once()
        self.assertIn('previous=2',self.store.load(self.id)['job']['message'])

    def test_duplicate_question_is_one_message_and_model_change_requires_new_id(self):
        body={'kind':'chat','note':'问题','requestId':'c'*32}
        self.store.start(self.id,body);self.store.start(self.id,body)
        self.assertEqual(len(self.store.load(self.id)['chatHistory']),2)
        with self.assertRaises(Problem):self.store.start(self.id,{**body,'model':'gpt-6-sol'})
        with self.assertRaises(Problem):self.store.start(self.id,{'kind':'chat','note':'问题','model':'unconfigured','enqueue':True})

    def test_failed_question_keeps_the_question_and_does_not_confirm_a_build(self):
        self.store.command=[sys.executable,'-c','import sys;sys.stdin.read();sys.exit(9)']
        self.store.start(self.id,{'kind':'chat','note':'为什么失败？'});self.store.work_once()
        data=self.store.load(self.id)
        self.assertEqual(data['job']['status'],'failed');self.assertEqual(data['chatHistory'][0]['text'],'为什么失败？')
        self.assertIsNone(data['built_job']);self.assertIsNone(data.get('reviewState'))

    def test_question_queued_after_failed_task_can_explain_the_failure(self):
        command=self.store.command
        self.store.command=[sys.executable,'-c','import sys;sys.stdin.read();sys.exit(9)']
        self.store.start(self.id,{'kind':'chat','note':'第一个问题'})
        self.store.command=command
        self.store.start(self.id,{'kind':'chat','note':'解释前次失败','enqueue':True})
        self.store.work_once();self.store.work_once()
        data=self.store.load(self.id)
        self.assertEqual(data['job']['status'],'completed',data['job']['message'])
        self.assertIn('解释前次失败',data['job']['message'])

    def test_old_worker_rejects_question_before_creating_a_task(self):
        with self.store.transaction():self.store.db.execute('INSERT INTO worker VALUES (1,123,0,0)')
        (self.store.root/'worker-capabilities.json').write_text(json.dumps({'pid':123,'modelRouting':1,'focusedReview':1,'stageRouting':1}))
        with self.assertRaisesRegex(Problem,'尚未启用项目聊天'):self.store.start(self.id,{'kind':'chat','note':'问题'})
        self.assertEqual(self.store.load(self.id)['chatHistory'],[])

    def test_new_conversations_restore_history_without_context_leakage(self):
        first='a'*32;second='b'*32
        self.store.conversation(self.id,{'id':first})
        self.store.start(self.id,{'kind':'chat','note':'第一段','conversationId':first});self.store.work_once()
        self.store.conversation(self.id,{'id':second})
        self.store.start(self.id,{'kind':'chat','note':'第二段','conversationId':second});self.store.work_once()
        self.assertIn('previous=0',self.store.load(self.id)['job']['message'])
        self.store.start(self.id,{'kind':'chat','note':'接着第一段','conversationId':first});self.store.work_once()
        data=self.store.load(self.id);self.assertIn('previous=2',data['job']['message'])
        self.assertEqual(len(data['conversations']),3)
        self.assertEqual([item['title'] for item in data['conversations']][1:],['第一段','第二段'])
        with self.assertRaises(Problem):self.store.start(self.id,{'kind':'chat','note':'错误对话','conversationId':'c'*32})

    def test_automatic_question_does_not_enqueue_modification(self):
        self.store.start(self.id,{'kind':'chat','note':'解释错误，不修改','autoScope':'code'});self.store.work_once()
        data=self.store.load(self.id)
        self.assertEqual(data['job']['status'],'completed',data['job']['message'])
        self.assertEqual(self.store.pending(self.id),[])
        self.assertEqual((self.root/'preview.html').read_text(),'original source')

    def test_automatic_plan_change_runs_as_a_separate_guarded_task(self):
        self.store.edit(self.id,{'plan':{key:'设计内容' for key in ('prd','frontend','backend','database')},'baseVersion':0})
        self.store.start(self.id,{'kind':'chat','note':'AUTO_MODIFY 调整方案','autoScope':'plan'})
        self.store.work_once();pending=self.store.pending(self.id)
        self.assertEqual(len(pending),1)
        self.assertEqual(pending[0]['kind'],'revise')
        self.store.work_once();data=self.store.load(self.id)
        self.assertEqual(len(data['versions']),2)
        self.assertEqual(len([item for item in data['chatHistory'] if item['role']=='user']),1)
        self.assertEqual((self.root/'preview.html').read_text(),'original source')

    def test_automatic_code_change_still_requires_confirmed_design(self):
        self.store.start(self.id,{'kind':'chat','note':'AUTO_MODIFY 修复按钮','autoScope':'code'})
        self.store.work_once();data=self.store.load(self.id)
        self.assertEqual(data['job']['status'],'failed')
        self.assertIn('未开始修改',data['job']['message'])
        self.assertEqual(self.store.pending(self.id),[])
        self.assertEqual((self.root/'preview.html').read_text(),'original source')

    def test_automatic_code_change_does_not_contact_or_stop_preview(self):
        from unittest.mock import patch
        self.store.edit(self.id,{'plan':{key:'设计内容' for key in ('prd','frontend','backend','database')},'baseVersion':0})
        self.store.approve(self.id,{'baseVersion':1})
        self.store.preview_origin='http://127.0.0.1:12345'
        self.store.start(self.id,{'kind':'chat','note':'AUTO_MODIFY 修复按钮','autoScope':'code'})
        with patch('server.http.client.HTTPConnection',side_effect=AssertionError('must not stop preview')):self.store.work_once()
        pending=self.store.pending(self.id)
        self.assertEqual(pending[0]['kind'],'iterate')
        self.assertTrue(pending[0]['isolated'])
        self.assertEqual((self.root/'preview.html').read_text(),'original source')
        self.store.work_once()
        data=self.store.load(self.id)
        self.assertEqual(data['job']['status'],'completed',data['job']['message'])
        self.assertEqual(data['previewRevision'],data['job']['id'])

    def test_cancelled_assistant_edit_retains_published_code_and_draft(self):
        from unittest.mock import patch
        from server import ExecutionStopped
        self.store.edit(self.id,{'plan':{key:'设计内容' for key in ('prd','frontend','backend','database')},'baseVersion':0})
        self.store.approve(self.id,{'baseVersion':1})
        data=self.store.load(self.id);data.update(built_from=data['approved'],built_job='published',accepted='published',reviewState={'status':'passed','sourceJob':'published'});self.store.save(data)
        self.store.start(self.id,{'kind':'iterate','note':'修复','chatMessage':True})
        def edit(project_id,job,control,workspace,*args,**kwargs):
            (workspace/'preview.html').write_text('unfinished')
            current=self.store.load(self.id)
            self.assertEqual(current['built_job'],'published')
            self.assertEqual((self.root/'preview.html').read_text(),'original source')
            raise ExecutionStopped('cancelled','任务已取消')
        with patch.object(self.store,'invoke_stage',side_effect=edit):self.store.work_once()
        data=self.store.load(self.id)
        self.assertEqual(data['job']['status'],'cancelled');self.assertEqual(data['accepted'],'published')
        self.assertEqual(data['reviewState']['status'],'passed')
        self.assertEqual((self.root/'preview.html').read_text(),'original source')
        self.assertEqual((self.store.directory(self.id)/'assistant-drafts'/data['job']['id']/'preview.html').read_text(),'unfinished')

    def test_previous_modification_messages_remain_accessible_in_legacy_conversation(self):
        self.store.edit(self.id,{'plan':{key:'设计内容' for key in ('prd','frontend','backend','database')},'baseVersion':0})
        self.store.start(self.id,{'kind':'revise','note':'以前提交的方案意见','target':'PRD'})
        self.store.work_once();history=self.store.load(self.id)['chatHistory']
        self.assertEqual(history[0]['conversationId'],'legacy')
        self.assertEqual(history[0]['text'],'以前提交的方案意见')
        self.assertEqual(history[0]['target'],'PRD')

    def test_conversation_titles_persist_and_renaming_preserves_messages(self):
        identifier='d'*32;self.store.conversation(self.id,{'id':identifier})
        self.store.start(self.id,{'kind':'chat','note':'原始上下文','conversationId':identifier});self.store.work_once()
        before=self.store.load(self.id)['chatHistory']
        self.store.conversation(self.id,{'id':identifier,'operation':'rename','title':'地形导入排查'})
        self.store.conversation(self.id,{'id':'legacy','operation':'rename','title':'历史方案讨论'})
        data=self.store.load(self.id)
        self.assertEqual(data['conversations'][0]['title'],'历史方案讨论')
        self.assertEqual(data['conversations'][1]['title'],'地形导入排查')
        self.assertEqual(data['chatHistory'],before)
        self.store.start(self.id,{'kind':'chat','note':'接着上次','conversationId':identifier});self.store.work_once()
        self.assertIn('previous=2',self.store.load(self.id)['job']['message'])
        with self.assertRaises(Problem):self.store.conversation(self.id,{'id':identifier,'operation':'rename','title':' '})
        with self.assertRaises(Problem):self.store.conversation(self.id,{'id':identifier,'operation':'rename','title':'另一个名字','baseTitle':'过期名字'})

    def test_full_conversation_remains_available_after_recent_context_window(self):
        for number in range(8):
            self.store.start(self.id,{'kind':'chat','note':'历史问题 '+str(number)});self.store.work_once()
        self.store.start(self.id,{'kind':'chat','note':'回顾最早的问题'})
        record=self.store.load(self.id)['job'];self.store.work_once()
        archive=self.root/'.studio'/record['id']/'conversation-history.json'
        history=json.loads(archive.read_text())
        self.assertEqual(len(history),16);self.assertEqual(history[0]['text'],'历史问题 0')

    def test_uploaded_image_reaches_private_chat_copy_and_history(self):
        from unittest.mock import patch
        from test_document_cache import PNG
        import base64
        self.store.start(self.id,{'kind':'chat','note':'解释图片','target':'选区','contexts':['选区一','选区二'],'images':[{'name':'error.png','data':'data:image/png;base64,'+base64.b64encode(PNG).decode()}]})
        def answer(project_id,job,control,workspace,result,prompt,*args,**kwargs):
            request=json.loads((result.parent/result.name.replace('result-','request-')).read_text())
            image=Path(request['references'][0])
            self.assertTrue(image.is_relative_to(workspace));self.assertEqual(image.read_bytes(),PNG)
            self.assertEqual(request['contexts'],['选区一','选区二'])
            return {'answer':'读取了错误截图'}
        with patch.object(self.store,'invoke_stage',side_effect=answer):self.store.work_once()
        data=self.store.load(self.id);self.assertEqual(data['job']['status'],'completed',data['job']['message'])
        image=data['chatHistory'][0]['images'][0]
        self.assertEqual(image['name'],'error.png');self.assertIn('/chat-images/',image['url'])
        self.assertEqual((self.root/'.studio'/data['job']['id']/image['file']).read_bytes(),PNG)

    def test_invalid_chat_image_does_not_create_a_task(self):
        with self.assertRaises(Problem):self.store.start(self.id,{'kind':'chat','note':'图片','images':[{'name':'bad.png','data':'data:image/png;base64,YmFk'}]})
        self.assertEqual(self.store.pending(self.id),[])


    def test_selected_model_and_reasoning_persist_in_queued_policy(self):
        with self.assertRaisesRegex(Problem,'推理强度'):self.store.start(self.id,{'kind':'chat','note':'无效强度','reasoning':'ultra'})
        for model in ('gpt-6-astra','claude-sonnet-5-5'):
            for effort in ('low','medium','high','xhigh','max'):
                queued=self.store.start(self.id,{'kind':'chat','note':'测试选择','model':model,'reasoning':effort,'enqueue':True})
                policy=queued['submittedJob']['models']
                self.assertEqual(policy['analysis'],model);self.assertEqual(policy['development'],model)
                self.assertEqual(policy['reasoning'],effort)


    def test_automatic_modification_keeps_selected_reasoning(self):
        self.store.edit(self.id,{'plan':{key:'设计内容' for key in ('prd','frontend','backend','database')},'baseVersion':0})
        self.store.approve(self.id,{'baseVersion':1})
        self.store.start(self.id,{'kind':'chat','note':'AUTO_MODIFY 修复按钮','autoScope':'code','model':'gpt-6-astra','reasoning':'max'})
        self.store.work_once()
        child=self.store.pending(self.id)[0]
        self.assertEqual(child['models']['analysis'],'gpt-6-astra')
        self.assertEqual(child['models']['reasoning'],'max')

    def test_file_is_copied_to_chat_and_retained_after_workspace_changes(self):
        import base64
        from unittest.mock import patch
        content='实际错误内容'.encode()
        self.store.start(self.id,{'kind':'chat','note':'解释文件','files':[{'name':'error.txt','data':base64.b64encode(content).decode()}]})
        def answer(project_id,job,control,workspace,result,prompt,*args,**kwargs):
            request=json.loads((result.parent/result.name.replace('result-','request-')).read_text())
            attached=request['attachments'][0]
            self.assertTrue(Path(attached['path']).is_relative_to(workspace))
            self.assertEqual(Path(attached['path']).read_bytes(),content)
            self.assertEqual(Path(attached['textPath']).read_text(),'实际错误内容')
            return {'answer':'文件已读取'}
        with patch.object(self.store,'invoke_stage',side_effect=answer):self.store.work_once()
        data=self.store.load(self.id);self.assertEqual(data['job']['status'],'completed',data['job']['message'])
        file=data['chatHistory'][0]['files'][0]
        self.assertEqual(file['name'],'error.txt')
        self.assertEqual((self.store.directory(self.id)/'chat-files'/data['job']['id']/file['file']).read_bytes(),content)
        self.assertNotIn('path',file)

    def test_malformed_file_and_path_names_are_rejected_before_queueing(self):
        for attachment in ({'name':'bad.txt','data':'!!!'},{'name':'../outside','data':'YQ=='}):
            with self.assertRaises(Problem):self.store.start(self.id,{'kind':'chat','note':'文件','files':[attachment]})
        with self.assertRaises(Problem):self.store.start(self.id,{'kind':'chat','note':'太多文件','files':[{'name':'a.txt','data':'YQ=='}]*5})
        self.assertEqual(self.store.pending(self.id),[])
