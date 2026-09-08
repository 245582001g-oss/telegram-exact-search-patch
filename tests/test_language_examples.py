"""Read existing compiled payload and test language examples with synthetic objects."""
from pathlib import Path
import hashlib
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build-dir', type=Path, default=Path(__file__).resolve().parent.parent / 'build')
BUILD = parser.parse_args().build_dir.resolve()
WORK = BUILD
REPO = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / 'tests'))
import test_menu_payload as fixtures

fixtures.BUILD = BUILD
fixtures.old.ROOT = BUILD

# group, text, query, expected; these expectations are checked against actual x64.
CASES = [
    ('好人完整连续', '好人', '好人', True),
    ('好人完整连续', '他是个好人', '好人', True),
    ('好人完整连续', '好人好事', '好人', True),
    ('好人不拆单字', '好', '好人', False),
    ('好人不拆单字', '人', '好人', False),
    ('好人不拆单字', '真好', '好人', False),
    ('好人顺序连续', '人好', '好人', False),
    ('好人词内不忽略空格', '好 人', '好人', False),
    ('好人词内不忽略换行', '好\n人', '好人', False),
    ('好人词内不忽略标点', '好，人', '好人', False),
    ('好人词内不忽略其他字', '好的人', '好人', False),
    ('好人词内不忽略零宽字符', '好\u200b人', '好人', False),
    ('好人词内不忽略Emoji', '好👍人', '好人', False),
    ('简体中文', '重庆有很多好人', '好人 重庆', True),
    ('简体中文', '好人住在重庆', '重庆 好人', True),
    ('简体中文', '重庆只有风景', '好人 重庆', False),
    ('词内连续', '好 人住在重庆', '好人 重庆', False),
    ('跨行AND', '好人\n跨行描述\n重庆', '好人 重庆', True),
    ('繁体中文', '臺北的咖啡店很好', '臺北 咖啡', True),
    ('繁简不转换', '臺北的咖啡店很好', '台北 咖啡', False),
    ('繁简不转换', '重慶有好人', '重庆 好人', False),
    ('英语', 'Python tutorial for beginners', 'Python tutorial', True),
    ('英语顺序不限', 'A tutorial introduces Python', 'Python tutorial', True),
    ('英语缺词', 'Python reference guide', 'Python tutorial', False),
    ('大小写', 'Python tutorial', 'python tutorial', False),
    ('大小写', 'python tutorial', 'Python tutorial', False),
    ('大小写', 'python tutorial', 'python tutorial', True),
    ('日语', '東京で日本語を勉強しています', '東京 日本語', True),
    ('日语缺词', '大阪で日本語を勉強しています', '東京 日本語', False),
    ('韩语', '서울에서 한국어를 공부합니다', '서울 한국어', True),
    ('韩语缺词', '부산에서 한국어를 공부합니다', '서울 한국어', False),
    ('俄语', 'Москва: изучаем русский язык', 'Москва русский', True),
    ('俄语大小写', 'Москва: изучаем русский язык', 'москва русский', False),
    ('阿拉伯语', 'تعلم اللغة العربية في القاهرة', 'العربية القاهرة', True),
    ('阿拉伯语缺词', 'تعلم اللغة العربية في دبي', 'العربية القاهرة', False),
    ('阿拉伯语附标不消除', 'كِتاب جديد', 'كتاب', False),
    ('西语', 'Aprende español en Madrid', 'español Madrid', True),
    ('西语附标不消除', 'Aprende español en Madrid', 'espanol Madrid', False),
    ('西语大小写', 'Aprende español en Madrid', 'español madrid', False),
    ('混合语言', '上海 Python 入门 tutorial', '上海 Python tutorial', True),
    ('混合语言缺词', '北京 Python 入门 tutorial', '上海 Python tutorial', False),
    ('Emoji混合', '花🌸在東京', '🌸 東京', True),
    ('Emoji缺失', '花在東京', '🌸 東京', False),
    ('子串非整词', 'cats', 'cat', True),
    ('子串非整词', 'concatenate', 'cat', True),
    ('子串长度', 'cat', 'cats', False),
    ('不做词形转换', 'mice', 'mouse', False),
    ('不做词形转换', 'went', 'go', False),
    ('重音字面', 'café', 'café', True),
    ('重音不消除', 'café', 'cafe', False),
    ('NFC不转NFD', 'café', 'cafe\u0301', False),
    ('NFD不转NFC', 'cafe\u0301', 'café', False),
    ('相同NFD', 'cafe\u0301', 'cafe\u0301', True),
    ('全角不折叠', 'Ｐｙｔｈｏｎ', 'Python', False),
    ('全角相同', 'Ｐｙｔｈｏｎ', 'Ｐｙｔｈｏｎ', True),
    ('空格AND', 'blue comes before red', 'red blue', True),
    ('多空格AND', 'blue comes before red', '  red   blue  ', True),
    ('换行制表AND', 'blue comes before red', '\tred\nblue\r', True),
    ('全角空格AND', 'blue comes before red', 'red\u3000blue', True),
    ('不换行空格AND', 'blue comes before red', 'red\u00a0blue', True),
    ('窄不换行空格AND', 'blue comes before red', 'red\u202fblue', True),
    ('零宽空格不分词', 'red blue', 'red\u200bblue', False),
    ('零宽空格字面', 'red\u200bblue', 'red\u200bblue', True),
    ('重复词不计次数', 'cat', 'cat cat', True),
    ('两个词可重叠', 'foobar', 'foo oob', True),
    ('空格不要求文本分词', '猫狗', '猫 狗', True),
    ('空查询匹配器', 'anything', '', True),
    ('全空白匹配器', 'anything', ' \t\u3000', True),
    ('空消息', '', 'cat', False),
    ('引号不是短语语法', 'red blue', '"red blue"', False),
    ('引号仍按空白分词', '"red and blue"', '"red blue"', True),
    ('OR不是运算符', 'red', 'red OR blue', False),
    ('OR作为普通文本', 'blue OR red', 'red OR blue', True),
    ('OR甚至不是整词', 'red WORD blue', 'red OR blue', True),
    ('减号不是排除', 'red dog', 'red -cat', False),
    ('减号普通字符', 'red -cat', 'red -cat', True),
    ('星号不是通配', 'python', 'py*', False),
    ('星号普通字符', 'literal py* text', 'py*', True),
    ('问号不是通配', 'cat', 'c?t', False),
    ('问号普通字符', 'literal c?t text', 'c?t', True),
    ('括号不分组', 'red', '(red)', False),
    ('竖线不是或', 'red blue', 'red|blue', False),
    ('正则无特殊意义', 'red red', 'r.*d', False),
    ('网址字面', '说明见 https://example.com/docs', 'example.com docs', True),
    ('标点不移除', 'hello, world', 'hello world', True),
    ('标点必须存在', 'hello world', 'hello, world', False),
]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

