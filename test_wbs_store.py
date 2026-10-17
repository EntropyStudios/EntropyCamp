import tempfile
import unittest
from unittest.mock import patch
from wbs_store import WbsStore, WbsError


class WbsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = WbsStore(self.temp.name)
        self.body = {'complete': True, 'expectedRevision': 0, 'projects': [{'id':'p','name':'V3'}], 'modules': [],
                     'issues': [{'id':'MOTION-1','title':'父','projectId':'p'},
                                {'id':'MOTION-2','title':'子','projectId':'p','parentId':'MOTION-1'}]}

    def test_import_updates_parent_type_and_project_not_stale_fields(self):
        first=self.store.import_data(self.body)
        self.assertEqual(first['issues'][1]['parentId'],'MOTION-1')
        self.body['expectedRevision']=1
        self.body['projects'].append({'id':'other','name':'其他项目'})
        self.body['issues'][1].update(parentId=None, projectId='other', status='Canceled',statusType='canceled')
        second=self.store.import_data(self.body)
        self.assertIsNone(second['issues'][1]['parentId'])
        self.assertEqual(second['issues'][1]['projectId'],'other')
        self.assertEqual(second['issues'][1]['statusType'],'canceled')

    def test_incomplete_or_conflicting_import_preserves_snapshot(self):
        self.store.import_data(self.body)
        with self.assertRaises(WbsError): self.store.import_data(self.body)
        self.body.update(expectedRevision=1,complete=False)
        with self.assertRaises(WbsError): self.store.import_data(self.body)
        self.assertEqual(self.store.snapshot()['revision'],1)

    def test_explicit_links_survive_import_and_child_cannot_link(self):
        self.store.import_data(self.body)
        result=self.store.link({'issueId':'MOTION-1','recordIds':['recABC'],'note':'相同范围及验收','expectedRevision':1})
        self.assertEqual(result['revision'],2)
        with self.assertRaises(WbsError): self.store.link({'issueId':'MOTION-2','recordIds':[],'expectedRevision':2})
        self.body['expectedRevision']=2
        self.assertEqual(self.store.import_data(self.body)['links']['MOTION-1']['recordIds'],['recABC'])

    def test_story_points_and_dates_do_not_become_duration(self):
        self.body['issues'][0].update(estimate=8,dueDate='2026-10-20',description='前置依赖：MOTION-5\nWBS 剩余工期：2.5 个工作日')
        self.body['issues'][1].update(estimate=10,dueDate='2026-10-25')
        rows=self.store.import_data(self.body)['issues']
        self.assertEqual(rows[0]['duration'],2.5)
        self.assertEqual(rows[0]['specDependencies'],['MOTION-5'])
        self.assertEqual(rows[0]['blockedBy'],[])
        self.assertIsNone(rows[1]['duration'])

    def test_secret_not_in_settings_or_snapshot(self):
        self.store.save_settings({'token':'secret-unit-test'})
        self.assertTrue(self.store.settings()['configured'])
        self.assertNotIn('secret-unit-test',str(self.store.settings())+str(self.store.snapshot()))
        self.assertEqual(self.store.config.stat().st_mode&0o777,0o600)

    def test_refresh_does_not_fallback_to_another_team(self):
        with patch.object(self.store,'_query',return_value={'teams':{'nodes':[{'id':'nav','key':'NAV'}]}}):
            with self.assertRaisesRegex(WbsError,'MOTION'): self.store.fetch_linear()

    def test_no_partial_refresh_when_dependency_pagination_incomplete(self):
        pages=[{'teams':{'nodes':[{'id':'t','key':'MOTION'}]}},
               {'team':{'projects':{'nodes':[],'pageInfo':{'hasNextPage':False}}}},
               {'team':{'labels':{'nodes':[],'pageInfo':{'hasNextPage':False}}}},
               {'team':{'issues':{'nodes':[{'relations':{'nodes':[],'pageInfo':{'hasNextPage':True}}}], 'pageInfo':{'hasNextPage':False}}}}]
        with patch.object(self.store,'_query',side_effect=pages):
            with self.assertRaisesRegex(WbsError,'分页'): self.store.fetch_linear()

    def test_refresh_reads_all_nested_relations_and_native_incoming_blocks(self):
        def conn(rows,more=False,cursor=None):return {'nodes':rows,'pageInfo':{'hasNextPage':more,'endCursor':cursor}}
        issue={'id':'uuid','identifier':'MOTION-2','title':'后续','description':'', 'dueDate':None,'updatedAt':'now',
               'state':{'name':'Todo','type':'unstarted'},'assignee':None,'parent':None,'project':{'id':'p','name':'V3'},'projectMilestone':None,
               'labels':conn([{'name':'规划','parent':{'name':'WBS · V3'}}]),
               'relations':conn([{'type':'related','relatedIssue':{'identifier':'MOTION-8'}}],True,'next'),
               'inverseRelations':conn([{'type':'blocks','issue':{'identifier':'MOTION-1'}}])}
        pages=[{'teams':{'nodes':[{'id':'t','key':'MOTION'}]}}, {'team':{'projects':conn([{'id':'p','name':'V3'}])}},
               {'team':{'labels':conn([])}},{'team':{'issues':conn([issue])}},
               {'issue':{'relations':conn([{'type':'blocked_by','relatedIssue':{'identifier':'MOTION-3'}}])}}]
        with patch.object(self.store,'_query',side_effect=pages) as query:
            result=self.store.fetch_linear()
        self.assertEqual(result['issues'][0]['blockedBy'],['MOTION-3','MOTION-1'])
        self.assertEqual(result['issues'][0]['module'],'规划')
        self.assertEqual(query.call_args.args[1],{'id':'uuid','after':'next'})


if __name__=='__main__': unittest.main()
