"""Bounded upload decoding and text extraction; callers own attachment storage."""

import base64
import binascii
import io
from pathlib import PurePath
import zipfile
from xml.etree import ElementTree as ET

MAX_FILE=30*1024*1024
MAX_IMPORT_BODY=4*((MAX_FILE+2)//3)+4096
MAX_WORD_EXPANDED=120*1024*1024
MAX_DOCUMENT_XML=30*1024*1024
MAX_TEXT=30000
WORD='http://schemas.openxmlformats.org/wordprocessingml/2006/main'


class DocumentTree(ET.TreeBuilder):
    """Reject document type declarations, including non-UTF-8 XML encodings."""

    def doctype(self,name,pubid,system):
        raise ValueError('Word 文档不能包含 DTD 或外部实体')


def extract_requirements(body,allow_image_only=False):
    """Return reviewed-input text from one base64 file, or reject without storing it.

    Accept .docx main-document text and UTF-8/UTF-16 Markdown/plain text. Limit
    compressed and expanded ZIP data before parsing; never resolve relationships.
    """
    name=body.get('name');encoded=body.get('data')
    if not isinstance(name,str) or not name.strip() or len(name)>160 or any(c in name for c in '/\\\r\n\x00'):
        raise ValueError('文件名无效，请使用不含路径的文件名，最多 160 字符')
    suffix=PurePath(name).suffix.lower()
    if suffix not in ('.docx','.md','.markdown','.txt'):
        raise ValueError('支持 .docx、.md、.markdown、.txt；旧版 .doc 请先另存为 .docx')
    if not isinstance(encoded,str) or len(encoded)>4*((MAX_FILE+2)//3):raise ValueError('单个需求文件不能超过 30 MB')
    try:raw=base64.b64decode(encoded,validate=True)
    except (binascii.Error,ValueError) as error:raise ValueError('文件数据无效，请重新选择文件') from error
    if not raw or len(raw)>MAX_FILE:raise ValueError('需求文件为空或超过 30 MB')
    if suffix=='.docx':
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries=archive.infolist()
                if len(entries)>2000 or sum(item.file_size for item in entries)>MAX_WORD_EXPANDED:raise ValueError('Word 文档解压内容过大，请精简后上传')
                matches=[item for item in entries if item.filename=='word/document.xml']
                if len(matches)!=1:raise ValueError('不是有效的 Word .docx 文档')
                document=matches[0]
                if document.flag_bits & 1:raise ValueError('不支持加密 Word 文档，请先解除密码')
                if document.file_size>MAX_DOCUMENT_XML:raise ValueError('Word 正文过大，请精简后上传')
                xml=archive.read(document)
            root=ET.fromstring(xml,parser=ET.XMLParser(target=DocumentTree()))
            body_element=root.find('{'+WORD+'}body')
            if root.tag!='{'+WORD+'}document' or body_element is None:raise ValueError('Word 文档正文结构无效')
            lines=[]
            for paragraph in body_element.iter('{'+WORD+'}p'):
                pieces=[]
                for node in paragraph.iter():
                    if node.tag=='{'+WORD+'}t':pieces.append(node.text or '')
                    elif node.tag=='{'+WORD+'}tab':pieces.append('\t')
                    elif node.tag in ('{'+WORD+'}br','{'+WORD+'}cr'):pieces.append('\n')
                lines.append(''.join(pieces))
            content='\n'.join(lines)
        except (zipfile.BadZipFile,KeyError,ET.ParseError,RuntimeError,NotImplementedError) as error:
            raise ValueError('无法读取 Word 文档，请确认未损坏、未加密，并另存为 .docx 后重试') from error
        warning='仅提取 Word 正文段落和表格文字；图片、页眉页脚、批注和版式不导入，请检查提取结果。'
    else:
        try:content=raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
        except UnicodeError as error:raise ValueError('文本编码不支持，请另存为 UTF-8 或带 BOM 的 UTF-16 后上传') from error
        warning='已按原文导入，请检查内容后创建项目。'
    content=content.replace('\r\n','\n').replace('\r','\n').strip()
    if '\x00' in content:raise ValueError('文件包含二进制内容，不能作为文字需求导入')
    if not content and not (allow_image_only and suffix=='.docx'):raise ValueError('没有提取到文字；扫描件或图片请使用参考截图上传')
    if len(content)>MAX_TEXT:raise ValueError('提取的需求超过 30000 字符，请拆分或精简后上传')
    return {'name':name,'text':content,'warning':warning}
