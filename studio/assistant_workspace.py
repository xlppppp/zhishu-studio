"""Keep assistant edits separate from published source until a successful task."""
from pathlib import Path
import shutil

from model_workflow import ReviewCopy
from review_workflow import source_files, source_hashes


class AssistantWorkspace:
    """Retain a private draft and roll back failed file publication before reporting it."""

    def __init__(self, workspace, directory, job_id, request, result):
        self.workspace=workspace
        self.before=source_hashes(workspace)
        self.root=directory/'assistant-drafts'/job_id
        with_copy=ReviewCopy(workspace)
        try:shutil.copytree(with_copy.root,self.root)
        finally:with_copy.close()
        exchange=self.root/'.studio'/job_id
        shutil.copytree(request.parent,exchange)
        self.request=exchange/request.name
        self.result=exchange/result.name
        # Attachment paths are owned by this task's exchange directory.
        self.request.write_text(self.request.read_text().replace(str(request.parent),str(exchange)))

    def publish(self):
        """Reject concurrent source edits; restore touched files if publication fails."""
        if source_hashes(self.workspace)!=self.before:
            raise ValueError('原工作区在修改期间发生变化；本轮代码保留在助手草稿中，未覆盖现有版本')
        after=source_hashes(self.root)
        changed=sorted(name for name in self.before.keys()|after.keys() if self.before.get(name)!=after.get(name))
        files=source_files(self.root)
        backup=self.root.parent/(self.root.name+'-previous')
        backup.mkdir()
        for name in changed:
            original=self.workspace/name
            if original.is_symlink() or any((self.workspace/parent).is_symlink() for parent in Path(name).parents):
                raise ValueError('工作区路径发生变化，未发布助手修改')
            if original.is_file():
                target=backup/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,target)
        touched=[]
        try:
            for name in changed:
                target=self.workspace/name
                target.parent.mkdir(parents=True,exist_ok=True)
                touched.append(name)
                if name in files:
                    temporary=target.with_name(target.name+'.studio-publish')
                    shutil.copyfile(files[name],temporary);temporary.replace(target)
                else:target.unlink()
        except OSError:
            for name in reversed(touched):
                target=self.workspace/name;old=backup/name
                temporary=target.with_name(target.name+'.studio-publish')
                if temporary.is_file():temporary.unlink()
                if old.is_file():shutil.copyfile(old,target)
                elif target.exists():target.unlink()
            raise
