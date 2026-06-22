"""文本解析引擎 —— 从 .txt/.md/.docx/.pdf 中提取文字并生成特征向量。"""

import hashlib
import re
import unicodedata


def _is_chinese(c):
    """判断单个字符是否为 CJK 统一表意文字。"""
    cp = ord(c)
    return (0x4E00 <= cp <= 0x9FFF or
            0x3400 <= cp <= 0x4DBF or
            0xF900 <= cp <= 0xFAFF)


def _read_plain_text(file_path):
    """读取纯文本文件，自动检测编码。"""
    for encoding in ('utf-8', 'gbk', 'latin-1'):
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()


def _read_docx(file_path):
    """从 .docx 文件中提取所有段落文字。"""
    from docx import Document
    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return '\n'.join(paragraphs)


def _read_pdf(file_path):
    """从 .pdf 文件中提取所有页面文字。"""
    from PyPDF2 import PdfReader
    reader = PdfReader(file_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return '\n'.join(pages)


def _normalize_text(raw_text):
    """分词：中文字符级 + 英文单词级混合。返回 token 列表。"""
    text = raw_text.lower()
    # 全角标点转半角
    text = unicodedata.normalize('NFKC', text)
    # 中文标点替换为空格
    text = re.sub(r'[，。！？、；：""''「」『』【】（）《》…—　]', ' ', text)
    # 英文标点替换为空格
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    tokens = []
    for chunk in text.split():
        # 判断是否以中文为主
        chinese_chars = [c for c in chunk if _is_chinese(c)]
        if len(chinese_chars) > len(chunk) * 0.3:
            # 中文字符级 token（保留连续中文作为超词 + 单字）
            for c in chunk:
                if _is_chinese(c) or c.isalnum():
                    tokens.append(c)
            # 额外添加中文字符 bigram 提升结构敏感度
            ch_only = [c for c in chunk if _is_chinese(c)]
            for i in range(len(ch_only) - 1):
                tokens.append(ch_only[i] + ch_only[i + 1])
        else:
            tokens.append(chunk)

    return tokens


def _split_sentences(text):
    """按句末标点分句，支持中英文。"""
    text = unicodedata.normalize('NFKC', text)
    text = text.replace('。', '.').replace('！', '!').replace('？', '?')
    raw_sentences = re.split(r'[.!?\n]+', text)
    return [s.strip() for s in raw_sentences if len(s.strip()) > 3]


def _compute_shingle_hashes(tokens, k=3):
    """计算 k-词滑动窗口的 MD5 哈希集。"""
    if len(tokens) < k:
        return [hashlib.md5(' '.join(tokens).encode()).hexdigest()[:12]]
    hashes = set()
    for i in range(len(tokens) - k + 1):
        shingle = ' '.join(tokens[i:i + k])
        hashes.add(hashlib.md5(shingle.encode()).hexdigest()[:12])
    return sorted(hashes)


def extract_text(file_path, language):
    """提取文本内容。根据文件类型分发到对应读取器。"""
    if language in ('txt', 'md'):
        raw_text = _read_plain_text(file_path)
    elif language == 'docx':
        raw_text = _read_docx(file_path)
    elif language == 'pdf':
        raw_text = _read_pdf(file_path)
    else:
        raise ValueError(f'不支持的文本格式: {language}')

    return raw_text


def extract_text_features(file_path, language):
    """提取文本特征向量，返回与 extract_features() 相同结构。"""
    raw_text = extract_text(file_path, language)
    tokens = _normalize_text(raw_text)
    sentences = _split_sentences(raw_text)
    shingle_hashes = _compute_shingle_hashes(tokens, k=3)
    fingerprint = hashlib.sha256(''.join(sorted(shingle_hashes)).encode()).hexdigest()[:32]

    return {
        'content_type': 'text',
        'language': language,
        'fingerprint': fingerprint,
        'subtree_hashes': shingle_hashes,
        'node_count': len(tokens),
        'tokens': tokens,
        'sentences': sentences,
    }
