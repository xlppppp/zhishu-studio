"""Local expiring originals and ordered Word text/image handoff for requirements."""
import base64
import hashlib
import json
from pathlib import Path
import posixpath
import shutil
import time
import uuid
import zipfile
import io
from xml.etree import ElementTree as ET

from requirements_import import extract_requirements,DocumentTree,WORD

TTL_SECONDS=24*60*60
MAX_CACHE_BYTES=512*1024*1024
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def safe_file(directory,name):
    """Resolve a managed attachment leaf, rejecting symlinked parents and names."""
    if not isinstance(name,str) or Path(name).name!=name or name in ('.','..') or '\\' in name:raise ValueError('附件文件名无效')
    if directory.is_symlink() or directory.parent.is_symlink():raise ValueError('附件目录不能是符号链接')
    path=directory/name
    if path.is_symlink() or not path.is_file():raise ValueError('附件文件缺失或不能读取，请重新上传')
    return path


def word_assets(raw):
    """Read embedded image relationships without following external resources.

    Output preserves paragraph order and inline image markers, not page layout.
    Unsupported objects remain in the original and receive explicit warnings.
    """
    assets={};warnings=[];lines=[];known={}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        root=ET.fromstring(archive.read('word/document.xml'),parser=ET.XMLParser(target=DocumentTree()))
        relations={}
        if 'word/_rels/document.xml.rels' in archive.namelist():
            info=archive.getinfo('word/_rels/document.xml.rels')
            if info.file_size>1024*1024:raise ValueError('Word 图片关系文件过大，请精简后上传')
            relroot=ET.fromstring(archive.read(info),parser=ET.XMLParser(target=DocumentTree()))
            for item in relroot:
                identifier=item.get('Id')
                if identifier in relations:raise ValueError('Word 图片关系 ID 重复')
                relations[identifier]=item.attrib
        for number,paragraph in enumerate(root.iter('{'+WORD+'}p'),1):
            pieces=[]
            for node in paragraph.iter():
                local=node.tag.rsplit('}',1)[-1]
                if node.tag=='{'+WORD+'}t':pieces.append(node.text or '')
                elif node.tag=='{'+WORD+'}tab':pieces.append('\t')
                elif node.tag in ('{'+WORD+'}br','{'+WORD+'}cr'):pieces.append('\n')
                if local in ('chart','relIds','OLEObject'):
                    warnings.append(f'段落 {number} 包含图表、SmartArt 或嵌入对象；原文件保留，需另附截图供识图。')
                if local not in ('blip','imagedata'):continue
                identifier=node.get('{'+REL+'}embed') or node.get('{'+REL+'}id') or node.get('{'+REL+'}link')
                relation=relations.get(identifier)
                if not relation or relation.get('TargetMode')=='External':
                    warnings.append(f'段落 {number} 的图片关系缺失或为外部链接，未下载；请另附截图。');pieces.append('[图片未能读取]');continue
                target=relation.get('Target','')
                member=posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('word',target))
                if not member.startswith('word/media/') or member not in archive.namelist():
                    warnings.append(f'段落 {number} 的图片路径无法读取，请另附截图。');pieces.append('[图片未能读取]');continue
                if member not in known:
                    if len(known)>=80:raise ValueError('Word 图片超过 80 张，请拆分文档后上传')
                    info=archive.getinfo(member)
                    if info.file_size>30*1024*1024:raise ValueError('Word 单张图片超过 30 MB，请压缩后上传')
                    content=archive.read(info)
                    kind='png' if content.startswith(b'\x89PNG\r\n\x1a\n') else 'jpeg' if content.startswith(b'\xff\xd8\xff') else 'webp' if content.startswith(b'RIFF') and content[8:12]==b'WEBP' else 'unsupported'
                    index=len(known)+1;filename=f'image-{index}.'+(kind if kind!='unsupported' else 'bin')
                    record={'file':filename,'number':index,'paragraph':number,'supported':kind!='unsupported','source':member}
                    known[member]=record;assets[filename]=content
                    if not record['supported']:warnings.append(f'图片 {index}（段落 {number}）格式不支持直接识图，原件保留；请补充 PNG/JPEG/WebP 截图。')
                record=known[member];pieces.append(f"\n[图片 {record['number']}：{record['file']}，位于段落 {number}]\n")
            value=''.join(pieces).strip()
            if value:lines.append(f'【段落 {number}】\n'+value)
    return '\n\n'.join(lines),list(known.values()),assets,list(dict.fromkeys(warnings))


