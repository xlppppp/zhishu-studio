"""Preserve original documents, inline image context, and idempotent AI handoff."""
import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from document_cache import DocumentCache
from server import Store,Problem

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX2cAAAAASUVORK5CYII=')


def docx(picture=PNG,external=False,image_only=False):
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml',f'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body><w:p><w:r><w:t>{'' if image_only else '图片前的业务说明'}</w:t><w:drawing><a:blip r:embed="rId1"/></w:drawing><w:t>{'' if image_only else '图片后的说明'}</w:t></w:r></w:p></w:body></w:document>''')
        target='https://example.invalid/private.png' if external else 'media/image1.png'
        mode=' TargetMode="External"' if external else ''
        archive.writestr('word/_rels/document.xml.rels',f'<Relationships><Relationship Id="rId1" Target="{target}"{mode}/></Relationships>')
        if not external:archive.writestr('word/media/image1.png',picture)
    return data.getvalue()


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name,[sys.executable,str(Path(__file__).with_name('fake_harness.py'))]);self.addCleanup(self.store.close)
        self.cache=DocumentCache(Path(self.temp.name))

    def upload(self,raw=None,name='需求.docx'):
        return self.cache.add({'name':name,'data':base64.b64encode(raw if raw is not None else docx()).decode()})

    def test_staging_preserves_original_and_image_order_without_calling_ai(self):
        raw=docx();record=self.upload(raw);root=self.cache.directory(record['id'])
        self.assertEqual((root/record['file']).read_bytes(),raw);self.assertEqual((root/'image-1.png').read_bytes(),PNG)
        content=(root/'content.txt').read_text()
        self.assertLess(content.index('图片前'),content.index('[图片 1'));self.assertLess(content.index('[图片 1'),content.index('图片后的'))
        self.assertEqual(record['imageCount'],1);self.assertEqual(self.store.listing(),[])

    def test_images_only_and_unsupported_formats_are_not_silently_discarded(self):
        self.assertEqual(self.upload(docx(image_only=True))['imageCount'],1)
        record=self.upload(docx(picture=b'wmf format'))
        self.assertFalse(record['images'][0]['supported']);self.assertTrue(any('格式不支持' in text for text in record['warnings']))
        self.assertEqual((self.cache.directory(record['id'])/'image-1.bin').read_bytes(),b'wmf format')

    def test_external_images_are_reported_without_fetching(self):
        record=self.upload(docx(external=True));self.assertEqual(record['images'],[]);self.assertTrue(any('外部链接' in text for text in record['warnings']))

    def test_creation_combines_supplement_and_ordered_assets_and_enqueues_once(self):
        raw=docx();upload=self.upload(raw);request={'name':'图文项目','requirements':'补充：蓝色主题','documents':[upload['id']],'analyze':True,'requestId':uuid.uuid4().hex}
        project=self.store.create_and_analyze(request);duplicate=self.store.create_and_analyze(request)
        self.assertEqual(project['id'],duplicate['id']);self.assertEqual(len(self.store.pending(project['id'])),1)
        row=self.store.db.execute('SELECT spec FROM jobs WHERE project_id=?',(project['id'],)).fetchone();spec=json.loads(row[0]);inputs=json.loads(Path(spec['request']).read_text())
        self.assertEqual(inputs['requirements'],'补充：蓝色主题');document=inputs['documents'][0]
        self.assertEqual(Path(document['originalFile']).read_bytes(),raw)
        self.assertIn('段落 1',Path(document['textFile']).read_text());self.assertIn(document['images'][0]['path'],inputs['references']);self.assertIn('image',spec['snapshot']['modelPolicy']['input'])
        self.cache.remove(upload['id'])
        self.assertTrue((self.store.directory(project['id'])/'documents'/upload['id']/upload['file']).is_file())
        self.assertEqual(self.store.create_and_analyze(request)['id'],project['id'])
        self.store.work_once();self.assertEqual(self.store.load(project['id'])['job']['status'],'completed')

    def test_document_only_project_and_failed_analysis_preserve_uploads(self):
        upload=self.upload();self.store.command=[]
        project=self.store.create_and_analyze({'name':'仅文档','requirements':'','documents':[upload['id']],'analyze':True})
        self.assertEqual(project['requirements'],'');self.assertIn('analysisError',project);self.assertEqual(len(project['documents']),1)
        self.assertEqual(project['job']['status'],'idle');self.assertIn('未启动',project['job']['message'])

    def test_expired_and_invalid_cache_ids_reject_before_analysis(self):
        upload=self.upload()
        with patch('document_cache.time.time',return_value=upload['expiresAt']+1):
            with self.assertRaisesRegex(ValueError,'过期'):self.cache.read(upload['id'])
        with self.assertRaises(ValueError):self.cache.directory('../escape')
        with self.assertRaises(ValueError):self.store.create_and_analyze({'name':'过期','documents':['f'*32],'analyze':True})
        self.assertEqual(self.store.listing(),[])

    def test_duplicate_creation_id_cannot_replace_a_saved_requirement(self):
        upload=self.upload();body={'name':'项目','documents':[upload['id']],'requirements':'说明','requestId':uuid.uuid4().hex,'analyze':True}
        self.store.create_and_analyze(body)
        with self.assertRaisesRegex(Problem,'另一份需求'):self.store.create_and_analyze({**body,'requirements':'另一份说明'})

    def test_chat_with_imported_document_retains_selection_and_completes(self):
        uploaded=self.upload()
        project=self.store.create_and_analyze({'name':'附件问答','requirements':'检查导入错误','documents':[uploaded['id']],'analyze':False})
        identifier=project['id'];selection='div#form-error accessor.count 超限'
        self.store.start(identifier,{'kind':'chat','note':'为什么校验失败','target':selection,'autoScope':'code'})
        spec=json.loads(self.store.db.execute('SELECT spec FROM jobs WHERE project_id=?',(identifier,)).fetchone()[0])
        inputs=json.loads(Path(spec['request']).read_text())
        self.assertEqual(inputs['target'],selection)
        self.store.work_once()
        data=self.store.load(identifier)
        self.assertEqual(data['job']['status'],'completed',data['job']['message'])
        self.assertEqual(data['chatHistory'][0]['target'],selection)
