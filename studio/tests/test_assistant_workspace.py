"""Assistant edits remain private until completion; concurrent changes are retained."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from assistant_workspace import AssistantWorkspace


class AssistantWorkspaceTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.directory=Path(temporary.name);self.workspace=self.directory/'workspace';self.workspace.mkdir()
        (self.workspace/'app.py').write_text('old')
        exchange=self.workspace/'.studio'/'job';exchange.mkdir(parents=True)
        request=exchange/'request.json';request.write_text(json.dumps({'feedback':'修复'}))
        self.draft=AssistantWorkspace(self.workspace,self.directory,'job',request,exchange/'result.json')

    def test_edit_add_and_remove_are_published_only_on_completion(self):
        (self.draft.root/'app.py').write_text('new');(self.draft.root/'new.py').write_text('added')
        self.assertEqual((self.workspace/'app.py').read_text(),'old');self.assertFalse((self.workspace/'new.py').exists())
        self.draft.publish()
        self.assertEqual((self.workspace/'app.py').read_text(),'new');self.assertEqual((self.workspace/'new.py').read_text(),'added')

    def test_concurrent_external_edit_is_not_overwritten(self):
        (self.draft.root/'app.py').write_text('assistant');(self.workspace/'app.py').write_text('external')
        with self.assertRaisesRegex(ValueError,'发生变化'):self.draft.publish()
        self.assertEqual((self.workspace/'app.py').read_text(),'external')
        self.assertEqual((self.draft.root/'app.py').read_text(),'assistant')

    def test_failed_publication_restores_previously_changed_files(self):
        (self.draft.root/'app.py').write_text('new');(self.draft.root/'z.py').write_text('added')
        original=Path.replace
        def replace(path,target):
            if path.name=='z.py.studio-publish':raise OSError('disk fixture')
            return original(path,target)
        with patch.object(Path,'replace',replace),self.assertRaises(OSError):self.draft.publish()
        self.assertEqual((self.workspace/'app.py').read_text(),'old');self.assertFalse((self.workspace/'z.py').exists())
