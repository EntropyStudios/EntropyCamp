"""Read local DeepSeek Harness v4 logs; never access providers or credentials."""
import copy
import json
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

PREFIX = 'deepseek-'
SESSION_ID = re.compile(r'^(?:session-)?[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$')


def is_deepseek(identifier):
    return isinstance(identifier, str) and identifier.startswith(PREFIX)


class DeepSeekSessions:
    def __init__(self, home):
        self.root = Path(home).expanduser() / 'sessions'
        self.lock = threading.RLock()
        self.cache = {}

    @staticmethod
    def empty(identifier):
        return {'id': identifier, 'name': 'DeepSeek 对话', 'preview': '', 'provider': 'deepseek',
                'hostId': 'local', 'sourceLabel': 'DeepSeek · 本机', 'exists': False,
                'status': 'unavailable', 'phase': 'unavailable', 'phaseLabel': '日志不可用',
                'model': '', 'reasoningEffort': '', 'cwd': '', 'updatedAt': None,
                'activityStartedAt': None, 'toolKind': '', 'latestCompletedAt': None,
                'latestCompletedTurnId': None, 'turns': []}

    def _paths(self):
        paths = {}
        if self.root.is_dir():
            for name in ('session.v4.jsonl', 'session.v4.jsonl.zstd'):
                for path in self.root.glob('*/*/' + name):
                    sid = path.parent.name
                    if SESSION_ID.fullmatch(sid) and path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(self.root.resolve()):
                        identifier = PREFIX + sid
                        if identifier not in paths or path.stat().st_mtime_ns > paths[identifier].stat().st_mtime_ns:
                            paths[identifier] = path
        return paths

    def _read(self, identifier, path):
        if path is None:
            return self.empty(identifier)
        try:
            stat = path.stat()
            signature = (str(path), stat.st_ino, stat.st_size, stat.st_mtime_ns)
            cached = self.cache.get(identifier)
            if cached and cached[0] == signature:
                return cached[1]
            result = self.empty(identifier)
            result.update(exists=True, status='idle', phase='idle', phaseLabel='保持关注')
            # Read compressed logs through the installed decoder into an anonymous
            # temporary file, avoiding a second full in-memory copy or extracted assets.
            with tempfile.TemporaryFile() as raw:
                if path.suffix == '.zstd':
                    decoder = shutil.which('zstd')
                    if not decoder:
                        raise OSError('未安装 zstd，无法读取 DeepSeek 日志')
                    subprocess.run([decoder, '-dc', '--', str(path)], stdout=raw, stderr=subprocess.PIPE, timeout=15, check=True)
                    raw.seek(0)
                    self._parse(result, raw)
                else:
                    with path.open('rb') as source:
                        self._parse(result, source)
            self.cache[identifier] = (signature, result)
            return result
        except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError):
            return self.empty(identifier)

    @staticmethod
    def _parse(result, lines):
        current = None
        seen = set()
        for line in lines:
            if not line.endswith(b'\n'):
                continue
            try:
                row = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(row, dict):
                continue
            kind = row.get('type')
            if kind == 'session':
                if row.get('delegationDepth', 0) or row.get('parentSessionId'):
                    result['exists'] = False
                    return
                result['cwd'] = str(row.get('cwd') or '')
                continue
            seq = row.get('seq')
            if seq is not None and seq in seen:
                continue
            seen.add(seq)
            data = row.get('data') or {}
            if not isinstance(data, dict):
                continue
            stamp = row.get('time')
            if not isinstance(stamp, (float, int)):
                continue
            when = stamp / 1000
            if kind == 'session/title' and isinstance(data.get('title'), str):
                result['name'] = data['title'][:160]
            if kind in {'request/context', 'model/selection'}:
                result['model'] = str(data.get('model') or result['model'])
                result['reasoningEffort'] = str(data.get('reasoningEffort') or result['reasoningEffort'])
            if kind == 'turn/start':
                current = {'id': f"{result['id']}:turn-{data.get('turn', seq)}", 'startedAt': when,
                           'completedAt': None, 'status': 'inProgress', 'items': []}
                result.update(status='active', phase='reasoning', phaseLabel='处理中', activityStartedAt=when, toolKind='')
            if current is None:
                continue
            source = data.get('source') if isinstance(data.get('source'), dict) else {}
            if kind == 'user/message' and source.get('kind') == 'user':
                content = data.get('content') if isinstance(data.get('content'), list) else []
                text = '\n'.join(p.get('text', '') for p in content if isinstance(p, dict) and p.get('type') == 'text' and isinstance(p.get('text'), str)).strip()
                if text:
                    if current not in result['turns']:
                        result['turns'].append(current)
                    current['items'].append({'role': 'user', 'phase': 'user', 'text': text, 'timestamp': when})
                    result['preview'] = result['preview'] or text[:160]
                    if result['name'] == 'DeepSeek 对话':
                        result['name'] = text.splitlines()[0][:100]
            elif kind == 'assistant/message':
                message = data.get('message') if isinstance(data.get('message'), dict) else {}
                parts = message.get('content') if isinstance(message.get('content'), list) else []
                for part in parts:
                    if isinstance(part, dict) and part.get('type') == 'text' and part.get('text'):
                        current['items'].append({'role': 'assistant', 'phase': 'commentary', 'text': str(part['text']), 'timestamp': when})
                has_text = any(isinstance(p, dict) and p.get('type') == 'text' for p in parts)
                tools = [p for p in parts if isinstance(p, dict) and p.get('type') == 'tool-call']
                phase = 'executing' if tools else 'outputting' if has_text else 'reasoning'
                result.update(phase=phase, phaseLabel={'executing':'执行工具', 'outputting':'AI 输出', 'reasoning':'处理中'}[phase],
                              toolKind=str(tools[-1].get('name') or '') if tools else '')
            elif kind == 'tool/call':
                name = str(data.get('name') or 'Tool')
                current['items'].append({'role': 'assistant', 'phase': 'tool', 'text': '调用工具：' + name, 'timestamp': when})
                result.update(phase='executing', phaseLabel='执行工具', toolKind=name)
            elif kind == 'step/start':
                result.update(phase='reasoning', phaseLabel='处理中', toolKind='')
            elif kind == 'turn/end':
                if data.get('turn') is not None and current['id'] != f"{result['id']}:turn-{data['turn']}":
                    continue
                reason = data.get('reason') if isinstance(data.get('reason'), dict) else {}
                assistants = [item for item in current['items'] if item['phase'] == 'commentary' and item['role'] == 'assistant']
                if isinstance(reason, dict) and reason.get('kind') == 'completed' and assistants and current in result['turns']:
                    assistants[-1]['phase'] = 'final_answer'
                    current.update(status='completed', completedAt=when)
                    result.update(latestCompletedTurnId=current['id'], latestCompletedAt=when)
                else:
                    current['status'] = 'interrupted' if reason.get('kind') == 'aborted' else 'failed'
                result.update(status='idle', phase='idle', phaseLabel='保持关注', activityStartedAt=None, toolKind='')
                current = None
            if kind in {'turn/start', 'turn/end', 'user/message', 'assistant/message', 'tool/call', 'step/start'}:
                result['updatedAt'] = max(result.get('updatedAt') or 0, when)

    def list_threads(self, limit=200):
        with self.lock:
            rows = [self._read(identifier, path) for identifier, path in self._paths().items()]
            return [{k:v for k,v in row.items() if k != 'turns'} for row in sorted(rows, key=lambda r:r.get('updatedAt') or 0, reverse=True) if row['exists'] and row['turns']][:limit]

    def thread_statuses(self, identifiers):
        with self.lock:
            paths = self._paths()
            return [{k:v for k,v in self._read(identifier, paths.get(identifier)).items() if k != 'turns'} for identifier in identifiers]

    def work_logs(self, identifiers, since=None, until=None, include_process=True):
        with self.lock:
            paths = self._paths()
            logs = []
            for identifier in identifiers:
                row = self._read(identifier, paths.get(identifier))
                turns = []
                for turn in row['turns']:
                    end = turn.get('completedAt') or turn['startedAt']
                    if since is not None and end < since or until is not None and turn['startedAt'] > until:
                        continue
                    value = copy.deepcopy(turn)
                    value['items'] = [item for item in value['items'] if (include_process or item['role'] == 'user' or item['phase'] == 'final_answer') and (until is None or item['timestamp'] <= until)]
                    if until is not None and end > until:
                        value.update(completedAt=None, status='inProgress')
                    turns.append(value)
                logs.append({'id':identifier, 'name':row['name'], 'provider':'deepseek', 'hostId':'local', 'turns':turns,
                             **({'error':'DeepSeek Harness 日志不可用'} if not row['exists'] else {})})
            return logs
