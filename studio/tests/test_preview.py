"""Preview routing isolates app APIs and keeps inspection opt-in."""

import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from preview_runtime import RuntimeManager, PreviewHandler, inject_bridge, sandbox_profile


class PreviewTests(unittest.TestCase):
    """Use owned ephemeral ports and no model requests or application processes."""

    def test_bridge_precedes_application_listeners_and_starts_in_experience_mode(self):
        html=inject_bridge('<!doctype html><html><head><script>app()</script></head></html>','a'*32,'http://127.0.0.1:3088')
        self.assertLess(html.index("let mode='experience'"),html.index('app()'))
        self.assertIn("if(mode==='experience')return;",html)
        self.assertIn("event.origin!==config.parentOrigin",html)
        self.assertIn("event.data?.channel!==config.channel",html)
        self.assertIn("event.key==='Escape'",html)

    def test_manifest_rejects_path_escape_and_invalid_app(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory)
            manager=RuntimeManager(None,'http://127.0.0.1:3088')
            for fields in ({'cwd':'../outside'},{'frontend':'/tmp'},{'app':'app;rm:main'}):
                (workspace/'studio-preview.json').write_text(json.dumps({'kind':'python-asgi',**fields}))
                with self.assertRaises(ValueError):manager.config(workspace)

    def test_preflight_reports_missing_layout_without_launching_code(self):
        from server import Store
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory,[])
            try:
                project=store.create({'name':'预检','requirements':'测试预检'})
                manager=RuntimeManager(store,'http://127.0.0.1:3088')
                result=manager.preflight(project['id'])
                self.assertFalse(result['ready'])
                self.assertIn('没有可用',result['detail'])
                self.assertEqual(manager.entries,{})
                self.assertFalse((store.directory(project['id'])/'preview-runtime').exists())
            finally:store.close()

    def test_http_manifest_uses_host_python_and_rejects_escaped_script(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'public').mkdir()
            (root/'public/index.html').write_text('<html/>');(root/'server.py').write_text('')
            manifest=root/'studio-preview.json'
            manifest.write_text(json.dumps({'kind':'python-http','cookieNames':['session']}))
            manager=RuntimeManager(None,'http://127.0.0.1:3088')
            config=manager.config(root)
            self.assertEqual(config['python'],Path(sys.executable))
            self.assertEqual(config['script'],(root/'server.py').resolve())
            self.assertEqual(config['maxResponseBytes'],64*1024*1024)
            for invalid in (0,True,601*1024*1024):
                manifest.write_text(json.dumps({'kind':'python-http','maxResponseBytes':invalid}))
                with self.assertRaisesRegex(ValueError,'maxResponseBytes'):manager.config(root)
            manifest.write_text(json.dumps({'kind':'python-http','script':'../server.py'}))
            with self.assertRaises(ValueError):manager.config(root)

    def test_missing_configuration_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'没有可用'):
                RuntimeManager(None,'http://127.0.0.1:3088').config(Path(directory))

    def test_sandbox_denies_outbound_and_limits_writes(self):
        profile=sandbox_profile(Path('/tmp/preview-work'),Path('/tmp/preview-data'))
        self.assertIn('(deny default)',profile)
        self.assertNotIn('(allow network-outbound',profile)
        self.assertNotIn('(allow file-read*)',profile)
        self.assertIn('(allow file-write* (subpath',profile)


