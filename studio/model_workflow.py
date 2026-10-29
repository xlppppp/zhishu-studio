"""Immutable model routing and bounded review copies for Studio tasks."""
import json
from pathlib import Path
import re
import shutil
import tempfile
from review_workflow import excluded_review_path


def model_policy(path=None):
    """Validate deployment settings before accepting a queued task."""
    return validate_policy(json.loads((path or Path(__file__).with_name('model-routing.json')).read_text()))


def validate_policy(policy):
    """Validate a durable queued model policy without applying current defaults."""
    if not isinstance(policy,dict) or not {'provider','analysis','development','review','maxReviewRounds'}<=set(policy) or set(policy)-{'provider','analysis','development','review','maxReviewRounds','input','reviewMode','fallback','stageProviders','reasoning','assistantModels'}:
        raise ValueError('model-routing.json 必须包含 provider、analysis、development、review、maxReviewRounds')
    for key in ('provider','analysis','development','review'):
        if not isinstance(policy[key],str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}',policy[key]):raise ValueError('模型路由字段无效：'+key)
    if type(policy['maxReviewRounds']) is not int or not 1<=policy['maxReviewRounds']<=5:raise ValueError('maxReviewRounds 必须为 1 至 5 的整数')
    if 'input' in policy and (not isinstance(policy['input'],list) or not policy['input'] or any(item not in ('text','image') for item in policy['input']) or 'text' not in policy['input'] or len(set(policy['input']))!=len(policy['input'])):raise ValueError('input 必须声明 text，可同时声明 image')
    if policy.get('reviewMode','full') not in ('full','focused'):raise ValueError('reviewMode 必须为 full 或 focused')
    if 'stageProviders' in policy:
        routes=policy['stageProviders']
        if not isinstance(routes,dict) or set(routes)!={'analysis','development','review'}:raise ValueError('stageProviders 必须包含 analysis、development、review')
        if any(not isinstance(route,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}',route) for route in routes.values()):raise ValueError('stageProviders 提供方路由无效')
    if 'reasoning' in policy and policy['reasoning'] not in ('low','medium','high','xhigh','max'):raise ValueError('reasoning 必须为 low、medium、high、xhigh 或 max')
    if 'assistantModels' in policy:
        names=policy['assistantModels']
        if not isinstance(names,list) or not names or len(names)>20 or any(not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}',name) for name in names) or len(set(names))!=len(names):raise ValueError('assistantModels 必须为不重复的模型名称列表')
    if 'fallback' in policy:
        fallback=policy['fallback']
        if not isinstance(fallback,dict) or set(fallback)!={'from','to','primaryRetries'}:raise ValueError('fallback 必须包含 from、to、primaryRetries')
        for key in ('from','to'):
            if not isinstance(fallback[key],str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}',fallback[key]):raise ValueError('fallback 模型无效：'+key)
        if fallback['from']==fallback['to'] or type(fallback['primaryRetries']) is not int or not 0<=fallback['primaryRetries']<=5:raise ValueError('fallback 模型必须不同，primaryRetries 必须为 0 至 5 的整数')
    return policy


def model_patch(directory,policy,stage):
    """Preserve the configured provider connection while selecting a stage model."""
    path=directory/'model.patch.yml'
    provider=policy.get('stageProviders',{}).get(stage,policy['provider'])
    models=[{'id':name,**({'input':policy['input']} if 'input' in policy else {}),**({'reasoningEfforts':{'off':None,policy['reasoning']:policy['reasoning']}} if 'reasoning' in policy else {})} for name in dict.fromkeys([*(policy[key] for key in ('analysis','development','review')), *([policy['fallback']['to']] if 'fallback' in policy else [])])]
    base=json.loads(Path(__file__).with_name('harness.patch.yml').read_text())
    providers=next(entry['config']['providers'] for entry in base if entry['id']=='llm-pi-ai')
    if provider not in providers:raise ValueError('harness.patch.yml 未配置模型提供方：'+provider)
    providers[provider]['models']=models
    if 'fallback' in policy and policy[stage]==policy['fallback']['from']:
        providers[provider]['retryPolicy']['maxRetries']=policy['fallback']['primaryRetries']
    if 'reasoning' in policy:providers[provider]['reasoning']=policy['reasoning']
    path.write_text(json.dumps([{'id':'llm-pi-ai','config':{'providers':providers}},
        {'id':'agent-default-model','config':{'provider':provider,'model':policy[stage],**({'reasoningEffort':policy['reasoning']} if 'reasoning' in policy else {})}}],indent=2)+'\n')
    return path


def validate_review(value):
    """Reject malformed, contradictory, or unsubstantiated passing reviews."""
    if not isinstance(value,dict) or set(value)!={'summary','verdict','findings','checks'}:raise ValueError('审查报告必须包含 summary、verdict、findings、checks')
    def string(item,key,limit=4000):
        result=item.get(key)
        if not isinstance(result,str) or not result.strip() or len(result)>limit:raise ValueError('审查字段无效：'+key)
        return result.strip()
    summary=string(value,'summary',10000);verdict=value['verdict']
    if verdict not in ('pass','changes_requested','inconclusive'):raise ValueError('审查 verdict 无效')
    if not isinstance(value['findings'],list) or len(value['findings'])>50 or not isinstance(value['checks'],list) or len(value['checks'])>50:raise ValueError('审查问题或检查数量无效')
    findings=[]
    for item in value['findings']:
        if not isinstance(item,dict):raise ValueError('审查问题必须为对象')
        finding={key:string(item,key) for key in ('id','severity','file','trigger','evidence','suggestion')}
        if finding['severity'] not in ('critical','high','medium','low'):raise ValueError('审查严重程度无效')
        path=Path(finding['file'])
        if path.is_absolute() or '..' in path.parts or '\\' in finding['file']:raise ValueError('审查文件必须为工作区相对路径')
        if type(item.get('line')) is not int or item['line']<1:raise ValueError('审查行号必须为正整数')
        finding['line']=item['line'];findings.append(finding)
    if len({item['id'] for item in findings})!=len(findings):raise ValueError('审查问题 ID 重复')
    checks=[]
    for item in value['checks']:
        if not isinstance(item,dict):raise ValueError('审查检查必须为对象')
        check={key:string(item,key) for key in ('command','status','result')}
        if check['status'] not in ('passed','failed','not_run'):raise ValueError('审查检查状态无效')
        checks.append(check)
    blockers=any(item['severity']!='low' for item in findings)
    if verdict=='pass' and (blockers or not checks or any(item['status']!='passed' for item in checks)):raise ValueError('审查通过必须没有阻塞问题，并有实际通过的检查；未验证项应返回 inconclusive')
    if verdict=='changes_requested' and not findings and not any(item['status']=='failed' for item in checks):raise ValueError('要求修复时必须提供问题或失败检查')
    return {'summary':summary,'verdict':verdict,'findings':findings,'checks':checks}


class ReviewCopy:
    """Review a disposable source copy, excluding credentials and dependencies.

    Normal review writes never return to the original. Harness still owns tool
    confinement; this copy does not grant additional filesystem permissions.
    """
    def __init__(self,workspace):
        self.temporary=tempfile.TemporaryDirectory(prefix='studio-review-');self.root=Path(self.temporary.name).resolve()
        total=count=0
        try:
            def excluded(directory,names):
                return [name for name in names if excluded_review_path(Path(directory)/name)]
            def copy(source,target):
                nonlocal total,count
                size=Path(source).stat().st_size;total+=size;count+=1
                if total>50*1024*1024 or count>5000:raise ValueError('审查源码超过 50 MB 或 5000 文件，请清理构建产物后重试')
                return shutil.copyfile(source,target)
            shutil.copytree(workspace,self.root,ignore=excluded,copy_function=copy,dirs_exist_ok=True)
        except (OSError,ValueError):self.close();raise

    def close(self):
        """Remove the copy after its model process has stopped."""
        self.temporary.cleanup()
