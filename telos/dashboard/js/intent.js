// TELOS Canonical Intent Extractor — the ONE function that turns a trace's
// intent into a display string.
//
// Why this exists (root-cause pattern: "untyped dict rendered into DOM —
// assume string, get object"): real decision traces carry `selected_intent`
// as a dict {type, confidence}, NOT a plain string. Interpolating the raw
// field into innerHTML renders "[object Object]" — exactly what the Memory
// timeline showed. Every render site (memory.js, story.js, ...) MUST route
// intent through intentLabel(); this file is the single canonical source.
//
// Structural rule: never interpolate a raw trace field into the DOM — route
// every object-valued field through a strict accessor like intentLabel().
function intentLabel(t) {
  if (!t || typeof t !== 'object') return '—';
  var si = t.selected_intent;
  if (si && typeof si === 'object') {
    if (typeof si.type === 'string' && si.type) return si.type;
    if (typeof si.intent_type === 'string' && si.intent_type) return si.intent_type;
    if (typeof si.intent === 'string' && si.intent) return si.intent;
  } else if (typeof si === 'string' && si) {
    return si;
  }
  if (typeof t.intent_type === 'string' && t.intent_type) return t.intent_type;
  var so = t.strategic_options;
  if (Array.isArray(so) && so.length > 0 && so[0] && typeof so[0] === 'object') {
    if (typeof so[0].intent_type === 'string' && so[0].intent_type) return so[0].intent_type;
    if (typeof so[0].type === 'string' && so[0].type) return so[0].type;
  }
  return '—';
}