class PreviewHTTPTests(unittest.TestCase):
    """Frontend and API share an isolated origin with explicit write validation."""

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.root=Path(self.directory.name).resolve()
        (self.root/'index.html').write_text('<html><head></head><body>fixture</body></html>')
        (self.root/'.secret').write_text('private')
        class Backend(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith('/api/large'):
                    content=b'{"mesh":"'+b'x'*(9*1024*1024)+b'"}'
                    self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                    try:self.wfile.write(content)
                    except (BrokenPipeError,ConnectionResetError):pass
                    return
                self.send_response(200)
                self.send_header('Set-Cookie','session=demo; Domain=example.com; Path=/api')
                self.end_headers()
                self.wfile.write(json.dumps({'cookie':self.headers.get('Cookie','')}).encode())
            def do_POST(self):
                size=int(self.headers.get('Content-Length','0'));body=self.rfile.read(size)
                self.send_response(201);self.end_headers();self.wfile.write(json.dumps({'idempotency':self.headers.get('Idempotency-Key'),'received':len(body)}).encode())
            def log_message(self,*args):pass
        self.backend=ThreadingHTTPServer(('127.0.0.1',0),Backend)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),PreviewHandler)
        self.server.frontend=self.root;self.server.backend_port=self.backend.server_port
        self.server.channel='a'*32;self.server.parent_origin='http://127.0.0.1:3088'
        self.threads=[threading.Thread(target=server.serve_forever) for server in (self.backend,self.server)]
        for thread in self.threads:thread.start()

    def tearDown(self):
        for server in (self.server,self.backend):server.shutdown();server.server_close()
        for thread in self.threads:thread.join()
        self.directory.cleanup()

    def request(self,path,method='GET',headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            connection.request(method,path,headers=headers or {})
            response=connection.getresponse();return response.status,response.read(),dict(response.getheaders())
        finally:connection.close()

    def test_frontend_injects_channel_and_cannot_read_private_files(self):
        status,body,headers=self.request('/')
        self.assertEqual(status,200);self.assertIn(b'__STUDIO_BRIDGE__',body)
        self.assertIn("connect-src 'self'",headers['Content-Security-Policy'])
        self.assertEqual(self.request('/.secret')[0],404)
        self.assertEqual(self.request('/../outside')[0],404)

    def test_only_same_origin_writes_reach_backend(self):
        self.assertEqual(self.request('/api/items','POST')[0],403)
        self.assertEqual(self.request('/api/items','POST',{'Origin':'http://evil.example'})[0],403)
        self.assertEqual(self.request('/api/items','POST',{'Origin':f'http://127.0.0.1:{self.server.server_port}'})[0],201)
        self.assertEqual(self.request('/api/health')[0],200)

    def test_frontend_directory_replacement_cannot_expose_sibling_files(self):
        outside=self.root.parent/(self.root.name+'-private')
        outside.mkdir()
        try:
            (outside/'index.html').write_text('private data')
            frontend=self.root/'frontend';frontend.mkdir()
            self.server.frontend=frontend
            frontend.rmdir();frontend.symlink_to(outside,target_is_directory=True)
            self.assertEqual(self.request('/')[0],404)
        finally:
            frontend.unlink()
            (outside/'index.html').unlink();outside.rmdir()

    def test_write_preserves_idempotency_key(self):
        status,body,_=self.request('/api/items','POST',{'Origin':f'http://127.0.0.1:{self.server.server_port}','Idempotency-Key':'test-request'})
        self.assertEqual(status,201)
        self.assertEqual(json.loads(body)['idempotency'],'test-request')

    def test_only_this_preview_session_cookie_is_forwarded(self):
        self.server.cookie_names=['session']
        prefix='studio_preview_'+self.server.channel+'_'
        status,body,headers=self.request('/api/health',headers={'Cookie':prefix+'session=mine; session=foreign; studio_preview_other_session=other'})
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['cookie'],'session=mine')
        cookie=headers['Set-Cookie']
        self.assertIn(prefix+'session=demo',cookie)
        self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
        self.assertNotIn('Domain=',cookie)

    def test_foreign_host_rejected(self):
        self.assertEqual(self.request('/',headers={'Host':'evil.example'})[0],403)

    def test_large_mesh_response_crosses_proxy_without_old_eight_mib_truncation(self):
        self.server.diagnostic_log=self.root/'runtime.log'
        status,body,headers=self.request('/api/large?secret=omit')
        self.assertEqual(status,200);self.assertEqual(len(json.loads(body)['mesh']),9*1024*1024)
        log=json.loads(self.server.diagnostic_log.read_text())
        self.assertEqual(log['phase'],'large-response');self.assertEqual(log['responseBytes'],len(body))
        self.assertNotIn('secret',self.server.diagnostic_log.read_text())

    def test_response_limit_reports_json_and_trace_instead_of_html_502(self):
        self.server.max_response_bytes=1024;self.server.diagnostic_log=self.root/'runtime.log'
        status,body,headers=self.request('/api/large')
        self.assertEqual(status,502);self.assertIn('application/json',headers['Content-Type'])
        error=json.loads(body);self.assertEqual(error['code'],'PREVIEW_RESPONSE_TOO_LARGE')
        self.assertIn('maxResponseBytes',error['error'])
        self.assertEqual(json.loads(self.server.diagnostic_log.read_text())['traceId'],error['traceId'])

    def test_glb_upload_larger_than_four_mebibytes_reaches_backend(self):
        data=b'x'*(4*1024*1024+1)
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        try:
            connection.request('POST','/api/terrain',data,{'Origin':f'http://127.0.0.1:{self.server.server_port}','Content-Type':'model/gltf-binary'})
            response=connection.getresponse();body=response.read()
            self.assertEqual(response.status,201);self.assertEqual(json.loads(body)['received'],len(data))
        finally:connection.close()

    def test_oversized_upload_returns_actionable_json_without_backend_request(self):
        self.server.max_request_bytes=1024
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        try:
            connection.request('POST','/api/terrain',b'x'*1025,{'Origin':f'http://127.0.0.1:{self.server.server_port}'})
            response=connection.getresponse();body=response.read()
            self.assertEqual(response.status,413);self.assertIn('application/json',response.getheader('Content-Type'))
            self.assertIn('上传大小',json.loads(body)['error'])
        finally:connection.close()


class PreviewPublicationTests(unittest.TestCase):
    """Candidate startup keeps the previous frontend available until readiness."""

    def test_runtime_source_is_frozen_and_failed_candidate_keeps_previous_url(self):
        from server import Store
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory,[]);self.addCleanup(store.close)
            project=store.create({'name':'冻结预览','requirements':'预览'})
            identifier=project['id'];workspace=store.directory(identifier)/'workspace'
            (workspace/'public').mkdir(parents=True);(workspace/'public/index.html').write_text('old')
            (workspace/'server.py').write_text('pass')
            (workspace/'studio-preview.json').write_text(json.dumps({'kind':'python-http'}))
            project.update(approved='design');store.save(project)
            manager=RuntimeManager(store,'http://127.0.0.1:3088')
            launched=[]
            def launch(project_id, source, config, entry):launched.append((config,entry))
            with patch('preview_runtime.shutil.which',return_value='/usr/bin/sandbox-exec'),patch.object(manager,'launch',side_effect=launch):
                manager.start(identifier);manager.entries[identifier]['thread'].join(timeout=2)
                config,first=launched[0];first.update(status='running',url='http://127.0.0.1:12345/')
                (workspace/'public/index.html').write_text('new')
                self.assertEqual((config['frontend']/'index.html').read_text(),'old')
                project=store.load(identifier);project['previewRevision']='revision-2';store.save(project)
                manager.start(identifier);manager.entries[identifier]['thread'].join(timeout=2)
                second=manager.entries[identifier]
                self.assertEqual(manager.status(identifier)['url'],first['url'])
                second.update(status='failed',message='health failed')
                result=manager.status(identifier)
                self.assertEqual(result['status'],'running');self.assertEqual(result['url'],first['url'])
                self.assertIn('health failed',result['message']);self.assertFalse(first['stop'].is_set())


if __name__=='__main__':unittest.main()
