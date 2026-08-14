// TELOS GridWorld Module — v5 "The Scanned Perimeter".
//
// The isometric game renderer is gone. In its place: a cinematic cartographic
// sonar of the REAL 5×5 territory — fog-of-war scanned from the agent's real
// position, visited cells as luminous map fragments, the real trail as a
// glowing filament with a traveling light pulse, reward cells as gold flares
// that spend down with REAL reward_collected/reward_available, and a coverage
// ring whose arc = REAL world_coverage.
//
// Honesty contract:
//   * Every pixel maps to a real field: state.terrain, state.position /
//     animPos / prevPos, state.visited, state.visitCounts, state.rewards,
//     state.goal, state.agent2Pos, terrain_changes, episodes, and the
//     /api/overview reward fractions. No fabricated cells, no random terrain.
//   * The scan sweep angle is tied to the REAL cycle count (golden-angle
//     step per cycle) — motion is a data clock, not decoration.
//   * Fog-of-war reveals only cells actually visited or within scan radius
//     of the real position (Manhattan ≤ 2, same honest rule as before).
//   * All motion is gated by window.__reducedMotion (one static frame).

// ─── The Scanned Perimeter — layout & projection (2D Cartesian) ───
const PERIM = {
  cell: 0, ox: 0, oy: 0, mapW: 0,
  zoom: 1, camX: 0, camY: 0,
};

function cellToScreen(x, y) {
  return {
    sx: PERIM.ox + x * PERIM.cell + PERIM.camX,
    sy: PERIM.oy + y * PERIM.cell + PERIM.camY,
  };
}

function screenToCell(mx, my) {
  const gx = Math.floor((mx - PERIM.ox - PERIM.camX) / PERIM.cell);
  const gy = Math.floor((my - PERIM.oy - PERIM.camY) / PERIM.cell);
  return [gx, gy];
}

// Kept name (dashboard.js hover handlers historically used it); maps to the
// perimeter projection so old call sites keep working unchanged.
function isoToScreen(x, y) { return cellToScreen(x, y); }
function screenToIso(mx, my) { return screenToCell(mx, my); }

function getTerrainAt(x, y) {
  const key = `${Math.round(x)},${Math.round(y)}`;
  return state.terrain[key] || 'plains';
}

// --- Pathfinding & Cost Helpers ---
function getTerrainCost(tt) {
  return TCOST[tt] || 1;
}

