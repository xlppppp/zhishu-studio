"""Retain generated source across explicit fresh builds and interrupted directory swaps."""
import json
import os
from pathlib import Path
import re
import shutil


def workspace_status(workspace):
    """Report existing source and safe static previews independently of task acceptance."""
    if workspace.is_symlink() or not workspace.is_dir():return {'hasWorkspaceProgress':False,'previewAvailable':False}
    ignored={'.studio','node_modules','.venv','venv','__pycache__','.git','.data'}
    progress=any(not path.is_symlink() and path.name not in ignored and not path.name.startswith('.env') for path in workspace.iterdir())
    preview=workspace/'preview.html'
    available=preview.is_file() and not preview.is_symlink() and preview.stat().st_size<=2*1024*1024
    return {'hasWorkspaceProgress':progress,'previewAvailable':available}


def recover_restart(directory):
    """Restore the retained workspace if a process stopped between directory renames."""
    marker=directory/'.workspace-restart.json'
    if not marker.exists():return
    if marker.is_symlink():raise ValueError('工作区恢复记录不能是符号链接')
    record=json.loads(marker.read_text())
    if not isinstance(record,dict) or set(record)!={'jobId'}:raise ValueError('工作区恢复记录无效')
    identifier=record['jobId']
    if not isinstance(identifier,str) or not re.fullmatch(r'[a-f0-9]{32}',identifier):raise ValueError('工作区恢复记录无效')
    workspace=directory/'workspace';backup=directory/'workspace-backups'/identifier
    if workspace.is_symlink() or backup.parent.is_symlink():raise ValueError('工作区和备份目录不能是符号链接')
    if not workspace.exists():
        if not backup.is_dir() or backup.is_symlink():raise ValueError('工作区备份缺失，请检查项目目录后恢复')
        os.rename(backup,workspace)
    marker.unlink()


def restart_workspace(directory,job_id):
    """Retain the entire prior workspace and install only the new task's control files.

    A journal lets the next Worker restore the old directory after a hard stop.
    Failure before model invocation leaves either the original or a full backup.
    """
    recover_restart(directory)
    workspace=directory/'workspace';backups=directory/'workspace-backups'
    if workspace.is_symlink() or backups.is_symlink():raise ValueError('工作区和备份目录不能是符号链接')
    backup=backups/job_id;staging=directory/('.workspace-next-'+job_id)
    if backup.exists() or staging.exists():raise ValueError('本次工作区备份已存在，请检查后重新提交')
    backups.mkdir(exist_ok=True)
    staging.mkdir()
    try:
        shutil.copytree(workspace/'.studio'/job_id,staging/'.studio'/job_id,symlinks=True)
        marker=directory/'.workspace-restart.json'
        marker.write_text(json.dumps({'jobId':job_id})+'\n')
        os.rename(workspace,backup)
        try:os.rename(staging,workspace)
        except OSError:
            os.rename(backup,workspace)
            raise
        marker.unlink()
    finally:
        if staging.exists():shutil.rmtree(staging)
    return backup.relative_to(directory).as_posix()
