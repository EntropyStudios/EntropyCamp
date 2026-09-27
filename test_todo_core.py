import json
import subprocess
import unittest
from pathlib import Path


class TodoCoreTests(unittest.TestCase):
    @staticmethod
    def run_core(script):
        root = Path(__file__).parent
        result = subprocess.run(
            ["node", "-e", script, str(root / "todo-core.js")],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_normalization_rejects_invalid_fields_and_duplicate_ids(self):
        result = self.run_core(r"""
const core=require(process.argv[1]);
console.log(JSON.stringify(core.normalizeStore({version:1,items:[
 {id:'a',title:'  今天完成  ',section:'today',priority:'high',order:2,createdAt:10,updatedAt:20},
 {id:'a',title:'重复 ID',section:'bad',priority:'bad',createdAt:30},
 {id:'empty',title:'   ',createdAt:40},
]})));
""")
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["title"], "今天完成")
        self.assertEqual(result["items"][0]["section"], "today")
        self.assertEqual(result["items"][0]["priority"], "high")
        self.assertNotEqual(result["items"][0]["id"], result["items"][1]["id"])
        self.assertEqual(result["items"][1]["section"], "inbox")

    def test_views_priority_summary_and_reordering_are_stable(self):
        result = self.run_core(r"""
const core=require(process.argv[1]);
const items=core.normalizeStore({version:1,items:[
 {id:'normal',title:'Normal',section:'today',priority:'normal',order:0,createdAt:1},
 {id:'normal-2',title:'Normal 2',section:'today',priority:'normal',order:1,createdAt:5},
 {id:'high',title:'High',section:'today',priority:'high',order:9,createdAt:2},
 {id:'done',title:'Done',section:'today',priority:'low',completedAt:30,createdAt:3},
 {id:'later',title:'Later',section:'later',priority:'high',createdAt:4},
]}).items;
const moved=core.moveItem(items,'normal',1);
console.log(JSON.stringify({
 today:core.sortItems(items,'today').map(x=>x.id),
 completed:core.sortItems(items,'completed').map(x=>x.id),
 summary:core.todaySummary(items),
 moved:core.sortItems(moved,'today').map(x=>x.id),
 original:items.map(x=>[x.id,x.order]),
 next:core.nextOrder(items,'today'),
}));
""")
        self.assertEqual(result["today"], ["high", "normal", "normal-2"])
        self.assertEqual(result["completed"], ["done"])
        self.assertEqual(result["summary"], {"total": 4, "completed": 1, "remaining": 3})
        self.assertEqual(result["moved"], ["high", "normal-2", "normal"])
        self.assertEqual(result["original"], [["normal", 0], ["normal-2", 1], ["high", 9], ["done", 3], ["later", 4]])
        self.assertEqual(result["next"], 10)


if __name__ == "__main__":
    unittest.main()
