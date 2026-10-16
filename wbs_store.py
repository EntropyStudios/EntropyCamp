"""Local WBS mirror. Linear contracts are read-only; links are explicitly confirmed."""
import json
import math
import os
import re
import threading
import time
import urllib.request
from pathlib import Path

from task_sync import write_json_atomic
from linear_auth import LinearAuth, AuthError

LOCK = threading.RLock()
ID = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")


class WbsError(ValueError):
    pass


class WbsStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / 'wbs.json'
        self.config = self.directory / 'wbs-linear.json'

    def _read(self):
        if not self.path.exists():
            return dict(revision=0, importedAt=None, projects=[], issues=[], modules=[], links={})
        return json.loads(self.path.read_text())

    def snapshot(self):
        with LOCK:
            return self._read()

    def settings(self):
        with LOCK:
            config = json.loads(self.config.read_text()) if self.config.exists() else {}
            return {'configured': bool(config.get('token')), 'teamKey': 'MOTION'}

    def save_settings(self, body):
        token = body.get('token')
        if not isinstance(token, str) or len(token) > 4096 or any(c.isspace() for c in token):
            raise WbsError('密钥格式无效')
        with LOCK:
            if token or body.get('clearToken'):
                write_json_atomic(self.config, {'token': token if not body.get('clearToken') else ''})
        return self.settings()

    @staticmethod
    def normalize(body):
        projects, issues, modules = body.get('projects'), body.get('issues'), body.get('modules', [])
        if not all(isinstance(x, list) for x in (projects, issues, modules)):
            raise WbsError('需要projects、issues、modules列表')
        if len(issues) > 10000 or len(projects) > 500 or len(modules) > 2000:
            raise WbsError('数据量超出限制')
        project_ids=set()
        for p in projects:
            if not isinstance(p,dict) or not isinstance(p.get('id'),str) or not p['id'] or not isinstance(p.get('name'),str) or p['id'] in project_ids:
                raise WbsError('Project字段无效或重复')
            project_ids.add(p['id'])
        if any(not isinstance(m,dict) or not isinstance(m.get('name'),str) or not isinstance(m.get('group'),str) for m in modules):
            raise WbsError('Module字段无效')
        seen = set()
        result = []
        for row in issues:
            identifier = row.get('id') if isinstance(row, dict) else None
            if not isinstance(identifier, str) or not ID.fullmatch(identifier) or identifier in seen:
                raise WbsError('Issue编号无效或重复')
            seen.add(identifier)
            if row.get('projectId') is not None and (not isinstance(row['projectId'],str) or row['projectId'] not in project_ids):
                raise WbsError('Issue所属Project不在完整快照中；不要丢失跨项目归属')
            parent = row.get('parentId')
            if parent is not None and (not isinstance(parent, str) or not ID.fullmatch(parent)):
                raise WbsError('父任务编号无效')
            description = str(row.get('description') or '')
            # Only explicit remaining-work metadata, never estimates/story points or date gaps.
            match = re.search(r'WBS\s*(?:剩余工期|预计工期)[^\n：:]*[：:]\s*(?:\*|\\)*\s*(\d+(?:\.\d+)?)', description)
            duration = float(match[1]) if match else None
            if duration is not None and not math.isfinite(duration):
                raise WbsError('工期无效')
            dependencies = row.get('blockedBy', [])
            if not isinstance(dependencies, list) or any(not isinstance(x, str) or not ID.fullmatch(x) for x in dependencies):
                raise WbsError('前置依赖须为Issue编号列表')
            spec = []
            for line in description.splitlines():
                if re.match(r'^\s*(?:\*\*|#+\s*)?前置依赖', line):
                    spec.extend(re.findall(r'\b[A-Z][A-Z0-9_]*-\d+\b', line))
            result.append({
                'id': identifier, 'title': str(row.get('title') or identifier),
                'description': description, 'parentId': parent,
                'projectId': row.get('projectId'), 'module': row.get('module') or '未分类',
                'assignee': str(row.get('assignee') or ''), 'status': str(row.get('status') or 'Todo'),
                'statusType': str(row.get('statusType') or 'unstarted'),
                'dueDate': row.get('dueDate'), 'updatedAt': row.get('updatedAt'),
                'blockedBy': sorted(set(dependencies)), 'specDependencies': sorted(set(spec)),
                'duration': duration, 'milestone': row.get('milestone'),
                'url': 'https://linear.app/sevenova/issue/' + identifier,
            })
        return {'projects': projects, 'issues': result, 'modules': modules}

    def preview(self, body):
        candidate = self.normalize(body)
        old = self.snapshot()
        before = {r['id']: r for r in old['issues']}
        after = {r['id']: r for r in candidate['issues']}
        return dict(expectedRevision=old['revision'], added=[k for k in after if k not in before],
                    removed=[k for k in before if k not in after],
                    changed=[k for k in after if k in before and after[k] != before[k]],
                    changes=[{'id':k,'fields':{field:{'before':before[k].get(field),'after':after[k].get(field)}
                                              for field in after[k] if after[k].get(field)!=before[k].get(field)}}
                             for k in after if k in before and after[k]!=before[k]])

    def import_data(self, body):
        candidate = self.normalize(body)
        if body.get('complete') is not True:
            raise WbsError('只接受完整分页的部门快照；请传complete=true')
        with LOCK:
            old = self._read()
            if body.get('expectedRevision') != old['revision']:
                raise WbsError('版本冲突，请刷新后重新预览')
            value = dict(candidate, revision=old['revision']+1, importedAt=int(time.time()*1000),
                         source='Linear · MOTION完整快照', links=old.get('links', {}))
            write_json_atomic(self.path, value)
            return value

    def link(self, body):
        with LOCK:
            value = self._read()
            if body.get('expectedRevision') != value['revision']:
                raise WbsError('版本冲突，请刷新后重试')
            identifier = body.get('issueId')
            issue = next((i for i in value['issues'] if i['id'] == identifier), None)
            if not issue or issue['parentId']:
                raise WbsError('飞书节点只关联已确认的父TASK，不关联推进子Issue')
            records = body.get('recordIds')
            if not isinstance(records, list) or len(records)>30 or any(not isinstance(x,str) or not re.fullmatch(r'rec[A-Za-z0-9_-]+', x) for x in records):
                raise WbsError('飞书记录ID格式无效')
            note = str(body.get('note') or '').strip()
            if records and not note:
                raise WbsError('请说明目的、范围、验收的对应依据')
            value.setdefault('links', {})[identifier] = {'recordIds':list(dict.fromkeys(records)), 'note':note, 'confirmedAt':int(time.time()*1000)}
            value['revision'] += 1
            write_json_atomic(self.path, value)
            return value

    def _query(self, query, variables=None):
        config = json.loads(self.config.read_text()) if self.config.exists() else {}
        try:
            token = LinearAuth(self.directory).bearer() or config.get('token')
        except AuthError as error:
            raise WbsError(str(error)) from None
        if not token:
            raise WbsError('请先登录Linear，再刷新任务')
        req = urllib.request.Request('https://api.linear.app/graphql',
            data=json.dumps({'query': query, 'variables': variables or {}}).encode(),
            headers={'Authorization':token, 'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=40) as response:
                result=json.load(response)
        except Exception:
            raise WbsError('Linear读取失败，请检查网络或重新登录；原快照保留') from None
        if result.get('errors') or not result.get('data'):
            raise WbsError('Linear查询未完整成功；原快照保留')
        return result['data']

    def fetch_linear(self):
        teams=self._query('query { teams { nodes { id key } } }')['teams']['nodes']
        team=next((x for x in teams if x['key']=='MOTION'),None)
        if not team:
            raise WbsError('未找到MOTION团队，不回退到其他部门')
        def pages(query, resource):
            after=None
            rows=[]
            for _ in range(300):
                connection=self._query(query, {'id':team['id'], 'after':after})['team'][resource]
                rows.extend(connection['nodes'])
                if not connection['pageInfo']['hasNextPage']:
                    return rows
                next_cursor=connection['pageInfo']['endCursor']
                if not next_cursor or next_cursor==after:
                    break
                after=next_cursor
            raise WbsError('Linear分页未完成，不覆盖原快照')
        projects=pages('query($id:String!,$after:String){team(id:$id){projects(first:50,after:$after){nodes{id name url description state} pageInfo{hasNextPage endCursor}}}}','projects')
        labels=pages('query($id:String!,$after:String){team(id:$id){labels(first:100,after:$after){nodes{id name parent{name}} pageInfo{hasNextPage endCursor}}}}','labels')
        issues=pages('query($id:String!,$after:String){team(id:$id){issues(first:10,after:$after){nodes{id identifier title description dueDate updatedAt state{name type} assignee{name} parent{identifier} project{id name} projectMilestone{name targetDate} labels(first:20){nodes{name parent{name}} pageInfo{hasNextPage endCursor}} relations(first:10){nodes{type relatedIssue{identifier}} pageInfo{hasNextPage endCursor}} inverseRelations(first:10){nodes{type issue{identifier}} pageInfo{hasNextPage endCursor}}} pageInfo{hasNextPage endCursor}}}}','issues')
        rows=[]
        def nested(i,resource,fields):
            connection=i.get(resource)
            if not connection:
                raise WbsError('Issue关系读取不完整，不覆盖快照')
            nodes=list(connection['nodes']);seen=set()
            while connection['pageInfo']['hasNextPage']:
                cursor=connection['pageInfo'].get('endCursor')
                if not cursor or cursor in seen:raise WbsError('Issue依赖关系分页未完成，不覆盖快照')
                seen.add(cursor)
                query='query($id:String!,$after:String){issue(id:$id){'+resource+'(first:50,after:$after){nodes{'+fields+'} pageInfo{hasNextPage endCursor}}}}'
                connection=self._query(query,{'id':i['id'],'after':cursor})['issue'][resource]
                nodes.extend(connection['nodes'])
                if len(seen)>100:raise WbsError('Issue关系分页超出限制')
            return nodes
        for i in issues:
            relations=nested(i,'relations','type relatedIssue{identifier}')
            inverse=nested(i,'inverseRelations','type issue{identifier}')
            issue_labels=nested(i,'labels','name parent{name}')
            pname=(i.get('project') or {}).get('name')
            module=next((l['name'] for l in issue_labels if (l.get('parent') or {}).get('name')=='WBS · '+str(pname)), '未分类')
            rows.append(dict(id=i['identifier'],title=i['title'],description=i['description'],
                parentId=(i.get('parent') or {}).get('identifier'),projectId=(i.get('project') or {}).get('id'),
                module=module,assignee=(i.get('assignee') or {}).get('name'),status=i['state']['name'],statusType=i['state']['type'],
                dueDate=i['dueDate'],updatedAt=i['updatedAt'],milestone=i.get('projectMilestone'),
                blockedBy=([r['relatedIssue']['identifier'] for r in relations if r['type']=='blocked_by']+
                           [r['issue']['identifier'] for r in inverse if r['type']=='blocks'])))
        return {'projects':projects,'issues':rows,'modules':[{'name':l['name'],'group':(l.get('parent') or {}).get('name')} for l in labels if (l.get('parent') or {}).get('name','').startswith('WBS · ')], 'complete':True}
