"""Deterministic subprocess fixture; never used by the workbench runtime."""

import json
from pathlib import Path
import re
import sys
import os
import time


prompt = sys.stdin.read()
fixture_args=sys.argv[1:]
if "--session-id" in fixture_args:
    offset=fixture_args.index("--session-id")
    assert fixture_args[offset+1]=="fixture-session"
    fixture_args=fixture_args[:offset]+fixture_args[offset+2:]
if fixture_args[-3:] != ["--profile", "headless", "--json"]:
    sys.exit(11)
result = Path(re.search(r"(?:写入|写入 )\s*(\S*result-[a-f0-9]+\.json)", prompt)[1].rstrip("，。"))
request = Path(re.search(r"读取输入文件 (\S*request-[a-f0-9]+\.json)", prompt)[1])
# Match the workspace-only file access enforced by the real Harness sandbox.
if not result.resolve().is_relative_to(Path.cwd()) or not request.resolve().is_relative_to(Path.cwd()):
    sys.exit(12)
inputs = json.loads(request.read_text())
if any(not Path(reference).resolve().is_relative_to(Path.cwd()) for reference in inputs.get("references", [])):
    sys.exit(13)
for document in inputs.get('documents',[]):
    for filename in [document['originalFile'],document['textFile'],*(item['path'] for item in document['images'])]:
        if not Path(filename).resolve().is_relative_to(Path.cwd()) or not Path(filename).is_file():sys.exit(15)
for attachment in inputs.get('attachments',[]):
    original=Path(attachment['path'])
    if not original.resolve().is_relative_to(Path.cwd()) or not original.is_file():sys.exit(16)
print(json.dumps({"type":"session","sessionId":"fixture-session"}), flush=True)
print(json.dumps({"type":"status","phase":"step_start"}), flush=True)
print(json.dumps({"type":"thinking","text":"PRIVATE_REASONING_NOT_FOR_UI"}), flush=True)
if os.environ.get("FIXTURE_READY"):
    Path(os.environ["FIXTURE_READY"]).touch()
    deadline=time.monotonic()+float(os.environ.get("FIXTURE_WAIT_SECONDS", "10"))
    while not Path(os.environ["FIXTURE_RELEASE"]).exists():
        if time.monotonic()>deadline:
            sys.exit(14)
        time.sleep(.02)
patches=[sys.argv[index+1] for index,value in enumerate(sys.argv[:-1]) if value=='--patch']
model='legacy'
if patches:
    overlay=json.loads(Path(patches[-1]).read_text())
    for row in overlay:
        if row['id']=='agent-default-model':model=row['config']['model']
print(json.dumps({'type':'fixtureModel','model':model,'stage':'review' if 'STUDIO_REVIEW' in prompt else 'repair' if 'STUDIO_REPAIR' in prompt else 'analysis' if '只做需求分析' in prompt else 'development'}),flush=True)
requirement=inputs.get('requirements','')
if 'FALLBACK_' in requirement and (model=='gpt-6.1-sol' or 'FALLBACK_BOTH' in requirement):
    code='AUTH' if 'FALLBACK_AUTH' in requirement else 'SERVER'
    if 'FALLBACK_UNKNOWN_TOOL' in requirement:print(json.dumps({'type':'tool_call','callId':'pending-tool'}),flush=True)
    print(json.dumps({'type':'status','phase':'retry_started','retry':1}),flush=True)
    print(json.dumps({'type':'status','phase':'turn_end','reason':{'kind':'error','error':{'code':code,'message':'fixture model failure'}}}),flush=True)
    sys.exit(9)
if 'STUDIO_CHAT' in prompt:
    Path('preview.html').write_text('chat changed only the disposable copy')
    result.write_text(json.dumps({'answer':'fixture answer: '+inputs['question']+'; previous='+str(len(inputs['conversation'])),**({'intent':'modify' if 'AUTO_MODIFY' in inputs['question'] else 'answer'} if inputs.get('autoScope') else {})}))
elif 'STUDIO_REVIEW' in prompt:
    requirement=inputs.get('requirements','')
    print(json.dumps({'type':'fixtureReviewFocus','focus':inputs.get('reviewFocus',{})}),flush=True)
    if 'REVIEW_FAIL_PROCESS' in requirement:sys.exit(9)
    if os.environ.get('FIXTURE_REVIEW_READY'):
        Path(os.environ['FIXTURE_REVIEW_READY']).touch()
        while not Path(os.environ['FIXTURE_REVIEW_RELEASE']).exists():time.sleep(.02)
    finding={'id':'bug-1','severity':'high','file':'README.md','line':1,'trigger':'fixture trigger','evidence':'fixture evidence','suggestion':'create repair-marker.txt'}
    report={'summary':'fixture review passed','verdict':'pass','findings':[],'checks':[{'command':'fixture: README exists','status':'passed','result':str(Path('README.md').is_file())}]}
    if 'REVIEW_ALWAYS' in requirement and not Path('continued-review.txt').is_file() or 'REVIEW_FIX' in requirement and not Path('repair-marker.txt').is_file():report.update(summary='fixture bug found',verdict='changes_requested',findings=[finding])
    if 'REVIEW_MEDIUM' in requirement:report.update(summary='fixture advisory',verdict='changes_requested',findings=[{**finding,'severity':'medium'}])
    if 'REVIEW_INCONCLUSIVE' in requirement:report.update(summary='fixture missing dependency',verdict='inconclusive',checks=[])
    if 'REVIEW_BAD' in requirement:report['findings']=[finding]
    if 'REVIEW_MUTATE' in requirement:Path('preview.html').write_text('reviewer wrote only disposable copy')
    result.write_text(json.dumps(report))
elif "只做需求分析" in prompt:
    result.write_text(json.dumps({key: f'<h2>已分析 {key}</h2><p>需求与待确认项</p><pre class="mermaid">flowchart LR\n A["导入需求"] --&gt; B["评审方案"]</pre>' for key in ("prd", "frontend", "backend", "database")}, ensure_ascii=False))
elif inputs.get('route')=='style':
    if 'STYLE_NEEDS_BUSINESS' in inputs['feedback']:
        pass
    elif 'STYLE_OUT_OF_SCOPE' in inputs['feedback']:
        Path('backend.py').write_text('unexpected backend change')
    elif 'STYLE_SCRIPT_CHANGE' in inputs['feedback']:
        Path('preview.html').write_text('<style>body{color:blue}</style><script>changed()</script>')
    else:
        for name in inputs['allowedFiles']:
            if name.endswith('.css'):
                Path(name).write_text(Path(name).read_text()+'\n/* fixture style adjustment */\n');break
        else:
            for name in inputs['allowedFiles']:
                if name.endswith('.html'):
                    content=Path(name).read_text()
                    Path(name).write_text(content.replace('</style>','\nbody{color:blue}\n</style>',1));break
    result.write_text(json.dumps({'summary':'fixture style adjustment','needsBusiness':'STYLE_NEEDS_BUSINESS' in inputs['feedback']}))
else:
    if inputs.get('priorReview'):Path('continued-review.txt').write_text('continued from previous review')
    if 'STUDIO_REPAIR' in prompt:Path('repair-marker.txt').write_text('fixed fixture bug')
    for name in ("README.md", "Dockerfile", "compose.yaml", ".env.example", "VALIDATION.md"):
        Path(name).write_text("fixture only; not a real application\n")
    Path("preview.html").write_text("<h1>测试预览</h1>")
    result.write_text(json.dumps({"summary": "fixture development result"}))

print(json.dumps({"type":"final","text":"fixture completed"}), flush=True)
