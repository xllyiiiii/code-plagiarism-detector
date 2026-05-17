"""AST 解析引擎 —— 将源代码解析为标准化 AST，提取子树哈希和指纹。"""

import ast
import hashlib
import json
import re
from collections import deque


class ASTParser:
    """多语言 AST 解析器（初期支持 Python，后续扩展 tree-sitter）。"""

    SUPPORTED_LANGUAGES = {'python', 'java', 'c', 'cpp', 'javascript'}

    def __init__(self, language='python'):
        if language not in self.SUPPORTED_LANGUAGES:
            raise ValueError(f'不支持的语言: {language}')
        self.language = language

    def parse(self, source_code):
        """解析源代码，返回标准化 AST 字典。"""
        if self.language == 'python':
            return self._parse_python(source_code)
        else:
            # 非 Python 语言回退到 token 级分析
            return self._parse_generic(source_code)

    # ================================================================
    # Python AST
    # ================================================================

    def _parse_python(self, source_code):
        """使用内置 ast 模块解析 Python 代码。"""
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            raise ValueError(f'Python 语法错误: {e}')

        normalized_root = self._normalize_node(tree)
        subtree_hashes = self._collect_subtree_hashes(tree)
        fingerprint = self._make_fingerprint(subtree_hashes)

        return {
            'language': 'python',
            'fingerprint': fingerprint,
            'ast_root': normalized_root,
            'subtree_hashes': sorted(subtree_hashes),
            'node_count': normalized_root.get('node_count', 0),
        }

    def _normalize_node(self, node, depth=0):
        """
        递归标准化 AST 节点：
           - 去掉行号/列号
           - 标识符泛化为 ID_ 占位符
           - 字面量泛化
           - 保留结构信息
        """
        if node is None:
            return None

        node_type = type(node).__name__
        info = {'_type': node_type}

        # 统计节点数
        child_count = 0

        for field_name, field_value in ast.iter_fields(node):
            if field_name in ('lineno', 'col_offset', 'end_lineno', 'end_col_offset', 'ctx'):
                continue

            if isinstance(field_value, ast.AST):
                child_count += 1
                info[field_name] = self._normalize_node(field_value, depth + 1)
            elif isinstance(field_value, list):
                normalized_list = []
                for item in field_value:
                    if isinstance(item, ast.AST):
                        child_count += 1
                        normalized_list.append(self._normalize_node(item, depth + 1))
                    elif isinstance(item, str):
                        normalized_list.append('STR_')
                    elif isinstance(item, (int, float)):
                        normalized_list.append('NUM_')
                    else:
                        normalized_list.append(str(type(item).__name__))
                info[field_name] = normalized_list
            elif isinstance(field_value, str):
                # 泛化所有字符串（标识符名、字符串字面量）
                if field_name == 'name' or field_name == 'id':
                    info[field_name] = 'ID_'  # 变量名/函数名泛化
                elif field_name in ('arg', 'attr'):
                    info[field_name] = 'ID_'
                else:
                    info[field_name] = 'STR_'
            elif isinstance(field_value, (int, float)):
                info[field_name] = 'NUM_'
            elif field_value is not None:
                info[field_name] = str(type(field_value).__name__)

        info['node_count'] = 1 + child_count

        # 计算本节点的结构哈希
        info['_hash'] = self._hash_node(info)
        return info

    def _hash_node(self, node_info):
        """计算单个节点的结构哈希（用于子树同构检测）。"""
        raw = json.dumps(node_info, sort_keys=True, default=str)
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def _collect_subtree_hashes(self, tree):
        """收集 AST 中所有子树的哈希值集合。"""
        hashes = set()

        def walk(node):
            if isinstance(node, ast.AST):
                node_type = type(node).__name__
                # 为每种子树类型生成结构描述
                children_types = []
                for _, field_value in ast.iter_fields(node):
                    if isinstance(field_value, ast.AST):
                        children_types.append(type(field_value).__name__)
                    elif isinstance(field_value, list):
                        for item in field_value:
                            if isinstance(item, ast.AST):
                                children_types.append(type(item).__name__)

                desc = f"{node_type}({','.join(sorted(children_types))})"
                hashes.add(hashlib.md5(desc.encode()).hexdigest()[:12])
                for child in ast.iter_child_nodes(node):
                    walk(child)

        walk(tree)
        return hashes

    def _make_fingerprint(self, subtree_hashes):
        """生成 AST 整体指纹。"""
        combined = ''.join(sorted(subtree_hashes))
        return hashlib.sha256(combined.encode()).hexdigest()[:32]

    # ================================================================
    # Generic (token-based fallback for non-Python languages)
    # ================================================================

    def _parse_generic(self, source_code):
        """对非 Python 语言做 token 级分析。"""
        tokens = self._tokenize(source_code)
        ngrams = self._extract_ngrams(tokens, n=5)
        fingerprint = hashlib.sha256(' '.join(sorted(ngrams)).encode()).hexdigest()[:32]

        return {
            'language': self.language,
            'fingerprint': fingerprint,
            'ast_root': None,
            'subtree_hashes': sorted(ngrams),
            'node_count': len(tokens),
            'tokens': tokens,
        }

    def _tokenize(self, source_code):
        """简易词法分析：提取标识符和关键字序列。"""
        # 移除字符串和注释
        code = re.sub(r'#.*', '', source_code)
        code = re.sub(r'""".*?"""', '""', code, flags=re.DOTALL)
        code = re.sub(r"'''.*?'''", "''", code, flags=re.DOTALL)
        code = re.sub(r'"[^"]*"', '"str"', code)
        code = re.sub(r"'[^']*'", "'str'", code)

        tokens = []
        for token in re.findall(r'[A-Za-z_]\w*|\d+|[^\s\w]', code):
            if token.isdigit():
                tokens.append('NUM')
            elif re.match(r'^[A-Za-z_]\w*$', token):
                # 保留关键字，泛化标识符
                keywords = {
                    'if', 'else', 'for', 'while', 'do', 'return', 'class',
                    'def', 'int', 'float', 'double', 'char', 'void', 'public',
                    'private', 'protected', 'static', 'new', 'import', 'from',
                    'in', 'is', 'not', 'and', 'or', 'True', 'False', 'None',
                    'null', 'true', 'false', 'this', 'super', 'try', 'catch',
                    'throw', 'throws', 'finally', 'switch', 'case', 'break',
                    'continue', 'default', 'extends', 'implements', 'package',
                    'function', 'var', 'let', 'const', 'async', 'await',
                }
                tokens.append(token if token in keywords else 'ID')
            else:
                tokens.append(token)
        return tokens

    def _extract_ngrams(self, tokens, n=5):
        """提取 token n-gram 集合（用于结构级比较）。"""
        if len(tokens) < n:
            return [hashlib.md5(' '.join(tokens).encode()).hexdigest()[:12]]
        ngrams = set()
        for i in range(len(tokens) - n + 1):
            gram = ' '.join(tokens[i:i + n])
            ngrams.add(hashlib.md5(gram.encode()).hexdigest()[:12])
        return ngrams


def parse_submission(file_path, language):
    """
    解析提交的代码文件。

    Returns:
        dict: 包含 fingerprint, subtree_hashes, node_count 等字段
    """
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        source_code = f.read()

    parser = ASTParser(language)
    return parser.parse(source_code)


def extract_features(file_path, language):
    """
    解析并提取可用于相似度比对的特征向量。

    Returns:
        dict: 精简的特征数据，可直接存入 Submission.ast_data
    """
    result = parse_submission(file_path, language)
    return {
        'language': result['language'],
        'fingerprint': result['fingerprint'],
        'subtree_hashes': result['subtree_hashes'],
        'node_count': result['node_count'],
        'tokens': result.get('tokens', []),
    }
