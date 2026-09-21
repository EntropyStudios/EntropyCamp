import subprocess
import unittest
from pathlib import Path


class PlanetVisualCoreTests(unittest.TestCase):
    def test_rounds_are_unique_stable_and_recycling_draws_next_card(self):
        script = r"""
const assert = require('assert');
const core = require('./planet-visual-core.js');
const cards = Array.from({length: 24}, (_, index) => ({id: `card-${index}`}));
assert.equal(core.ensureAssignments(cards), true);
assert.equal(core.PLANET_KEYS.length, 11);
for (let start = 0; start < 22; start += 11) {
  const round = cards.slice(start, start + 11).map(card => card.visualPlanetKey);
  assert.equal(new Set(round).size, 11, `round ${start / 11} repeated a planet`);
}
const snapshot = new Map(cards.map(card => [card.id, [card.visualPlanetSequence, card.visualPlanetKey]]));
cards.reverse();
assert.equal(core.ensureAssignments(cards), false);
cards.forEach(card => assert.deepEqual(
  [card.visualPlanetSequence, card.visualPlanetKey], snapshot.get(card.id),
));
const target = cards.find(card => card.id === 'card-0');
const before = target.visualPlanetSequence;
const assignmentBefore = new Map(cards.map(card=>[card.id,[card.visualPlanetSequence,card.visualPlanetKey]]));
const assignment = core.assignNext(target, cards);
assert.equal(assignment.sequence, 1);
assert.ok(assignment.sequence > before);
assert.deepEqual(cards.map(card=>card.visualPlanetSequence).sort((a,b)=>a-b),
  Array.from({length:cards.length},(_,index)=>index));
assert.equal(target.visualPlanetKey, core.planetKeyForSequence(target.visualPlanetSequence));
assert.ok(core.PLANET_KEYS.includes(target.visualPlanetKey));
const changed=cards.filter(card=>{
 const previous=assignmentBefore.get(card.id);return previous[0]!==card.visualPlanetSequence||previous[1]!==card.visualPlanetKey;
});
assert.equal(changed.length,2,'rebirth changed more than the target and its swap partner');
for(let start=0;start<cards.length;start+=core.PLANET_KEYS.length){
 const round=cards.filter(card=>card.visualPlanetSequence>=start&&card.visualPlanetSequence<start+core.PLANET_KEYS.length)
   .map(card=>card.visualPlanetKey);
 assert.equal(new Set(round).size,round.length);
}
console.log(JSON.stringify({pool: core.PLANET_KEYS, assignment}));
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_invalid_or_duplicate_sequences_are_repaired(self):
        script = r"""