paths = [BUILD / 'Telegram.exact.exe', BUILD / 'build' / 'payload.exe']
before = {p.name: digest(p) for p in paths}
reports = []
for base in (0x140000000, 0x7ff400000000):
    machine = fixtures.Machine(base)
    peer_receive_calls = []
    # This native receiver is outside the payload. Record the exact forwarded
    # vectors rather than letting execution continue into empty mapped pages.
    def receive_peers(args):
        peer_receive_calls.append((args[0], args[1], machine.values(args[1] + 8),
                                   machine.values(args[1] + 0x20)))
    machine.native(0x163af50, receive_peers)
    examples = []
    for group, text, query, expected in CASES:
        actual = bool(machine.call('AllKeywordsMatch', machine.qstring(text), machine.qstring(query)))
        assert actual == expected, (group, text, query, expected, actual)
        examples.append({'group': group, 'text': text, 'query': query, 'matched': actual})

    # Verify the actual public peer hook: entire query remains one substring.
    names = ['Python 教程', '教程 Python', 'Python 入门教程', 'Python  教程', 'Python\n教程']
    peers = [machine.peer(name) for name in names]
    inner = machine.inner('Python 教程')
    result = machine.alloc(0x50)
    machine.vector(peers, result + 8)
    machine.vector(peers, result + 0x20)
    machine.call('PatchPeers', inner, result)
    assert peer_receive_calls[-1][:2] == (inner, result)
    retained = [names[peers.index(peer)] for peer in machine.values(result + 8)]
    assert retained == ['Python 教程'], retained

    # Verify PatchLocal with a complete visible list and the same names.
    listing = machine.alloc(0x80)
    rows = [machine.row(machine.entry(name)) for name in names]
    machine.vector(rows, listing + 0x30)
    output = machine.alloc(24)
    machine.call('PatchLocal', listing, output, 0, inner)
    local_retained = [names[rows.index(row)] for row in machine.values(output)]
    assert local_retained == ['Python 教程'], local_retained

    # Same text candidates: global messages get AND; scoped search passes them.
    message_reports = []
    message_names = ['Python 教程', '教程 Python', 'Python 入门教程', '只有 Python']
    for scope in (0, 0x5e0, 0x98, 0xb8):
        message_inner = machine.inner('Python 教程', scope)
        items = [machine.item(name) for name in message_names]
        vector = machine.vector(items)
        start = len(machine.receive_calls)
        machine.call('PatchMessages', message_inner, vector, 0, 4, len(items))
        actual = [message_names[items.index(item)] for item in machine.receive_calls[start][1]]
        expected = message_names[:3] if scope == 0 else message_names
        assert actual == expected, (scope, actual)
        message_reports.append({'scope_offset': hex(scope), 'retained': actual})

    # User acceptance rule: query 好人 requires those two adjacent characters.
    # Exercise the exported hooks and their forwarded results, not just a matcher.
    haoren_candidates = ['好', '人', '真好', '好 人', '好\n人', '人好', '好，人',
                         '好的人', '好\u200b人', '好👍人', '好人', '他是个好人', '好人好事']
    haoren_expected = ['好人', '他是个好人', '好人好事']
    haoren_inner = machine.inner('好人')
    haoren_peers = [machine.peer(name) for name in haoren_candidates]
    haoren_result = machine.alloc(0x50)
    machine.vector(haoren_peers, haoren_result + 8)
    machine.vector(haoren_peers, haoren_result + 0x20)
    machine.call('PatchPeers', haoren_inner, haoren_result)
    assert peer_receive_calls[-1][:2] == (haoren_inner, haoren_result)
    haoren_peer_results = []
    for offset in (8, 0x20):
        actual = [haoren_candidates[haoren_peers.index(peer)]
                  for peer in machine.values(haoren_result + offset)]
        assert actual == haoren_expected, ('好人 public peer names', offset, actual)
        haoren_peer_results.append(actual)

    haoren_listing = machine.alloc(0x80)
    haoren_rows = [machine.row(machine.entry(name)) for name in haoren_candidates]
    machine.vector(haoren_rows, haoren_listing + 0x30)
    haoren_output = machine.alloc(24)
    machine.call('PatchLocal', haoren_listing, haoren_output, 0, haoren_inner)
    haoren_local = [haoren_candidates[haoren_rows.index(row)] for row in machine.values(haoren_output)]
    assert haoren_local == haoren_expected, ('好人 local names', haoren_local)

    haoren_message_results = []
    for scope in (0, 0x5e0, 0x98, 0xb8):
        for injected_text in ('好', '好人'):
            inner = machine.inner('好人', scope)
            items = [machine.item(name) for name in haoren_candidates]
            vector = machine.vector(items)
            injected = machine.item(injected_text)
            start = len(machine.receive_calls)
            machine.call('PatchMessages', inner, vector, injected, 4, len(items) + 1)
            received = machine.receive_calls[start]
            actual = [haoren_candidates[items.index(item)] for item in received[1]]
            expected = haoren_expected if scope == 0 else haoren_candidates
            assert actual == expected, ('好人 messages', scope, actual)
            expected_inject = injected if scope or injected_text == '好人' else 0
            assert received[2] == expected_inject, ('好人 injected item', scope, injected_text, received[2])
            haoren_message_results.append({'scope_offset': hex(scope), 'retained': actual,
                                           'injected_text': injected_text,
                                           'injected_retained': received[2] == injected})

    reports.append({'base': hex(base), 'all_keywords_cases': examples,
                    'peer_query': 'Python 教程', 'peer_names': names,
                    'peer_retained': retained, 'local_retained': local_retained,
                    'message_scope_checks': message_reports,
                    'haoren_contract': {'query': '好人', 'candidates': haoren_candidates,
                                        'public_peer_lists_retained': haoren_peer_results,
                                        'local_names_retained': haoren_local,
                                        'message_scope_checks': haoren_message_results}})
    del machine

after = {p.name: digest(p) for p in paths}
assert before == after, (before, after)
report = {'status': 'passed', 'case_count_per_base': len(CASES), 'hashes': before,
          'bases': reports, 'limits': ['Compiled x64 matcher and hooks with synthetic Qt/WinAPI objects only.',
                                    'Does not verify server retrieval or native UI query preprocessing.',
                                    'Literal query filtering is active for global search only; scoped message results and injections retain native passthrough.']}
(WORK / 'language-examples-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'status': report['status'], 'case_count_per_base': len(CASES), 'bases': [r['base'] for r in reports],
                  'hashes': before, 'peer_retained': reports[0]['peer_retained'],
                  'message_scope_checks': reports[0]['message_scope_checks'],
                  'haoren_contract': reports[0]['haoren_contract']}, ensure_ascii=False, indent=2))
