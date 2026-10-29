"""File parsing is bounded and never executes embedded document content."""
import base64
import io
import sys
from pathlib import Path
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from requirements_import import extract_requirements,MAX_FILE,MAX_DOCUMENT_XML


def request(name,raw):
    return {'name':name,'data':base64.b64encode(raw).decode()}


def word(xml):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:archive.writestr('word/document.xml',xml)
    return output.getvalue()


class ImportTests(unittest.TestCase):
    def test_markdown_and_supported_text_encodings_preserve_content(self):
        for name,raw in [('需求.md','# 需求\n- 客户管理'.encode()),('需求.markdown',b'\xef\xbb\xbf# Title'),('需求.txt','需求\r\n第二行'.encode('utf-16'))]:
            with self.subTest(name=name):
                result=extract_requirements(request(name,raw));self.assertTrue(result['text']);self.assertNotIn('\r',result['text']);self.assertEqual(result['name'],name)

    def test_word_paragraphs_table_text_and_line_breaks(self):
        xml=b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Requirements</w:t><w:br/><w:t>Next</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Customer</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'
        result=extract_requirements(request('需求.docx',word(xml)))
        self.assertEqual(result['text'],'Requirements\nNext\nCustomer');self.assertIn('图片',result['warning'])

    def test_invalid_and_unsupported_files_fail_without_fallback(self):
        for name,raw in [('a.doc',b'old binary'),('a.pdf',b'PDF'),('a.docx',b'not a zip'),('empty.txt',b''),('binary.txt',b'a\x00b'),('encoding.txt',b'\xff\xfa')]:
            with self.subTest(name=name),self.assertRaises(ValueError):extract_requirements(request(name,raw))

    def test_names_base64_and_size_are_validated(self):
        for body in [request('../a.md',b'a'),request('a\n.md',b'a'),{'name':'a.md','data':'!'},request('a.txt',b'a'*(MAX_FILE+1)),request('a.md',b'a'*30001)]:
            with self.subTest(name=body['name']),self.assertRaises(ValueError):extract_requirements(body)

    def test_xml_entities_are_rejected_in_utf8_and_utf16(self):
        for encoding in ('utf-8','utf-16'):
            xml=('<?xml version="1.0" encoding="'+encoding+'"?><!DOCTYPE a [<!ENTITY x "expanded">]><a>&x;</a>').encode(encoding)
            with self.subTest(encoding=encoding),self.assertRaisesRegex(ValueError,'DTD'):extract_requirements(request('unsafe.docx',word(xml)))

    def test_compressed_oversize_document_is_rejected_before_parsing(self):
        with self.assertRaisesRegex(ValueError,'过大'):extract_requirements(request('large.docx',word(b'a'*(MAX_DOCUMENT_XML+1))))

    def test_word_without_main_text_is_not_reported_as_imported(self):
        xml=b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p/></w:body></w:document>'
        with self.assertRaisesRegex(ValueError,'没有提取到文字'):extract_requirements(request('scan.docx',word(xml)))


class LargeImportTests(unittest.TestCase):
    def test_document_larger_than_old_limit_imports_only_text(self):
        xml=b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Large document requirements</w:t></w:r></w:p></w:body></w:document>'
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            archive.writestr('word/document.xml',xml)
            archive.writestr('word/media/image.bin',b'x'*(4*1024*1024))
        self.assertGreater(len(output.getvalue()),3*1024*1024)
        self.assertEqual(extract_requirements(request('large.docx',output.getvalue()))['text'],'Large document requirements')

    def test_exact_thirty_mb_is_accepted_before_text_length_validation(self):
        raw=b'Valid requirements'+b' '*(MAX_FILE-len(b'Valid requirements'))
        self.assertEqual(extract_requirements(request('boundary.txt',raw))['text'],'Valid requirements')
