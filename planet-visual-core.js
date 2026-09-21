(function attachPlanetVisualCore(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PlanetVisualCore = api;
})(typeof globalThis !== "undefined" ? globalThis : window, function createPlanetVisualCore() {
  "use strict";

  const PLANET_KEYS = Object.freeze([
    "ash-twin",
    "ember-twin",
    "timber-hearth",
    "attlerock",
    "brittle-hollow",
    "hollows-lantern",
    "giants-deep",
    "dark-bramble",
    "interloper",
    "quantum-moon",
    "stranger",
  ]);

  function mulberry32(seed) {
    return function random() {
      let value = seed += 0x6d2b79f5;
      value = Math.imul(value ^ value >>> 15, value | 1);
      value ^= value + Math.imul(value ^ value >>> 7, value | 61);
      return ((value ^ value >>> 14) >>> 0) / 4294967296;
    };
  }

  function shuffledRound(round) {
    const values = [...PLANET_KEYS];
    const random = mulberry32((0x454e5452 ^ Math.imul(round + 1, 0x9e3779b1)) >>> 0);
    for (let index = values.length - 1; index > 0; index -= 1) {
      const target = Math.floor(random() * (index + 1));
      [values[index], values[target]] = [values[target], values[index]];
    }
    return values;
  }

  function validSequence(value) {
    return Number.isInteger(value) && value >= 0;
  }

  function planetKeyForSequence(sequence) {
    if (!validSequence(sequence)) throw new TypeError("Planet sequence must be a non-negative integer");
    const round = Math.floor(sequence / PLANET_KEYS.length);
    return shuffledRound(round)[sequence % PLANET_KEYS.length];
  }

  function ensureAssignments(cards) {
    const values = Array.isArray(cards) ? cards : [];
    let changed = false;
    const ordered = values.map((card, index) => ({ card, index })).filter(({ card }) => card).sort((left, right) => {
      const leftSequence = left.card.visualPlanetSequence;
      const rightSequence = right.card.visualPlanetSequence;
      const leftValid = validSequence(leftSequence);
      const rightValid = validSequence(rightSequence);
      if (leftValid !== rightValid) return leftValid ? -1 : 1;
      if (leftValid && leftSequence !== rightSequence) return leftSequence - rightSequence;
      return left.index - right.index;
    });
    ordered.forEach(({ card }, sequence) => {
      const key = planetKeyForSequence(sequence);
      if (card.visualPlanetSequence !== sequence) {
        card.visualPlanetSequence = sequence;
        changed = true;
      }
      if (card.visualPlanetKey !== key) {
        card.visualPlanetKey = key;
        changed = true;
      }
    });
    return changed;
  }

  function assignNext(card, cards) {
    if (!card) throw new TypeError("Card is required");
    const values = Array.isArray(cards) ? cards : [];
    ensureAssignments(values);
    const current = validSequence(card.visualPlanetSequence) ? card.visualPlanetSequence : 0;
    const sequence = values.length > 1 ? (current + 1) % values.length : current;
    const partner = values.find((item) => item && item !== card && item.visualPlanetSequence === sequence);
    if (partner) {
      partner.visualPlanetSequence = current;
      partner.visualPlanetKey = planetKeyForSequence(current);
    }
    card.visualPlanetSequence = sequence;
    const key = planetKeyForSequence(sequence);
    card.visualPlanetKey = key;
    return { sequence, key, round: Math.floor(sequence / PLANET_KEYS.length) };
  }

  function rerollAssignments(cards, seed = Date.now()) {
    const values = (Array.isArray(cards) ? cards : []).filter(Boolean);
    const numericSeed = Number.isFinite(Number(seed)) ? Number(seed) : Date.now();
    const random = mulberry32((numericSeed ^ Math.floor(numericSeed / 0x100000000) ^ 0x43414d50) >>> 0);
    const shuffled = [...values];
    for (let index = shuffled.length - 1; index > 0; index -= 1) {
      const target = Math.floor(random() * (index + 1));
      [shuffled[index], shuffled[target]] = [shuffled[target], shuffled[index]];
    }
    let changed = false;
    shuffled.forEach((card, sequence) => {
      const key = planetKeyForSequence(sequence);
      if (card.visualPlanetSequence !== sequence || card.visualPlanetKey !== key) changed = true;
      card.visualPlanetSequence = sequence;
      card.visualPlanetKey = key;
    });
    return changed;
  }

  return Object.freeze({ PLANET_KEYS, shuffledRound, planetKeyForSequence, ensureAssignments, assignNext, rerollAssignments });
});
