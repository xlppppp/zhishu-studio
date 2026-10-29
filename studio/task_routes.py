"""Task-specific guidance and guarded transfer of appearance-only edits.

Style work runs on copies. Only validated existing styles return to the project;
backend files, secrets, dependencies and application logic are not copied in.
The Harness remains responsible for process confinement, not this file filter.
"""

import json
import os
import shutil
from pathlib import Path
from html.parser import HTMLParser
import tempfile

SKILLS=Path(__file__).parent/'skills'
class StyleMarkup(HTMLParser):
    """Locate real style contents, excluding script strings and tag attributes."""
    def __init__(self,content):
        super().__init__(convert_charrefs=False)
        self.offsets=[0]+[index+1 for index,char in enumerate(content) if char=='\n']
        self.ranges=[];self.start=None
        self.feed(content);self.close()

    def absolute_position(self):
        row,column=self.getpos();return self.offsets[row-1]+column

    def handle_starttag(self,tag,attrs):
        if tag=='style':self.start=self.absolute_position()+len(self.get_starttag_text())

    def handle_startendtag(self,tag,attrs):
        pass  # A self-closing element has no editable CSS content.

    def handle_endtag(self,tag):
        if tag=='style' and self.start is not None:
            self.ranges.append((self.start,self.absolute_position()));self.start=None


def style_skeleton(content):
    """Mask only CSS text; every tag, attribute, and script remains comparable."""
    markup=StyleMarkup(content);parts=[];cursor=0
    for start,end in markup.ranges:
        parts.extend([content[cursor:start],'__STUDIO_CSS__']);cursor=end
    return ''.join(parts)+content[cursor:]


def style_files(workspace):
    """Select bounded existing CSS and HTML under known frontend directories."""
    files={};total=0
    roots={'frontend','client','web','src','public','assets'}
    for base,directories,names in os.walk(workspace,followlinks=False):
        parent=Path(base)
        directories[:]=[name for name in directories if not name.startswith('.') and name not in ('node_modules','__pycache__') and not (parent==workspace and name not in roots) and not (parent/name).is_symlink()]
        for name in names:
            path=parent/name;relative=path.relative_to(workspace)
            if name.startswith('.') or path.suffix.lower() not in ('.css','.html'):continue
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(workspace.resolve()):continue
            if path.stat().st_size>2*1024*1024:raise ValueError('单个样式文件超过 2 MB，请使用业务开发路径')
            content=path.read_bytes();total+=len(content)
            if total>10*1024*1024:raise ValueError('样式文件总量超过 10 MB，请缩小前端目录')
            files[relative.as_posix()]=content
    if not any(name.lower().endswith('.css') or StyleMarkup(content.decode('utf-8')).ranges for name,content in files.items()):
        raise ValueError('没有独立 CSS 或 HTML style 块可供快改；组件内样式请使用业务开发路径')
    return files


def task_skill(exchange, route):
    """Copy stage-specific skills and their references into one discovery root."""
    groups={'chat':['project-chat'],'review':['code-review'],'style':['frontend-style'],'business':['business-development','frontend-design'],
            'analysis':['studio-analysis','create-prd','api-design-principles','mermaid-diagrams','frontend-design']}
    names=groups[route];root=exchange/'skills'
    for name in names:
        shutil.copytree(SKILLS/name,root/name,dirs_exist_ok=True)
    patch=exchange/'skills.patch.yml'
    patch.write_text(json.dumps([{'id':'skill-filesystem','config':{'includeDefaultRoots':False,'customSkillDirs':[str(root.resolve())],'watch':False}}]))
    return root/names[0]/'SKILL.md',patch


class StyleRun:
    """Own one disposable source copy and validate all changes before transfer."""

    def __init__(self, workspace, request_file, result_file):
        self.workspace=workspace
        self.original=style_files(workspace)
        self.temporary=tempfile.TemporaryDirectory(prefix='studio-style-')
        self.root=Path(self.temporary.name).resolve()
        try:self.prepare(request_file,result_file)
        except (OSError,ValueError):
            self.close()
            raise

    def prepare(self,request_file,result_file):
        """Copy style sources and validate the persisted input before invocation."""
        if request_file.stat().st_size>64000:raise ValueError('样式任务输入文件过大')
        for name,content in self.original.items():
            target=self.root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
        control=self.root/'.studio';control.mkdir()
        self.request=control/request_file.name;self.result=control/result_file.name
        original=json.loads(request_file.read_text())
        if not isinstance(original,dict) or not isinstance(original.get('feedback'),str):raise ValueError('样式任务输入必须包含文字修改意见')
        self.request.write_text(json.dumps({'feedback':original['feedback'],'route':'style','allowedFiles':list(self.original)},ensure_ascii=False,indent=2))
        self.skill,self.patch=task_skill(control,'style')
        self.controls={p.relative_to(self.root).as_posix():p.read_bytes() for p in control.rglob('*') if p.is_file()}

    def close(self):
        """Remove the disposable copy after its process and validation have ended."""
        self.temporary.cleanup()

    def changes(self):
        """Reject additions, deletion, symlinks, and non-style HTML changes."""
        for path in self.root.rglob('*'):
            if path.is_symlink():raise ValueError('样式任务产生符号链接，未接收改动')
            if not path.is_file():continue
            name=path.relative_to(self.root).as_posix()
            if name.startswith('.studio/'):
                if name in self.controls and path.read_bytes()!=self.controls[name]:raise ValueError('样式任务修改了执行配置，未接收改动')
                continue
            if name not in self.original:raise ValueError('样式任务越界新增文件，未接收改动：'+name)
        changed={}
        for name,before in self.original.items():
            path=self.root/name
            if not path.is_file():raise ValueError('样式任务删除文件，未接收改动：'+name)
            if path.stat().st_size>2*1024*1024:raise ValueError('样式结果文件过大，未接收改动')
            after=path.read_bytes()
            if after==before:continue
            if name.lower().endswith('.html') and style_skeleton(before.decode('utf-8'))!=style_skeleton(after.decode('utf-8')):
                raise ValueError('样式任务修改了 HTML 结构或脚本，请改走业务开发：'+name)
            changed[name]=after
        return changed

    @staticmethod
    def replace(path, content):
        """Replace one existing file without leaving a partial write."""
        descriptor,name=tempfile.mkstemp(prefix='.studio-style-',dir=path.parent)
        try:
            with os.fdopen(descriptor,'wb') as stream:stream.write(content)
            os.chmod(name,path.stat().st_mode & 0o777)
            os.replace(name,path)
        finally:
            if os.path.exists(name):os.unlink(name)

    def apply(self):
        """Transfer only validated styles; restore earlier writes if transfer fails."""
        changed=self.changes()
        for name,content in self.original.items():
            path=self.workspace/name
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(self.workspace.resolve()) or path.read_bytes()!=content:
                raise ValueError('原前端文件已变化，未接收样式结果，请重新提交')
        written=[]
        try:
            for name,content in changed.items():
                self.replace(self.workspace/name,content);written.append(name)
        except OSError:
            for name in written:self.replace(self.workspace/name,self.original[name])
            raise
        return list(changed)
