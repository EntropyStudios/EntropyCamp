import subprocess
import unittest
from pathlib import Path


class ClipboardNumberingTests(unittest.TestCase):
    def test_numbering_survives_blank_lines_and_intervening_paragraphs(self):
        script = r'''
const assert = require('node:assert/strict');
const core = require('./clipboard-core.js');
let blocks=core.parseMarkdown('1. One\n\n2. Two\n\n3. Three\n\n4. Four');
assert.equal(blocks.length,1);assert.equal(blocks[0].start,1);assert.equal(blocks[0].items.length,4);
blocks=core.parseMarkdown('1. One\n\nExplanation\n\n2. Two\n\nExplanation\n\n3. Three\n\nExplanation\n\n4. Four');
assert.deepEqual(blocks.filter(b=>b.type==='list').map(b=>b.start),[1,2,3,4]);
assert.equal(core.parseMarkdown('7) Seven\n8) Eight')[0].start,7);
assert.equal(core.parseMarkdown('1. One\n1. Two\n1. Three')[0].items.length,3);
assert.equal(core.parseMarkdown('- One\n\n- Two')[0].ordered,false);
'''
        result=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parent,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
