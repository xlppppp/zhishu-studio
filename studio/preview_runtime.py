"""Isolated local Python preview with an owned port, sandbox, proxy, and database.

Runtime code never inherits model credentials. macOS sandbox-exec confines writes
and denies outbound connections. Other hosts fail explicitly rather than weaken
confinement. The bridge is served from a different origin than the workbench.
"""

import http.client
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie, CookieError
from urllib.parse import urlsplit, unquote
import uuid


BRIDGE = Path(__file__).parent / 'web/preview-bridge.js'


def bridge_script(channel, parent_origin):
    """Inject only server-generated routing data, before application listeners."""
    config = json.dumps({'channel':channel,'parentOrigin':parent_origin})
    return '<script>window.__STUDIO_BRIDGE__='+config+';</script><script>'+BRIDGE.read_text()+'</script>'


def inject_bridge(html, channel, parent_origin):
    """Place the bridge before app scripts while preserving document structure."""
    script = bridge_script(channel, parent_origin)
    head = re.search(r'<head(?:\s[^>]*)?>',html,re.I)
    if head:
        return html[:head.end()]+script+html[head.end():]
    return script+html


def sandbox_profile(workspace, runtime_root):
    """Allow Python dependencies and workspace data; deny outbound networking."""
    roots = [str(workspace.resolve()),str(runtime_root.resolve()),'/System','/usr','/bin','/sbin','/Library','/opt/homebrew','/private/etc','/dev','/private/var/db/dyld','/private/var/db/oah','/private/preboot']
    reads=' '.join('(subpath '+json.dumps(root)+')' for root in roots)
    writes=' '.join('(subpath '+json.dumps(str(root.resolve()))+')' for root in (workspace,runtime_root))
    return f'''(version 1)
(deny default)
(allow process*)
(allow sysctl-read)
(allow mach-lookup)
(allow file-read-metadata)
(allow file-read* (literal "/") {reads})
(allow signal (target self))
(allow file-write* {writes} (literal "/dev/null"))
(allow network-inbound (local ip "localhost:*"))
'''