const assert = require('assert');
const core = require('./planet-visual-core.js');
const cards = [
  {id:'a', visualPlanetSequence:3, visualPlanetKey:'wrong'},
  {id:'b', visualPlanetSequence:3},
  {id:'c', visualPlanetSequence:-2},
];
assert.equal(core.ensureAssignments(cards), true);
assert.equal(new Set(cards.map(card => card.visualPlanetSequence)).size, 3);
cards.forEach(card => {
  assert.ok(Number.isInteger(card.visualPlanetSequence));
  assert.ok(card.visualPlanetSequence >= 0);
  assert.equal(card.visualPlanetKey, core.planetKeyForSequence(card.visualPlanetSequence));
});
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_clock_in_rerolls_all_cards_without_repeating_inside_rounds(self):
        script = r"""
const assert=require('assert');
const core=require('./planet-visual-core.js');
const cards=Array.from({length:24},(_,index)=>({id:`card-${index}`}));
core.ensureAssignments(cards);
const before=new Map(cards.map(card=>[card.id,card.visualPlanetSequence]));
assert.equal(core.rerollAssignments(cards,1789890000123),true);
assert.ok(cards.some(card=>card.visualPlanetSequence!==before.get(card.id)));
assert.deepEqual(cards.map(card=>card.visualPlanetSequence).sort((a,b)=>a-b),Array.from({length:24},(_,index)=>index));
for(let start=0;start<cards.length;start+=core.PLANET_KEYS.length){
 const keys=cards.filter(card=>card.visualPlanetSequence>=start&&card.visualPlanetSequence<start+core.PLANET_KEYS.length).map(card=>card.visualPlanetKey);
 assert.equal(new Set(keys).size,keys.length);
}
const snapshot=cards.map(card=>[card.id,card.visualPlanetSequence,card.visualPlanetKey]);
const replay=Array.from({length:24},(_,index)=>({id:`card-${index}`}));core.ensureAssignments(replay);core.rerollAssignments(replay,1789890000123);
assert.deepEqual(replay.map(card=>[card.id,card.visualPlanetSequence,card.visualPlanetKey]),snapshot);
"""
        result = subprocess.run(["node", "-e", script], cwd=Path(__file__).parent, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_gapped_historical_sequences_are_compacted_into_unique_current_rounds(self):
        script = r"""
const assert = require('assert');
const core = require('./planet-visual-core.js');
const historical = [1,3,5,7,8,9,10,11,12,22,33,34,35,36];
const cards = historical.map((sequence,index)=>({
  id:`card-${index}`,
  visualPlanetSequence:sequence,
  visualPlanetKey:core.planetKeyForSequence(sequence),
}));
assert.equal(core.ensureAssignments(cards),true);
assert.deepEqual(cards.map(card=>card.visualPlanetSequence).sort((a,b)=>a-b),
  Array.from({length:cards.length},(_,index)=>index));
for(let start=0;start<cards.length;start+=core.PLANET_KEYS.length){
  const round=cards.filter(card=>card.visualPlanetSequence>=start&&card.visualPlanetSequence<start+core.PLANET_KEYS.length)
    .map(card=>card.visualPlanetKey);
  assert.equal(new Set(round).size,round.length,`current round ${start/core.PLANET_KEYS.length} repeated a planet`);
}
const counts=new Map();cards.forEach(card=>counts.set(card.visualPlanetKey,(counts.get(card.visualPlanetKey)||0)+1));
assert.ok(Math.max(...counts.values())<=Math.ceil(cards.length/core.PLANET_KEYS.length));
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_acknowledgement_clears_cloud_and_assigns_rebirth_planet(self):
        script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const planetVisualCore = require('./planet-visual-core.js');
const source = fs.readFileSync('./app.js', 'utf8');
const start = source.indexOf('function acknowledgeAndReassignCard(');
const end = source.indexOf('\nfunction recycleCompletedCard', start);
const cards = [
  {id:'codex',codexThreadId:'thread',codexDue:true,codexLatestTurnId:'turn-2',codexLastSeenTurnId:'turn-1',visualShatteredToken:'codex:turn-2'},
  {id:'timer',codexThreadId:'',started:true,nextAt:1,intervalMs:60000,visualShatteredToken:'timer:1'},
];
planetVisualCore.ensureAssignments(cards);
const context = { cards, planetVisualCore, Date, startTimer: card => ({...card,started:true,nextAt:Date.now()+card.intervalMs}) };
vm.createContext(context);
vm.runInContext(source.slice(start,end),context);
const previousMaximum = Math.max(...cards.map(card=>card.visualPlanetSequence));
const codexSource = context.acknowledgeAndReassignCard(cards[0]);
assert.equal(codexSource,'turn-2');
assert.equal(cards[0].codexDue,false);
assert.equal(cards[0].codexLastSeenTurnId,'turn-2');
assert.equal(cards[0].visualShatteredToken,'');
assert.equal(cards[0].visualPlanetSequence,previousMaximum);
assert.equal(cards[1].visualPlanetSequence,0);
assert.ok(Number.isFinite(cards[0].visualRebirthAt));
const timerSource = context.acknowledgeAndReassignCard(cards[1]);
assert.equal(timerSource,1);
assert.ok(cards[1].nextAt>Date.now());
assert.equal(cards[1].visualShatteredToken,'');
assert.equal(cards[1].visualPlanetSequence,1);
assert.equal(cards[0].visualPlanetSequence,0);
assert.equal(new Set(cards.map(card=>card.visualPlanetKey)).size,2);
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_consecutive_recycles_serialize_saves_without_dropping_requests(self):
        script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const planetVisualCore=require('./planet-visual-core.js');
const source=fs.readFileSync('./app.js','utf8');
const start=source.indexOf('function acknowledgeAndReassignCard(');
const end=source.indexOf('\nfunction populateCodexSelect',start);
const cards=[
 {id:'a',cardId:'a',codexThreadId:'a',codexLatestTurnId:'turn-a',codexDue:true,visualShatteredToken:'codex:a'},
 {id:'b',cardId:'b',codexThreadId:'b',codexLatestTurnId:'turn-b',codexDue:true,visualShatteredToken:'codex:b'},
];
planetVisualCore.ensureAssignments(cards);
let activeSaves=0,maxActiveSaves=0,renders=0;const releases=[];
const context={cards,planetVisualCore,Date,startTimer:card=>card,enqueueFeishuEvent(){},showGraphNodeInspector(){},render(){renders++;},
 saveCards:async()=>{activeSaves++;maxActiveSaves=Math.max(maxActiveSaves,activeSaves);await new Promise(resolve=>releases.push(()=>{activeSaves--;resolve();}));return true;}};
vm.createContext(context);
vm.runInContext('let recycleSaveQueue=Promise.resolve();\n'+source.slice(start,end),context);
(async()=>{
 const first=context.recycleCompletedCard({cardId:'a'});
 const second=context.recycleCompletedCard({cardId:'b'});
 await new Promise(setImmediate);
 assert.equal(releases.length,1);assert.equal(activeSaves,1);
 releases.shift()();await new Promise(setImmediate);
 assert.equal(releases.length,1);assert.equal(activeSaves,1);
 releases.shift()();
 assert.deepEqual(await Promise.all([first,second]),[true,true]);
 assert.equal(maxActiveSaves,1);assert.equal(renders,2);
 assert.equal(cards[0].visualShatteredToken,'');assert.equal(cards[1].visualShatteredToken,'');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        result = subprocess.run(
            ["node", "-e", script], cwd=Path(__file__).parent,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
