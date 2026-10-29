"""Fresh builds retain a whole prior workspace and recover interrupted directory swaps."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_recovery import restart_workspace,recover_restart,workspace_status


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name);self.workspace=self.directory/'workspace';self.job='a'*32
        control=self.workspace/'.studio'/self.job;control.mkdir(parents=True)
        (control/'request.json').write_text('{}')
        (self.workspace/'preview.html').write_text('<h1>Existing UI</h1>')
        (self.workspace/'.env').write_text('SYNTHETIC_TEST_SETTING=1')

    def test_restart_keeps_full_backup_and_only_control_files_in_new_workspace(self):
        relative=restart_workspace(self.directory,self.job)
        backup=self.directory/relative
        self.assertEqual((backup/'preview.html').read_text(),'<h1>Existing UI</h1>')
        self.assertTrue((backup/'.env').is_file())
        self.assertFalse((self.workspace/'preview.html').exists())
        self.assertTrue((self.workspace/'.studio'/self.job/'request.json').is_file())
        self.assertFalse((self.directory/'.workspace-restart.json').exists())

    def test_failed_install_restores_original_workspace(self):
        original=os.rename
        def rename(source,target):
            if Path(source).name.startswith('.workspace-next-'):raise OSError('fixture disk failure')
            return original(source,target)
        with patch('workspace_recovery.os.rename',side_effect=rename),self.assertRaises(OSError):
            restart_workspace(self.directory,self.job)
        recover_restart(self.directory)
        self.assertTrue((self.workspace/'preview.html').is_file())

    def test_worker_recovery_restores_after_hard_stop_between_renames(self):
        backup=self.directory/'workspace-backups'/self.job;backup.parent.mkdir()
        (self.directory/'.workspace-restart.json').write_text(json.dumps({'jobId':self.job}))
        os.rename(self.workspace,backup)
        recover_restart(self.directory)
        self.assertTrue((self.workspace/'preview.html').is_file())

    def test_preview_requires_safe_file_but_not_completed_task(self):
        self.assertEqual(workspace_status(self.workspace),{'hasWorkspaceProgress':True,'previewAvailable':True})
        (self.workspace/'preview.html').unlink()
        (self.workspace/'preview.html').symlink_to(self.workspace/'.env')
        self.assertFalse(workspace_status(self.workspace)['previewAvailable'])

    def test_symlinked_backup_root_is_rejected_without_moving_source(self):
        (self.directory/'workspace-backups').symlink_to(self.directory,target_is_directory=True)
        with self.assertRaises(ValueError):restart_workspace(self.directory,self.job)
        self.assertTrue((self.workspace/'preview.html').is_file())