class DocumentCache:
    """Own a single-user, 24-hour on-disk staging area and project copies."""
    def __init__(self,root):
        self.root=Path(root)/'requirement-uploads'
        if self.root.is_symlink():raise ValueError('附件缓存目录不能是符号链接')
        self.root.mkdir(exist_ok=True,mode=0o700)

    def directory(self,identifier):
        if not isinstance(identifier,str) or len(identifier)!=32 or any(c not in '0123456789abcdef' for c in identifier):raise ValueError('附件标识无效')
        directory=self.root/identifier
        if directory.is_symlink():raise ValueError('附件缓存不能是符号链接')
        return directory

    def read(self,identifier):
        """Load a live staging record; expired references require re-upload."""
        directory=self.directory(identifier)
        try:record=json.loads(safe_file(directory,'manifest.json').read_text())
        except (OSError,ValueError) as error:raise ValueError('需求附件缓存不存在，请重新上传') from error
        if record.get('id')!=identifier or not isinstance(record.get('expiresAt'),(int,float)) or record['expiresAt']<=time.time():raise ValueError('需求附件缓存已过期，请重新上传')
        return record

    def remove(self,identifier):
        """Delete only the selected staging copy; project attachments are separate."""
        directory=self.directory(identifier)
        if directory.exists():shutil.rmtree(directory)

    def add(self,body):
        """Validate, stage originals and assets, and return lightweight metadata."""
        parsed=extract_requirements(body,allow_image_only=True)
        raw=base64.b64decode(body['data'],validate=True)
        name=parsed['name'];content=parsed['text'];images=[];assets={};warnings=[]
        if name.lower().endswith('.docx'):
            try:content,images,assets,warnings=word_assets(raw)
            except (zipfile.BadZipFile,ET.ParseError,KeyError,RuntimeError,NotImplementedError) as error:raise ValueError('Word 图片或关系数据损坏，请另存为 .docx 后重新上传') from error
            warnings.insert(0,'已保留原始 Word、正文与嵌入图片及段落位置；页眉页脚、批注和页面版式请以原件为准。')
        else:warnings=['已保留原文件及文字。Markdown 外链或本地路径图片不会自动下载，请另附参考截图。']
        if not content.strip() and not images:raise ValueError('文档没有可用文字或嵌入图片，请检查原件后重试')
        # Bound staged disk usage, expiring abandoned copies before admitting a new one.
        size=0
        for directory in self.root.iterdir():
            if not directory.is_dir() or directory.is_symlink():continue
            try:self.read(directory.name)
            except ValueError:self.remove(directory.name);continue
            size+=sum(path.stat().st_size for path in directory.iterdir() if path.is_file() and not path.is_symlink())
        needed=len(raw)+sum(map(len,assets.values()))+len(content.encode())
        if size+needed>MAX_CACHE_BYTES:raise ValueError('需求附件缓存空间已满，请移除不用的附件或稍后重试')
        identifier=uuid.uuid4().hex;directory=self.directory(identifier);directory.mkdir(mode=0o700)
        record={'id':identifier,'name':name,'size':len(raw),'expiresAt':time.time()+TTL_SECONDS,'file':'original'+Path(name).suffix.lower(),'textFile':'content.txt','images':images,'warnings':warnings}
        try:
            (directory/record['file']).write_bytes(raw);(directory/'content.txt').write_text(content)
            for filename,data in assets.items():(directory/filename).write_bytes(data)
            (directory/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
        except OSError:shutil.rmtree(directory);raise
        return {**record,'text':parsed['text'],'imageCount':len(images)}

    def attach(self,identifier,destination):
        """Copy a live upload into the project without consuming the cached original."""
        record=self.read(identifier);source=self.directory(identifier)
        destination.mkdir(parents=True,mode=0o700)
        for name in [record['file'],record['textFile'],*(image['file'] for image in record['images'])]:
            shutil.copyfile(safe_file(source,name),destination/name)
        (destination/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
        return record