class RuntimeManager:
    """Own preview lifetimes in the HTTP process, independently of task Workers."""

    def __init__(self, store, parent_origin):
        self.store=store
        self.parent_origin=parent_origin
        self.operations=threading.RLock()
        self.lock=threading.RLock()
        self.entries={}

    def status(self, project_id):
        """Return public lifecycle fields, never backend ports or environment values."""
        with self.lock:
            entry=self.entries.get(project_id)
            if entry is None:
                return {'status':'stopped','message':'尚未启动运行预览'}
            if entry['status']=='running' and entry.get('process') and entry['process'].poll() is not None:
                entry.update(status='failed',message='预览后端已退出，请查看预览日志后重新启动',url=None)
            visible=entry
            if entry['status'] in ('starting','failed') and entry.get('previous'):
                visible=entry['previous']
            result={key:visible.get(key) for key in ('status','message','url','channel','revision')}
            result['targetRevision']=entry.get('revision')
            result['replacementStatus']=entry['status'] if visible is not entry else None
            if visible is not entry:result['message']='新版本启动失败，保留原预览：'+entry['message'] if entry['status']=='failed' else '助手修改已完成，正在启动新版本；当前预览继续运行'
            return result

    def preflight(self, project_id):
        """Report preview prerequisites without executing generated code or migrations."""
        with self.store.transaction():
            project=self.store.load(project_id)
            checks=[{'name':'已确认方案且已有项目文件','ok':bool(project.get('approved') and project.get('hasWorkspaceProgress'))},
                    {'name':'任务已结束','ok':not bool(self.store.pending(project_id))},
                    {'name':'macOS 隔离运行环境','ok':sys.platform=='darwin' and shutil.which('sandbox-exec') is not None}]
            try:
                self.config(self.store.directory(project_id)/'workspace')
                checks.append({'name':'运行配置、Python 环境与前端入口','ok':True})
                detail='配置检查通过；依赖可导入、数据库迁移及健康检查将在启动时验证。'
            except (OSError,ValueError) as error:
                checks.append({'name':'运行配置、Python 环境与前端入口','ok':False})
                detail=str(error)
            return {'ready':all(item['ok'] for item in checks),'checks':checks,'detail':detail}

    def config(self, workspace):
        """Read the bounded Python manifest, or recognize the existing project layout."""
        path=workspace/'studio-preview.json'
        if path.is_file():
            if path.is_symlink() or path.stat().st_size>16384:
                raise ValueError('预览配置文件无效')
            value=json.loads(path.read_text())
            if not isinstance(value,dict) or value.get('kind') not in ('python-asgi','python-http'):
                raise ValueError('当前运行预览支持 python-asgi、python-http；其他技术栈需要独立运行适配')
        elif (workspace/'backend/app/main.py').is_file() and (workspace/'frontend/index.html').is_file():
            value={'kind':'python-asgi','cwd':'backend','python':'.venv/bin/python','app':'app.main:app','frontend':'frontend','health':'/api/v1/health'}
        else:
            raise ValueError('没有可用的运行配置，请生成 studio-preview.json；仍可使用静态演示')
        http=value['kind']=='python-http'
        config={'kind':value['kind']}
        for name,default in (('cwd','.' if http else 'backend'),('python',None if http else '.venv/bin/python'),('frontend','public' if http else 'frontend')):
            raw=value.get(name,default)
            if name=='python' and raw is None:
                config[name]=Path(sys.executable)
                continue
            if not isinstance(raw,str) or Path(raw).is_absolute() or '..' in Path(raw).parts:
                raise ValueError('预览配置的路径必须位于项目工作区内')
            candidate=workspace/raw
            if name!='python' and (candidate.is_symlink() or not candidate.resolve().is_relative_to(workspace.resolve())):
                raise ValueError('预览目录不能指向工作区外')
            config[name]=candidate
        app=value.get('app','app.main:app')
        health=value.get('health','/api/v1/health')
        if not http and (not isinstance(app,str) or not re.fullmatch(r'[A-Za-z_][\w.]*:[A-Za-z_]\w*',app)):
            raise ValueError('ASGI 应用入口无效')
        if not isinstance(health,str) or not re.fullmatch(r'/[A-Za-z0-9_./-]*',health) or '..' in health:
            raise ValueError('健康检查路径无效')
        if http:
            script=value.get('script','server.py')
            if not isinstance(script,str) or Path(script).is_absolute() or '..' in Path(script).parts:raise ValueError('HTTP 启动脚本必须位于工作目录内')
            target=config['cwd']/script
            if target.is_symlink() or not target.resolve().is_relative_to(config['cwd'].resolve()) or not target.is_file():raise ValueError('HTTP 启动脚本不存在或指向工作区外')
            config['script']=target.resolve()
        for name,default,maximum in (('maxRequestBytes',600*1024*1024,600*1024*1024),('requestTimeoutSeconds',120,600),('maxResponseBytes',64*1024*1024,600*1024*1024)):
            amount=value.get(name,default)
            if type(amount) is not int or not 1<=amount<=maximum:raise ValueError(name+' 超出允许范围')
            config[name]=amount
        cookies=value.get('cookieNames',[])
        if not isinstance(cookies,list) or len(cookies)>16 or any(not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}',name) for name in cookies):raise ValueError('cookieNames 必须是最多 16 个有效会话 Cookie 名称')
        config.update(app=app,health=health,cookie_names=cookies)
        if not config['python'].is_file() or not config['cwd'].is_dir() or not (config['frontend']/'index.html').is_file():
            raise ValueError('预览缺少 Python 虚拟环境、后端目录或前端 index.html，请查看项目 README')
        return config

    def start(self, project_id):
        """Schedule startup for confirmed projects with saved source and local runtime."""
        with self.lock:
            current=self.entries.get(project_id)
            project=self.store.load(project_id)
            revision=project.get('previewRevision')
            if current and current['status'] in ('starting','running') and current.get('revision')==revision:
                return self.status(project_id)
            previous=current if current and current['status']=='running' else current.get('previous') if current else None
            with self.store.transaction():
                project=self.store.load(project_id)
                self.store.ensure_idle(project)
                if not project.get('approved') or not project.get('hasWorkspaceProgress'):
                    raise ValueError('请先确认方案并生成项目文件，再启动运行预览')
                if sys.platform!='darwin' or shutil.which('sandbox-exec') is None:
                    raise ValueError('当前运行预览需要 macOS sandbox-exec；其他平台可使用静态演示')
                workspace=self.store.directory(project_id)/'workspace'
                config=self.config(workspace)
                channel=uuid.uuid4().hex
                entry={'revision':revision,'previous':previous,'status':'starting','message':'正在启动隔离的后端与预览数据库','url':None,'channel':channel,'stop':threading.Event(),'process':None,'server':None,'thread':None}
                frozen=self.store.directory(project_id)/'preview-runtime'/channel/'source'
                def ignored(directory,names):
                    from review_workflow import excluded_review_path
                    return [name for name in names if name not in ('dist','build') and excluded_review_path(Path(directory)/name)]
                shutil.copytree(workspace,frozen,ignore=ignored)
                frozen_config=self.config(frozen) if config['python']==Path(sys.executable) else None
                if frozen_config is None:
                    # The interpreter remains in the installed environment; application files are frozen.
                    frozen_config={key:(frozen/value.relative_to(workspace) if isinstance(value,Path) and key!='python' else value) for key,value in config.items()}
                config=frozen_config
                self.entries[project_id]=entry
                thread=threading.Thread(target=self.launch,args=(project_id,workspace,config,entry))
                entry['thread']=thread
                thread.start()
            return self.status(project_id)

    def launch(self, project_id, workspace, config, entry):
        """Initialize a private SQLite database, then serve frontend and proxied API."""
        runtime_base=self.store.directory(project_id)/'preview-runtime'
        runtime_root=runtime_base/entry['channel']
        runtime_root.mkdir(exist_ok=True)
        previous=entry.get('previous')
        old_database=runtime_base/previous['channel']/'preview.sqlite' if previous else runtime_base/'preview.sqlite'
        profile=sandbox_profile(workspace,runtime_root)
        env={key:os.environ[key] for key in ('PATH','LANG','SYSTEMROOT') if key in os.environ}
        env.update(TMPDIR=str(runtime_root),HOME=str(runtime_root),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',DATABASE_URL='sqlite:///'+str(runtime_root/'preview.sqlite'),AUTH_ENABLED='false',SCHEDULE_ENABLED='false',DISPATCH_ENABLED='false',LLM_PROVIDER='extractive',APP_ENV='development')
        if config['kind']=='python-http':env.update(DATABASE_PATH=str(runtime_root/'preview.sqlite'),HOST='127.0.0.1')
        def command(args):
            return ['sandbox-exec','-p',profile,str(config['python']),*args]
        listener=None
        try:
            active=runtime_base/'active.json'
            if previous is None and active.is_file():
                channel=json.loads(active.read_text()).get('channel')
                if not isinstance(channel,str) or not re.fullmatch('[a-f0-9]{32}',channel):raise ValueError('已保存的预览数据库位置无效，请检查 active.json')
                old_database=runtime_base/channel/'preview.sqlite'
            if old_database.is_file():
                with sqlite3.connect(old_database) as old, sqlite3.connect(runtime_root/'preview.sqlite') as new:old.backup(new)
            with (runtime_base/'runtime.log').open('ab',buffering=0) as log:
                if config['kind']=='python-asgi':
                    init=subprocess.Popen(command(['-m','alembic','upgrade','head']),cwd=config['cwd'],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
                    entry['process']=init
                    try:
                        init.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        self.terminate(init)
                        raise ValueError('预览数据库初始化超时，请查看预览日志')
                    if entry['stop'].is_set():
                        return
                    if init.returncode!=0:
                        raise ValueError(f'预览数据库初始化失败（退出码 {init.returncode}），请查看预览日志、迁移脚本与系统隔离权限')
                listener=socket.socket()
                listener.bind(('127.0.0.1',0))
                listener.listen(128)
                backend_port=listener.getsockname()[1]
                if config['kind']=='python-http':
                    env.update(STUDIO_PREVIEW_FD=str(listener.fileno()),PORT=str(backend_port))
                args=[str(config['script'])] if config['kind']=='python-http' else ['-m','uvicorn',config['app'],'--fd',str(listener.fileno()),'--no-access-log']
                process=subprocess.Popen(command(args),cwd=config['cwd'],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,pass_fds=(listener.fileno(),),start_new_session=True)
                entry['process']=process
                listener.close();listener=None
                deadline=time.monotonic()+20
                while not entry['stop'].is_set():
                    if process.poll() is not None:
                        raise ValueError('预览后端启动失败，请查看预览日志')
                    connection=http.client.HTTPConnection('127.0.0.1',backend_port,timeout=1)
                    try:
                        connection.request('GET',config['health'])
                        response=connection.getresponse();response.read()
                        if response.status==200:
                            break
                    except OSError:
                        pass  # Readiness is established only by a successful health response.
                    finally:
                        connection.close()
                    if time.monotonic()>deadline:
                        raise ValueError('预览健康检查超时，请查看预览日志')
                    entry['stop'].wait(.2)
                if entry['stop'].is_set():
                    return
                server=ThreadingHTTPServer(('127.0.0.1',0),PreviewHandler)
                server.frontend=config['frontend'].resolve();server.backend_port=backend_port
                server.channel=entry['channel'];server.parent_origin=self.parent_origin
                server.cookie_names=config['cookie_names']
                server.max_request_bytes=config['maxRequestBytes'];server.request_timeout=config['requestTimeoutSeconds']
                server.max_response_bytes=config['maxResponseBytes'];server.diagnostic_log=runtime_base/'runtime.log'
                entry['server']=server
                serving=threading.Thread(target=server.serve_forever)
                serving.start()
                try:
                    marker=runtime_base/(entry['channel']+'.json.tmp')
                    marker.write_text(json.dumps({'channel':entry['channel'],'url':f'http://127.0.0.1:{server.server_port}/','proxyLimits':{key:config[key] for key in ('maxRequestBytes','maxResponseBytes','requestTimeoutSeconds')}}));marker.replace(runtime_base/'active.json')
                    with self.lock:
                        entry.update(status='running',message='运行预览已就绪：独立数据库、网络隔离；不代表审查或功能验收通过',url=f'http://127.0.0.1:{server.server_port}/')
                    if previous:
                        previous['stop'].set()
                        previous['thread'].join(timeout=35)
                        if previous['thread'].is_alive():raise ValueError('新版本已启动，但旧预览未正常退出，请检查预览日志')
                        entry['previous']=None
                    entry['stop'].wait()
                finally:
                    server.shutdown();server.server_close();serving.join()
        except (OSError,ValueError,sqlite3.Error) as error:
            with self.lock:
                entry.update(status='failed',message=str(error),url=None)
        finally:
            if listener:
                listener.close()
            process=entry.get('process')
            if process:
                self.terminate(process)
            if entry['stop'].is_set():
                entry.update(status='stopped',message='运行预览已停止，预览数据已保留',url=None)

    @staticmethod
    def terminate(process):
        """Release only owned preview process groups, including migration children."""
        try:
            os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait()

    def stop(self, project_id):
        """Stop and join startup or running preview before source edits begin."""
        # Never hold the manager lock while joining its startup thread.
        with self.lock:
            entry=self.entries.get(project_id)
            if entry is None:
                return self.status(project_id)
            entry['stop'].set()
            previous=entry.get('previous')
            if previous:previous['stop'].set()
            process=entry.get('process')
        if process:
            self.terminate(process)
        thread=entry.get('thread')
        if thread and thread is not threading.current_thread():
            thread.join(timeout=35)
            if thread.is_alive():
                raise ValueError('预览尚未退出，请等待后再修改代码')
        if previous and previous.get('thread'):previous['thread'].join(timeout=35)
        return self.status(project_id)

    def close(self):
        """HTTP shutdown owns previews; independent development Workers are untouched."""
        for project_id in list(self.entries):
            self.stop(project_id)


class PreviewHandler(BaseHTTPRequestHandler):
    """Serve a dedicated frontend origin and proxy only owned backend /api paths."""

    def log_message(self,*args):
        pass  # Application payloads remain in the private preview, not Studio logs.

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def do_PUT(self):
        self.dispatch()

    def do_PATCH(self):
        self.dispatch()

    def do_DELETE(self):
        self.dispatch()

    def dispatch(self):
        origin=f'http://127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host')!=origin[7:]:
            self.send_error(403);return
        path=unquote(urlsplit(self.path).path)
        if self.command!='GET' and self.headers.get('Origin')!=origin:
            self.send_error(403);return
        if path.startswith('/api/'):
            self.proxy();return
        if self.command!='GET':
            self.send_error(405);return
        relative='index.html' if path in ('/','/app/') else path.removeprefix('/app/').lstrip('/')
        target=(self.server.frontend/relative).resolve()
        if self.server.frontend.is_symlink() or not target.is_relative_to(self.server.frontend) or any(part.startswith('.') for part in Path(relative).parts) or not target.is_file():
            self.send_error(404);return
        if target.stat().st_size>8*1024*1024:
            self.send_error(413);return
        body=target.read_bytes()
        kind=mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        if kind=='text/html':
            body=inject_bridge(body.decode(),self.server.channel,self.server.parent_origin).encode()
        self.respond(200,body,kind)

    def proxy(self):
        trace=uuid.uuid4().hex
        try:
            size=int(self.headers.get('Content-Length','0'))
            if self.headers.get('Transfer-Encoding'):
                self.respond(400,json.dumps({'error':'上传需要明确文件长度'}).encode(),'application/json');return
            if not 0<=size<=getattr(self.server,'max_request_bytes',600*1024*1024):
                self.close_connection=True
                self.respond(413,json.dumps({'error':'文件超过运行预览允许的上传大小，请减小文件或检查 studio-preview.json 的 maxRequestBytes'}).encode(),'application/json');return
            self.connection.settimeout(getattr(self.server,'request_timeout',120))
            def chunks():
                remaining=size
                while remaining:
                    chunk=self.rfile.read(min(64*1024,remaining))
                    if not chunk:raise OSError('上传未完成')
                    remaining-=len(chunk)
                    yield chunk
            body=chunks() if size else None
            headers={key:value for key,value in self.headers.items() if key.lower() in ('content-type','authorization','x-api-key','accept','idempotency-key','if-match')}
            headers['Content-Length']=str(size)
            prefix='studio_preview_'+self.server.channel+'_'
            names=getattr(self.server,'cookie_names',[])
            incoming=SimpleCookie(self.headers.get('Cookie',''))
            selected=SimpleCookie()
            for name in names:
                if prefix+name in incoming:selected[name]=incoming[prefix+name].value
            if selected:headers['Cookie']='; '.join(item.OutputString() for item in selected.values())
            connection=http.client.HTTPConnection('127.0.0.1',self.server.backend_port,timeout=getattr(self.server,'request_timeout',120))
            try:
                connection.request(self.command,self.path,body,headers)
                response=connection.getresponse()
                limit=getattr(self.server,'max_response_bytes',64*1024*1024)
                content=response.read(limit+1)
                if len(content)>limit:
                    self.diagnostic(trace,'response-too-large',responseBytes=len(content),limitBytes=limit)
                    self.respond(502,json.dumps({'error':'预览接口响应超过 '+str(limit)+' 字节；请在 studio-preview.json 调整 maxResponseBytes 后重新启动运行预览','code':'PREVIEW_RESPONSE_TOO_LARGE','traceId':trace}).encode(),'application/json');return
                if len(content)>8*1024*1024:self.diagnostic(trace,'large-response',responseBytes=len(content),status=response.status)
                cookies=[]
                for key,value in response.getheaders():
                    if key.lower()!='set-cookie':continue
                    for name,morsel in SimpleCookie(value).items():
                        if name not in names:continue
                        cookie=SimpleCookie();cookie[prefix+name]=morsel.value
                        item=cookie[prefix+name];item['path']='/';item['httponly']=True;item['samesite']='Strict'
                        for attr in ('max-age','expires'):
                            if morsel[attr]:item[attr]=morsel[attr]
                        cookies.append(item.OutputString())
                self.respond(response.status,content,response.getheader('Content-Type','application/json'),cookies)
            finally:
                connection.close()
        except (OSError,ValueError,CookieError,http.client.HTTPException) as error:
            self.close_connection=True
            self.diagnostic(trace,'upstream-error',errorType=type(error).__name__)
            self.respond(502,json.dumps({'error':'预览服务未完成请求，请查看预览日志后重试；上传校验可能失败，原页面保持运行','code':'PREVIEW_UPSTREAM_ERROR','traceId':trace}).encode(),'application/json')

    def respond(self,status,body,kind,cookies=()):
        try:
            self.send_response(status)
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(body)))
            for cookie in cookies:self.send_header('Set-Cookie',cookie)
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors "+self.server.parent_origin)
            self.end_headers();self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
            self.close_connection=True  # The preview client disconnected after dispatch.

    def diagnostic(self,trace,phase,**fields):
        """Record proxy metadata without query strings, payloads, cookies or credentials."""
        path=getattr(self.server,'diagnostic_log',None)
        if path is None:return
        record={'time':time.time(),'traceId':trace,'phase':phase,'method':self.command,'path':urlsplit(self.path).path,**fields}
        try:
            with path.open('a',encoding='utf-8') as output:output.write(json.dumps(record,ensure_ascii=False)+'\n')
        except OSError as error:
            print('Preview diagnostic write failed: '+type(error).__name__,file=sys.stderr)