function computeShortestPath() {
  const { gridSize, goal, position, terrain, blocked } = state;
  const GX = goal[0], GY = goal[1];
  const SX = Math.round(position[0]), SY = Math.round(position[1]);
  if (SX === GX && SY === GY) return [[SX, SY]];
  const dist = {}, prev = {};
  const visited = new Set();
  const pq = [];
  for (let y = 0; y < gridSize; y++) {
    for (let x = 0; x < gridSize; x++) {
      dist[`${x},${y}`] = Infinity;
      prev[`${x},${y}`] = null;
    }
  }
  dist[`${SX},${SY}`] = 0;
  pq.push([0, SX, SY]);
  const dirs = [[1,0],[-1,0],[0,1],[0,-1]];
  while (pq.length > 0) {
    pq.sort((a, b) => a[0] - b[0]);
    const [d, cx, cy] = pq.shift();
    const ck = `${cx},${cy}`;
    if (visited.has(ck)) continue;
    visited.add(ck);
    if (cx === GX && cy === GY) break;
    for (const [dx, dy] of dirs) {
      const nx = cx + dx, ny = cy + dy;
      if (nx < 0 || nx >= gridSize || ny < 0 || ny >= gridSize) continue;
      const nk = `${nx},${ny}`;
      if (visited.has(nk)) continue;
      const ntt = terrain[nk] || 'plains';
      if (ntt === 'blocked') continue;
      const nd = d + getTerrainCost(ntt);
      if (nd < dist[nk]) {
        dist[nk] = nd;
        prev[nk] = [cx, cy];
        pq.push([nd, nx, ny]);
      }
    }
  }
  const path = [];
  let cx = GX, cy = GY;
  if (dist[`${cx},${cy}`] === Infinity) return [];
  while (prev[`${cx},${cy}`] !== null) {
    path.unshift([cx, cy]);
    [cx, cy] = prev[`${cx},${cy}`];
  }
  path.unshift([SX, SY]);
  return path;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

// ─── Semantic terrain palette (color = meaning, never rainbow) ───
const TERRAIN_SCAN = {
  'plains':   '#3f7d4a',
  'forest':   '#2a6b3a',
  'water':    '#2a6a9a',
  'desert':   '#c9a75a',
  'mountain': '#6a6a7a',
  'blocked':  '#8a3a3a',
};
const TERRAIN_LABEL = {
  'plains': 'PLAINS', 'forest': 'FOREST', 'water': 'WATER',
  'desert': 'DESERT', 'mountain': 'MOUNTAIN', 'blocked': 'BLOCKED',
};

// Real reward fractions from /api/overview (may be null — honest default).
function rewardFraction() {
  try {
    var ov = (typeof _lastOverview !== 'undefined' && _lastOverview) || null;
    if (ov && typeof ov.reward_available === 'number' && ov.reward_available > 0) {
      return Math.max(0, Math.min(1, ov.reward_collected / ov.reward_available));
    }
    if (ov && typeof ov.score_components === 'object' && ov.score_components &&
        typeof ov.score_components.reward_fraction === 'number') {
      return ov.score_components.reward_fraction;
    }
  } catch (e) {}
  return null;
}
function coverageFraction() {
  try {
    var ov = (typeof _lastOverview !== 'undefined' && _lastOverview) || null;
    if (ov && ov.score_components && typeof ov.score_components.world_coverage === 'number') {
      return ov.score_components.world_coverage;
    }
    if (ov && typeof ov.world_states === 'number' && state.gridSize) {
      return ov.world_states / (state.gridSize * state.gridSize);
    }
  } catch (e) {}
  return null;
}

// ─── The Scanned Perimeter — main draw ───
function drawGrid3D(canvas) {
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  const gs = state.gridSize || 5;

  // Layout: centered square map with headroom for the readout strip.
  const mapArea = Math.min(w * 0.86, h * 0.74);
  PERIM.cell = mapArea / gs;
  PERIM.ox = (w - mapArea) / 2 + PERIM.cell / 2;
  PERIM.oy = (h - mapArea) / 2 + PERIM.cell / 2 + 10;
  const cell = PERIM.cell;
  const reduced = !!(window.__reducedMotion);
  const t = reduced ? 0 : state.time;

  // ── Night sky + hairline grid ──
  const sky = ctx.createRadialGradient(w / 2, h * 0.34, 10, w / 2, h * 0.34, Math.max(w, h) * 0.75);
  sky.addColorStop(0, '#181234');
  sky.addColorStop(0.55, '#0d0a1a');
  sky.addColorStop(1, '#070512');
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, w, h);

  ctx.strokeStyle = 'rgba(34,28,68,0.5)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let gx = 0; gx <= w; gx += 72) { ctx.moveTo(gx + 0.5, 0); ctx.lineTo(gx + 0.5, h); }
  for (let gy = 0; gy <= h; gy += 72) { ctx.moveTo(0, gy + 0.5); ctx.lineTo(w, gy + 0.5); }
  ctx.stroke();

  // Header: chapter line (mono, editorial).
  ctx.fillStyle = 'rgba(241,239,248,0.85)';
  ctx.font = '13px "Space Mono", monospace';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillText('THE SCANNED PERIMETER — territory as it is actually mapped', 14, 12);
  ctx.textAlign = 'center';

  // ── Real signal readouts (mono, all real fields) ──
  const mapped = state.visited.length;
  const cov = coverageFraction();
  const rewFrac = rewardFraction();
  const modeBit = state.metaMode ? state.metaMode : '—';
  const epSteps = (typeof _lastOverview !== 'undefined' && _lastOverview && _lastOverview.episodes)
    ? (_lastOverview.episodes.current_steps || 0) : (state.traces.length || 0);

  // Agent + scan geometry.
  const agentX = Math.round(state.animPos[0]), agentY = Math.round(state.animPos[1]);
  const scanRadius = 2;   // honest fog rule: Manhattan ≤ 2 of real position

  function revealed(x, y) {
    const vk = `${x},${y}`;
    if (state.visitCounts && state.visitCounts[vk] > 0) return true;
    const d = Math.abs(x - agentX) + Math.abs(y - agentY);
    return d <= scanRadius;
  }

  // ── Cells: unrevealed = dark abyss, revealed = terrain fragments ──
  for (let y = 0; y < gs; y++) {
    for (let x = 0; x < gs; x++) {
      const p = cellToScreen(x, y);
      const tt = getTerrainAt(x, y);
      const vis = revealed(x, y);
      const px = p.sx - cell / 2, py = p.sy - cell / 2;

      if (!vis) {
        ctx.fillStyle = 'rgba(7,5,18,0.82)';
        ctx.fillRect(px + 1, py + 1, cell - 2, cell - 2);
        ctx.strokeStyle = 'rgba(34,28,68,0.4)';
        ctx.strokeRect(px + 1, py + 1, cell - 2, cell - 2);
        if (x === agentX && y === agentY) {
          ctx.fillStyle = 'rgba(143,137,173,0.7)';
          ctx.font = '13px "Space Mono", monospace';
          ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          ctx.fillText('?', p.sx, p.sy);
        }
        continue;
      }

      const col = TERRAIN_SCAN[tt] || '#3f7d4a';
      const vk = `${x},${y}`;
      const visits = state.visitCounts[vk] || 0;
      const isB = tt === 'blocked';

      // Terrain fragment (soft, with an inner glow for visited cells).
      ctx.fillStyle = col;
      ctx.globalAlpha = isB ? 0.55 : 0.42;
      ctx.fillRect(px + 1, py + 1, cell - 2, cell - 2);
      ctx.globalAlpha = 1;
      if (visits > 0) {
        const g = ctx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, cell * 0.7);
        g.addColorStop(0, col + '44');
        g.addColorStop(1, 'transparent');
        ctx.fillStyle = g;
        ctx.fillRect(px, py, cell, cell);
      }
      // Hairline cell edge.
      ctx.strokeStyle = 'rgba(255,255,255,0.07)';
      ctx.lineWidth = 1;
      ctx.strokeRect(px + 0.5, py + 0.5, cell - 1, cell - 1);

      // Blocked cells: cross-hatch (real, cannot be crossed).
      if (isB) {
        ctx.strokeStyle = 'rgba(255,90,90,0.35)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(px + 4, py + 4); ctx.lineTo(px + cell - 4, py + cell - 4);
        ctx.moveTo(px + cell - 4, py + 4); ctx.lineTo(px + 4, py + cell - 4);
        ctx.stroke();
      }

      // ── Overlay modes (existing toggles, honest data) ──
      if (state.omegaHeatmap) {
        // Uncertainty: real distance-to-agent + unvisited (existing derivation).
        const dx = x - agentX, dy = y - agentY;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const maxDist = gs * 1.5;
        let oc;
        if (isB) oc = 'rgba(40,20,20,0.55)';
        else if (visits === 0) {
          const intensity = Math.max(0.2, Math.min(1.0, 1.0 - dist / maxDist));
          oc = `rgba(40, 100, 255, ${0.25 + intensity * 0.4})`;
        } else if (dist < 1.5) {
          oc = `rgba(74, 222, 128, ${(1.0 - dist * 0.5) * 0.3})`;
        } else {
          oc = 'rgba(100, 100, 120, 0.12)';
        }
        ctx.fillStyle = oc;
        ctx.fillRect(px + 1, py + 1, cell - 2, cell - 2);
        ctx.fillStyle = 'rgba(255,255,255,0.75)';
        ctx.font = '13px "Space Mono", monospace';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        const omegaVal = isB ? 0.9 : visits === 0 ? Math.max(0.3, 1.0 - dist / maxDist) : 0.1;
        ctx.fillText('Ω:' + omegaVal.toFixed(1), p.sx, p.sy);
      } else if (state.heatMode) {
        // Visit heat: intensity = REAL visit count.
        const heatA = visits === 0 ? 0.0 : Math.min(0.75, 0.15 + visits * 0.12);
        if (heatA > 0) {
          const hg = ctx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, cell * 0.6);
          hg.addColorStop(0, `rgba(255,150,90,${heatA})`);
          hg.addColorStop(1, 'transparent');
          ctx.fillStyle = hg;
          ctx.fillRect(px, py, cell, cell);
        }
        ctx.fillStyle = visits > 0 ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.35)';
        ctx.font = '13px "Space Mono", monospace';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(String(visits), p.sx, p.sy);
      } else if (state.showCosts) {
        ctx.fillStyle = 'rgba(255,255,255,0.85)';
        ctx.font = '13px "Space Mono", monospace';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText('×' + getTerrainCost(tt), p.sx, p.sy);
      }

      // Terrain micro-label on unvisited-but-scanned cells (readability).
      if (visits === 0 && !state.heatMode && !state.showCosts && !state.omegaHeatmap) {
        ctx.fillStyle = 'rgba(255,255,255,0.35)';
        ctx.font = '13px "Space Mono", monospace';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(TERRAIN_LABEL[tt], p.sx, p.sy);
      }

      // Terrain change flash (REAL event from terrain_changes).
      if (state.terrainFlash && state.terrainFlash[`${x},${y}`]) {
        const fl = state.terrainFlash[`${x},${y}`];
        const elapsed = state.time - fl.start;
        if (elapsed < 2.0) {
          const intensity = Math.max(0, 1.0 - elapsed / 2.0);
          ctx.fillStyle = `rgba(255,200,100,${intensity * 0.35})`;
          ctx.fillRect(px, py, cell, cell);
          ctx.strokeStyle = `rgba(255,200,100,${intensity * 0.8})`;
          ctx.strokeRect(px + 0.5, py + 0.5, cell - 1, cell - 1);
        } else {
          delete state.terrainFlash[`${x},${y}`];
        }
      }
    }
  }

  // ── Reward cells: gold flares that spend down (REAL ratio) ──
  const rFrac = rewFrac === null ? 0.5 : rewFrac;   // unknown → mid (honest default)
  for (const rk in (state.rewards || {})) {
    const val = state.rewards[rk];
    if (!val || val <= 0) continue;
    const parts = rk.split(',').map(Number);
    if (parts.length !== 2) continue;
    const p = cellToScreen(parts[0], parts[1]);
    const left = 1 - rFrac;   // remaining world value fraction
    const pulse = reduced ? 1 : 0.7 + Math.sin(t * 2.5 + parts[0] + parts[1]) * 0.3;
    const alpha = (0.25 + left * 0.55) * pulse;
    const g = ctx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, cell * 0.55);
    g.addColorStop(0, `rgba(250,204,21,${alpha})`);
    g.addColorStop(1, 'transparent');
    ctx.fillStyle = g;
    ctx.fillRect(p.sx - cell * 0.55, p.sy - cell * 0.55, cell * 1.1, cell * 1.1);
    ctx.fillStyle = `rgba(255,235,150,${0.5 + left * 0.5})`;
    ctx.font = '13px "Space Mono", monospace';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('+' + val, p.sx, p.sy - 2);
  }

  // ── Trail: the REAL visited path as a luminous filament ──
  if (state.visited.length > 1) {
    ctx.save();
    ctx.lineCap = 'round';
    // Underlay glow pass.
    ctx.strokeStyle = 'rgba(255,107,107,0.10)';
    ctx.lineWidth = cell * 0.28;
    ctx.beginPath();
    for (let i = 0; i < state.visited.length; i++) {
      const p = cellToScreen(state.visited[i][0], state.visited[i][1]);
      if (i === 0) ctx.moveTo(p.sx, p.sy);
      else ctx.lineTo(p.sx, p.sy);
    }
    ctx.stroke();
    // Core filament.
    ctx.strokeStyle = 'rgba(255,107,107,0.55)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < state.visited.length; i++) {
      const p = cellToScreen(state.visited[i][0], state.visited[i][1]);
      if (i === 0) ctx.moveTo(p.sx, p.sy);
      else ctx.lineTo(p.sx, p.sy);
    }
    ctx.stroke();
    // Traveling light pulse between the last two real positions.
    const last = state.visited[state.visited.length - 1];
    const prev = state.visited.length > 1 ? state.visited[state.visited.length - 2] : last;
    const e = 1 - Math.pow(1 - state.animT, 3);
    const px = prev[0] + (last[0] - prev[0]) * e;
    const py = prev[1] + (last[1] - prev[1]) * e;
    const pp = cellToScreen(px, py);
    const pr = reduced ? 5 : 4 + Math.sin(t * 4) * 1.5;
    const pg = ctx.createRadialGradient(pp.sx, pp.sy, 0, pp.sx, pp.sy, pr * 4);
    pg.addColorStop(0, 'rgba(255,150,150,0.5)');
    pg.addColorStop(1, 'transparent');
    ctx.fillStyle = pg;
    ctx.beginPath(); ctx.arc(pp.sx, pp.sy, pr * 4, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#ffb4b4';
    ctx.beginPath(); ctx.arc(pp.sx, pp.sy, pr, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  // ── Shortest path overlay (real Dijkstra on real terrain) ──
  if (state.shortestPath && state.shortestPath.length > 1 && !state.heatMode && !state.omegaHeatmap) {
    ctx.setLineDash([5, 5]);
    ctx.strokeStyle = 'rgba(74,222,128,0.55)';
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    for (let i = 0; i < state.shortestPath.length; i++) {
      const p = cellToScreen(state.shortestPath[i][0], state.shortestPath[i][1]);
      if (i === 0) ctx.moveTo(p.sx, p.sy);
      else ctx.lineTo(p.sx, p.sy);
    }
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // ── Alternative-path ghosts (REAL strategic_options directions) ──
  for (let ai = 0; ai < Math.min(state.altPaths.length, 3); ai++) {
    const alt = state.altPaths[ai];
    if (!alt || alt.length < 2) continue;
    const a = cellToScreen(alt[0][0], alt[0][1]);
    const b = cellToScreen(alt[1][0], alt[1][1]);
    const pulse = reduced ? 0.5 : 0.3 + Math.sin(t * 2 + ai) * 0.15;
    ctx.strokeStyle = `rgba(100,180,255,${pulse * 0.5})`;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([3, 5]);
    ctx.beginPath();
    ctx.moveTo(a.sx, a.sy);
    ctx.lineTo(b.sx, b.sy);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = `rgba(100,180,255,${pulse * 0.8})`;
    ctx.beginPath();
    ctx.arc(b.sx, b.sy, 3.5, 0, Math.PI * 2);
    ctx.fill();
  }

  // ── Goal crosshair (real goal) ──
  const gp = cellToScreen(state.goal[0], state.goal[1]);
  const goalPulse = reduced ? 0.85 : 0.6 + Math.sin(t * 2.2) * 0.25;
  const gs2 = cell * 0.30;
  ctx.strokeStyle = `rgba(250,204,21,${goalPulse * 0.8})`;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(gp.sx - gs2, gp.sy); ctx.lineTo(gp.sx + gs2, gp.sy);
  ctx.moveTo(gp.sx, gp.sy - gs2); ctx.lineTo(gp.sx, gp.sy + gs2);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(gp.sx, gp.sy, cell * 0.16, 0, Math.PI * 2);
  ctx.stroke();
  ctx.fillStyle = `rgba(250,204,21,${goalPulse})`;
  ctx.font = '13px "Space Mono", monospace';
  ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
  ctx.fillText('GOAL', gp.sx, gp.sy - gs2 - 3);

  // ── Coverage ring: arc = REAL world coverage ──
  const covF = cov === null ? (mapped / (gs * gs)) : cov;
  const ringR = mapArea * 0.62;
  const ringCx = w / 2, ringCy = PERIM.oy + (mapArea / 2) * 0.5 - 6;
  ctx.strokeStyle = 'rgba(125,151,255,0.22)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(ringCx, ringCy, ringR, 0, Math.PI * 2);
  ctx.stroke();
  ctx.strokeStyle = 'rgba(125,151,255,0.9)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(ringCx, ringCy, ringR, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.max(0.01, Math.min(1, covF)));
  ctx.stroke();
  ctx.fillStyle = 'rgba(125,151,255,0.95)';
  ctx.font = '13px "Space Mono", monospace';
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  ctx.fillText('MAPPED ' + mapped + '/' + (gs * gs) + ' · ' + Math.round(covF * 100) + '%', ringCx, ringCy + ringR + 8);

  // ── Scan sweep: a luminous radius rotating with the REAL cycle count ──
  if (!reduced) {
    const cycles = Math.max(1, state.traces.length || 1);
    const sweepA = ((cycles * 2.39996323) + t * 0.4) % (Math.PI * 2);  // golden-angle per real cycle
    const ap = cellToScreen(agentX, agentY);
    const sweepLen = mapArea * 0.85;
    const sx2 = ap.sx + Math.cos(sweepA) * sweepLen;
    const sy2 = ap.sy + Math.sin(sweepA) * sweepLen;
    const sg = ctx.createLinearGradient(ap.sx, ap.sy, sx2, sy2);
    sg.addColorStop(0, 'rgba(125,151,255,0.16)');
    sg.addColorStop(1, 'rgba(125,151,255,0.02)');
    ctx.strokeStyle = sg;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(ap.sx, ap.sy);
    ctx.lineTo(sx2, sy2);
    ctx.stroke();
  }

  // ── Beacons: TELOS (pink) + Agent2 (blue), REAL positions ──
  drawTELOS(ctx, cellToScreen(state.animPos[0], state.animPos[1]));
  drawAgent2(ctx);

  // ── Particles (existing living-dust; floats only over revealed cells) ──
  drawParticles(ctx);

  // ── Bottom readout strip (mono, all real fields) ──
  const rewTxt = rewFrac === null ? '—/—' : Math.round(rewFrac * 100) + '%';
  ctx.fillStyle = 'rgba(143,137,173,0.9)';
  ctx.font = '13px "Space Mono", monospace';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'bottom';
  const strip = 'CELLS MAPPED ' + mapped + '/' + (gs * gs) +
    ' · VALUE ' + rewTxt +
    ' · GOALS ' + ((typeof _lastOverview !== 'undefined' && _lastOverview && _lastOverview.episodes) ? (_lastOverview.episodes.completed || 0) : 0) +
    ' · STEP ' + epSteps +
    ' · MODE ' + modeBit;
  ctx.fillText(strip, 14, h - 10);

  // ── Terrain legend (real terrain types present in the map) ──
  const present = {};
  for (let y = 0; y < gs; y++) for (let x = 0; x < gs; x++) present[getTerrainAt(x, y)] = true;
  const keys = Object.keys(present).sort();
  let lx = 14, ly = 40;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  for (const k of keys) {
    ctx.fillStyle = TERRAIN_SCAN[k] || '#3f7d4a';
    ctx.fillRect(lx, ly + 1, 10, 10);
    ctx.strokeStyle = 'rgba(255,255,255,0.2)';
    ctx.strokeRect(lx + 0.5, ly + 1.5, 10, 10);
    ctx.fillStyle = 'rgba(200,198,222,0.75)';
    ctx.font = '13px "Space Mono", monospace';
    ctx.fillText(TERRAIN_LABEL[k], lx + 15, ly);
    lx += 15 + ctx.measureText(TERRAIN_LABEL[k]).width + 14;
  }

  // ── Hover tooltip (dashboard.js sets state.hoveredCell/hoverPos) ──
  if (state.hoveredCell && state.hoverPos) {
    const [hx, hy] = state.hoveredCell;
    const ttt = getTerrainAt(hx, hy);
    const cost = getTerrainCost(ttt);
    const vk = `${hx},${hy}`;
    const visits = state.visitCounts[vk] || 0;
    const lines = [
      TERRAIN_LABEL[ttt] + ' · ×' + cost,
      visits + ' visit' + (visits === 1 ? '' : 's') + (visits > 0 ? ' — mapped' : ' — scanned only'),
    ];
    const panelW = 200, lineH = 20, titleH = 20;
    const panelH = titleH + lines.length * lineH + 12;
    let px = state.hoverPos.sx + 18, py = state.hoverPos.sy - panelH / 2;
    if (px + panelW > w) px = state.hoverPos.sx - panelW - 18;
    if (py < 6) py = 6;
    if (py + panelH > h - 6) py = h - panelH - 6;
    ctx.save();
    ctx.shadowColor = 'rgba(0,0,0,0.6)';
    ctx.shadowBlur = 16;
    ctx.fillStyle = 'rgba(10,10,22,0.94)';
    ctx.strokeStyle = 'rgba(125,151,255,0.3)';
    ctx.lineWidth = 1;
    roundRect(ctx, px, py, panelW, panelH, 10);
    ctx.fill();
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.fillStyle = '#e0e0e0';
    ctx.font = 'bold 13px "Space Mono", monospace';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(`CELL (${hx},${hy})`, px + 12, py + 7);
    ctx.fillStyle = 'rgba(255,255,255,0.06)';
    ctx.fillRect(px + 12, py + titleH + 2, panelW - 24, 1);
    for (let i = 0; i < lines.length; i++) {
      ctx.fillStyle = i === 0 ? '#b0b0b0' : 'rgba(143,137,173,0.95)';
      ctx.font = '13px "Space Mono", monospace';
      ctx.fillText(lines[i], px + 12, py + titleH + 10 + i * lineH);
    }
    ctx.restore();
  }
}

// ─── TELOS beacon (pink; REAL position) ───
function drawTELOS(ctx, p) {
  const reduced = !!(window.__reducedMotion);
  const t = reduced ? 0 : state.time;
  const pulse = reduced ? 0.9 : 0.7 + Math.sin(t * 2.6) * 0.3;
  const r = Math.max(6, PERIM.cell * 0.20);
  const g = ctx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, r * 4);
  g.addColorStop(0, `rgba(255,107,107,${pulse * 0.35})`);
  g.addColorStop(1, 'transparent');
  ctx.fillStyle = g;
  ctx.beginPath(); ctx.arc(p.sx, p.sy, r * 4, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#ff6b6b';
  ctx.beginPath(); ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.85)';
  ctx.beginPath(); ctx.arc(p.sx - r * 0.25, p.sy - r * 0.25, r * 0.35, 0, Math.PI * 2); ctx.fill();
  // Sonar rings from the beacon (geometry only).
  ctx.strokeStyle = `rgba(255,107,107,${pulse * 0.3})`;
  ctx.lineWidth = 1;
  for (let i = 1; i <= 2; i++) {
    const rr = r * (2.2 + i * 1.3) + (reduced ? 0 : Math.sin(t * 1.8 + i) * 3);
    ctx.beginPath(); ctx.arc(p.sx, p.sy, rr, 0, Math.PI * 2); ctx.stroke();
  }
  ctx.fillStyle = 'rgba(255,200,200,0.85)';
  ctx.font = '13px "Space Mono", monospace';
  ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
  ctx.fillText('TELOS', p.sx, p.sy - r - 4);
}

// ─── Agent2 beacon (blue; REAL position) ───
function drawAgent2(ctx) {
  if (!state.agent2Pos) return;
  const p = cellToScreen(state.agent2Pos[0], state.agent2Pos[1]);
  const reduced = !!(window.__reducedMotion);
  const t = reduced ? 0 : state.time;
  const pulse = reduced ? 0.9 : 0.7 + Math.sin(t * 2.6 + 1.5) * 0.3;
  const r = Math.max(5, PERIM.cell * 0.17);
  const g = ctx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, r * 3.5);
  g.addColorStop(0, `rgba(96,165,250,${pulse * 0.32})`);
  g.addColorStop(1, 'transparent');
  ctx.fillStyle = g;
  ctx.beginPath(); ctx.arc(p.sx, p.sy, r * 3.5, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#60a5fa';
  ctx.beginPath(); ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.7)';
  ctx.beginPath(); ctx.arc(p.sx - r * 0.25, p.sy - r * 0.25, r * 0.3, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = 'rgba(170,210,255,0.8)';
  ctx.font = '13px "Space Mono", monospace';
  ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
  ctx.fillText('AGENT2', p.sx, p.sy - r - 3);
}

// ─── Goal marker kept for API parity (crosshair drawn inline in main pass) ───
function drawGoalMarker(ctx, cx, cy) {
  const gs2 = PERIM.cell * 0.30;
  ctx.strokeStyle = 'rgba(250,204,21,0.8)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(cx - gs2, cy); ctx.lineTo(cx + gs2, cy);
  ctx.moveTo(cx, cy - gs2); ctx.lineTo(cx, cy + gs2);
  ctx.stroke();
}

// ─── Particle system (living dust over revealed terrain only) ───
function spawnParticles() {
  if (window.__reducedMotion) return;
  if (state.particles.length < 40 && Math.random() < 0.3) {
    const x = Math.round(Math.random() * (state.gridSize - 1));
    const y = Math.round(Math.random() * (state.gridSize - 1));
    const tt = getTerrainAt(x, y);
    if (tt !== 'blocked' && tt !== 'water') {
      state.particles.push({
        x, y,
        life: 0.8 + Math.random() * 0.4,
        speed: 0.2 + Math.random() * 0.4,
        drift: (Math.random() - 0.5) * 0.3,
        size: 1 + Math.random() * 2,
        hue: tt === 'forest' ? 120 : tt === 'desert' ? 40 : 80,
      });
    }
  }
}

function drawParticles(ctx) {
  if (window.__reducedMotion) return;
  for (let i = state.particles.length - 1; i >= 0; i--) {
    const p = state.particles[i];
    p.life -= 0.005 * p.speed;
    if (p.life <= 0) { state.particles.splice(i, 1); continue; }
    const { sx, sy } = cellToScreen(p.x, p.y);
    const floatUp = (1 - p.life) * 22;
    const px = sx + Math.sin(state.time * 0.5 + p.x * 3) * 3;
    const py = sy - floatUp;
    const grad = ctx.createRadialGradient(px, py, 0, px, py, p.size * 2);
    grad.addColorStop(0, `hsla(${p.hue},80%,70%,${p.life * 0.4})`);
    grad.addColorStop(1, `hsla(${p.hue},80%,70%,0)`);
    ctx.fillStyle = grad;
    ctx.beginPath(); ctx.arc(px, py, p.size * 2, 0, Math.PI * 2); ctx.fill();
  }
}

function renderGrid() { const c = document.getElementById('grid-canvas'); if (c) drawGrid3D(c); }

// Kept for memory.js fallback (const TERRAIN_EMOJI referenced there).
const TERRAIN_EMOJI = { 'plains':'🌿', 'forest':'🌲', 'water':'🌊', 'desert':'🏜️', 'mountain':'⛰️' };

function toggleCostView() {
  state.showCosts = !state.showCosts;
  state.heatMode = false;
  state.omegaHeatmap = false;
  const b = document.getElementById('btn-cost-view');
  if (b) b.className = state.showCosts ? 'active' : '';
  const h = document.getElementById('btn-heat-mode');
  if (h) h.className = '';
  const o = document.getElementById('btn-omega-heat');
  if (o) o.className = '';
  state.shortestPath = computeShortestPath();
}

function toggleHeatMode() {
  state.heatMode = !state.heatMode;
  state.showCosts = false;
  state.omegaHeatmap = false;
  const h = document.getElementById('btn-heat-mode');
  if (h) h.className = state.heatMode ? 'active' : '';
  const b = document.getElementById('btn-cost-view');
  if (b) b.className = '';
  const o = document.getElementById('btn-omega-heat');
  if (o) o.className = '';
}

function toggleOmegaHeatmap() {
  state.omegaHeatmap = !state.omegaHeatmap;
  state.showCosts = false;
  state.heatMode = false;
  const o = document.getElementById('btn-omega-heat');
  if (o) o.className = state.omegaHeatmap ? 'active' : '';
  const b = document.getElementById('btn-cost-view');
  if (b) b.className = '';
  const h = document.getElementById('btn-heat-mode');
  if (h) h.className = '';
}
