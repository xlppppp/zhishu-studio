"""Bounded source inspection and local syntax evidence for staged reviews."""
import ast
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess

EXCLUDED={'node_modules','.git','.venv','venv','__pycache__','.studio','.data','dist','build','.ssh','.aws','.browsers','.local-browsers','.npm-cache','.cache','.pytest_cache','playwright-report','test-results','coverage'}


def excluded_review_path(path):
    """Skip tool installations, generated output, symlinks, credentials, and private databases."""
    return path.name in EXCLUDED or path.is_symlink() or path.name.startswith('.env') and path.name!='.env.example' or path.suffix.lower() in ('.pem','.key','.db','.sqlite','.sqlite3') or bool(re.search(r'\.(?:db|sqlite|sqlite3)-(?:wal|shm|journal)$',path.name))


def source_files(workspace):
    """Enumerate non-secret source files within the review copy's size limits."""
    import os
    files={};total=0
    for base,directories,names in os.walk(workspace,followlinks=False):
        directories[:]=sorted(name for name in directories if not excluded_review_path(Path(base)/name))
        for name in sorted(names):
            path=Path(base)/name
            if excluded_review_path(path):continue
            size=path.stat().st_size;total+=size
            if total>50*1024*1024 or len(files)>=5000:raise ValueError('审查源码超过 50 MB 或 5000 文件，请先清理构建产物')
            files[path.relative_to(workspace).as_posix()]=path
    return files


def source_hashes(workspace):
    """Fingerprint eligible source to derive added, modified, and removed files."""
    return {name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in source_files(workspace).items()}


def review_scope(workspace,before,kind,feedback):
    """Use full review for initial/risk-sensitive work and changed files otherwise."""
    import re
    after=source_hashes(workspace)
    changed=sorted(name for name in before.keys()|after.keys() if before.get(name)!=after.get(name))
    sensitive=re.compile(r'auth|permission|security|migrat|database|schema|(^|/)(db|models)(/|\.)|权限|鉴权|数据库',re.I)
    full=kind=='build' or any(sensitive.search(name) for name in changed) or bool(sensitive.search(feedback))
    return {'mode':'full' if full else 'changes','changedFiles':changed}


def basic_checks(workspace,check_stop):
    """Parse Python/JSON and bounded JavaScript files without running application code.

    These checks establish syntax evidence only, not functional or deployment readiness.
    """
    checks=[];node=shutil.which('node');javascript=0
    for name,path in source_files(workspace).items():
        check_stop()
        if path.suffix not in ('.py','.js','.mjs','.cjs') and path.name!='package.json':continue
        if len(checks)>=50:
            checks.append({'command':'remaining syntax checks','status':'not_run','result':'超过 50 项基础检查上限，需补充验证'});break
        if path.stat().st_size>1024*1024:continue
        status='passed';result='语法解析通过'
        try:
            if path.suffix=='.py':ast.parse(path.read_bytes(),filename=name)
            elif path.name=='package.json':json.loads(path.read_text())
            elif javascript<20 and node:
                javascript+=1
                run=subprocess.run([node,'--check',str(path.resolve())],capture_output=True,text=True,timeout=10,env={'PATH':str(Path(node).parent)})
                if run.returncode:status='failed';result=run.stderr[-2000:]
            else:continue
        except (SyntaxError,ValueError,UnicodeError) as error:status='failed';result=str(error)[:2000]
        except (OSError,subprocess.TimeoutExpired) as error:status='not_run';result=str(error)[:2000]
        checks.append({'command':'syntax: '+name,'status':status,'result':result})
    return checks


def review_disposition(report,checks):
    """Keep incomplete evidence and high-risk findings out of delivery acceptance."""
    if any(check['status']=='failed' for check in [*checks,*report['checks']]) or any(item['severity'] in ('critical','high','medium') for item in report['findings']):return 'blocked'
    if report['verdict']=='inconclusive' or not report['checks'] or any(check['status']=='not_run' for check in [*checks,*report['checks']]):return 'pending'
    if report['verdict']=='changes_requested' and not report['findings']:return 'pending'
    return 'advisories' if report['findings'] else 'passed'
