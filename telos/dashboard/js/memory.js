// TELOS Memory Module — decision trace timeline

// ─── Memory Timeline ───
// TERRAIN_EMOJI is declared as `const` in gridworld.js (loaded before this
// file). Re-declaring it with `var` throws "already declared" and kills this
// script — reference the existing binding instead.
var _TERRAIN_EMOJI = { 'plains':'🌿', 'forest':'🌲', 'water':'🌊', 'desert':'🏜️', 'mountain':'⛰️' };

function renderMemoryTimeline() {
  const c = document.getElementById('memory-timeline');
  if (!c) return;
  const traces = state.traces;
  const recent = traces.slice(-20).reverse(); // newest first

  if (recent.length === 0) {
    c.innerHTML = '<div class="empty-state">No decision traces yet</div>';
    return;
  }

  c.innerHTML = recent.map((t) => {
    const approved = t.council_validated && !t.firewall_blocked;
    const di = t.decision_integrity || 1;
    const terrain = (t.domain_facts && t.domain_facts.metadata && t.domain_facts.metadata.current_terrain) || '';
    const terrainEmoji = (typeof TERRAIN_EMOJI !== 'undefined' ? TERRAIN_EMOJI : _TERRAIN_EMOJI)[terrain] || '';
    const intent = intentLabel(t);  // canonical extractor (intent.js) — selected_intent is a dict in real traces
    const cycleId = t.cycle_id != null ? t.cycle_id : '?';
    const diColor = di > 0.8 ? '#4ade80' : di > 0.5 ? '#fbbf24' : '#ff6b6b';
    const statusIcon = approved ? '✅' : '🚫';

    return `<div class="mem-node">
      <div class="mem-dot ${approved ? 'green' : 'red'}"></div>
      <div class="mem-content">
        <div class="mem-header">
          <span class="mem-cycle">C${cycleId}</span>
          <span class="mem-di" style="color:${diColor}">DI ${di.toFixed(3)}</span>
          <span class="mem-status">${statusIcon}</span>
        </div>
        <div class="mem-detail">
          <span class="mem-terrain">${terrainEmoji} ${terrain || '—'}</span>
          <span class="mem-intent" title="${intent}">${intent}</span>
        </div>
      </div>
    </div>`;
  }).join('');

  // Scroll to top (newest)
  c.scrollTop = 0;
}

// ─── Fullscreen for Memory ───
var _memoryFullscreen = false;
function toggleMemoryFullscreen() {
  _memoryFullscreen = !_memoryFullscreen;
  var mp = document.querySelector('.memory-panel');
  if (!mp) return;
  if (_memoryFullscreen) {
    mp.style.position = 'fixed'; mp.style.top = '0'; mp.style.left = '0';
    mp.style.width = '100vw'; mp.style.height = '100vh'; mp.style.zIndex = '1000';
    mp.style.margin = '0'; mp.style.borderRadius = '0';
  } else {
    mp.style.position = ''; mp.style.top = ''; mp.style.left = '';
    mp.style.width = ''; mp.style.height = ''; mp.style.zIndex = '';
    mp.style.margin = ''; mp.style.borderRadius = '';
  }
}
