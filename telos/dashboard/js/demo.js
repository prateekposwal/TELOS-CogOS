// TELOS Demo Data Generator Module — synthetic traces for standalone mode
var _isDemoMode = true;

// ─── Demo Data Generator (standalone mode when no server) ───
function generateDemoTraces() {
  const path = [
    { pos: [1, 0], di: 0.95, md: 0.5, terrain: 'plains', a2: [3, 0] },
    { pos: [2, 0], di: 0.88, md: 1.2, terrain: 'forest', a2: [3, 1] },
    { pos: [3, 0], di: 0.92, md: 0.8, terrain: 'plains', a2: [2, 2] },
    { pos: [4, 0], di: 0.97, md: 1.5, terrain: 'desert', a2: [2, 3] },
    { pos: [4, 1], di: 0.85, md: 2.1, terrain: 'forest', a2: [2, 4] },
    { pos: [4, 2], di: 0.90, md: 1.8, terrain: 'plains', a2: [3, 4] },
    { pos: [4, 3], di: 0.78, md: 3.2, terrain: 'mountain', a2: [4, 4] },
    { pos: [4, 4], di: 0.95, md: 0.3, terrain: 'plains', a2: [4, 4] },
  ];

  for (let i = 0; i < path.length; i++) {
    const p = path[i];
    const di = p.di || 0.9;
    const md = p.md || 1.0;
    const tt = p.terrain || 'plains';
    const score = 100 - (i * 1.5) + (i > 3 ? 5 : 0);  // time pressure + some rewards

    const trace = {
      cycle_id: i + 1,
      decision_integrity: di,
      mission_drift: md,
      world_state: [p.pos[0], p.pos[1]],
      agent2_pos: p.a2,
      agent2_reward: i > 2 && i < 6 ? +[5, 3, 2][i - 3] : 0,
      score: score,
      council_validated: true,
      firewall_blocked: false,
      council_signals: [
        { validator_name: 'Reality', passed: true },
        { validator_name: 'Constraint', passed: true },
        { validator_name: 'Memory Advisor', passed: true },
        { validator_name: 'Mission Drift', passed: md < 5.0 },
      ],
      stream_activations: [
        { name: 'Reflex', priority: +(0.3 + Math.random() * 0.3).toFixed(3) },
        { name: 'Perception', priority: +(0.5 + Math.random() * 0.3).toFixed(3) },
        { name: 'Memory', priority: +(0.4 + Math.random() * 0.3).toFixed(3) },
        { name: 'Planning', priority: +(0.6 + Math.random() * 0.3).toFixed(3) },
      ],
      phase_durations_ms: {
        perceive: 12 + Math.floor(Math.random() * 20),
        streams: 8 + Math.floor(Math.random() * 15),
        simulate: 45 + Math.floor(Math.random() * 60),
        evaluate: 15 + Math.floor(Math.random() * 25),
        synthesis: 10 + Math.floor(Math.random() * 20),
        select: 5 + Math.floor(Math.random() * 10),
        council: 20 + Math.floor(Math.random() * 30),
      },
      selected_intent: `Navigate to (${p.pos[0]},${p.pos[1]})`,
      strategic_options: [
        { intent_type: 'move right', score: 0.85 },
        { intent_type: 'move up', score: 0.72 },
        { intent_type: 'wait', score: 0.35 },
      ],
      worlds_simulated: 3 + Math.floor(Math.random() * 5),
      domain_facts: {
        metadata: {
          position: [p.pos[0], p.pos[1]],
          current_terrain: tt,
        }
      },
      blocking_validator: null,
      terrain_changes: i === 3 ? [{ x: 2, y: 0, old: 'forest', new: 'desert' }] : [],
    };
    applyTrace(trace);
  }
}

// ─── Debug console logger ───
var _dbg = function(msg) { console.log('[TELOS]', msg); try { var e = document.getElementById('debug-log'); if (e) e.textContent = msg; } catch(ex) {} };

// ─── Boot ───
_dbg('Starting demo mode...');
(function bootDemo() {
  _dbg('Demo mode active');
  document.getElementById('status-text').textContent = 'Demo Mode';
  generateDemoTraces();
})();
