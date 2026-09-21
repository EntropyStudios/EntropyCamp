import subprocess
import unittest
from pathlib import Path


class SolarCycleCoreTests(unittest.TestCase):
    def test_beijing_cycle_and_work_modes(self):
        script = r"""
const assert=require('assert');
const core=require('./solar-cycle-core.js');
assert.equal(core.beijingDayProgress(Date.parse('2026-09-20T00:00:00Z')),0);
assert.equal(core.beijingDayProgress(Date.parse('2026-09-20T08:00:00Z')),0.5);
assert.ok(core.beijingDayProgress(Date.parse('2026-09-20T15:59:59Z'))>.9999);
assert.equal(core.beijingDayProgress(Date.parse('2026-09-20T16:00:00Z')),0);
assert.equal(core.beijingCycleOffset(Date.parse('2026-09-20T16:00:00Z')),16*60*60*1000);
const active=core.stateForSession({active:true,startedAt:123},Date.parse('2026-09-20T08:00:00Z'));
assert.equal(active.mode,'working');assert.equal(active.token,'start:123');assert.equal(active.dayProgress,.5);assert.equal(active.cycleOffsetMs,8*60*60*1000);
const ended=core.stateForSession({active:false,startedAt:123,endedAt:456},Date.parse('2026-09-20T08:00:00Z'));
assert.equal(ended.mode,'destroyed');assert.equal(ended.token,'end:456');
const fresh=core.stateForSession({},Date.parse('2026-09-20T08:00:00Z'));
assert.equal(fresh.mode,'day');assert.equal(fresh.token,'');
"""
        result = subprocess.run(["node", "-e", script], cwd=Path(__file__).parent, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
