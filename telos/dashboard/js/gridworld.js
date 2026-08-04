// TELOS GridWorld Module — 3D Isometric terrain, agents, pathfinding

// ─── 3D Isometric Parameters (unique to this module) ───
const ISO = {
  tw: 164, th: 82, hs: 26,
  ox: 550, oy: 420,
  zoom: 1,
  rotY: -0.6,
  rotX: -0.4,
  camX: 0, camY: 0,
  isDragging: false,
  lastMX: 0, lastMY: 0,
};

// ─── 3D Rotation Helpers ───
function isoToScreen(x, y, h) {
  const cx = x - 2, cy = y - 2, cz = (h || 0) * 0.2;
  const cY = Math.cos(ISO.rotY), sY = Math.sin(ISO.rotY);
  const cX = Math.cos(ISO.rotX), sX = Math.sin(ISO.rotX);
  const rx = cx * cY - cz * sY;
  const rz = cx * sY + cz * cY;
  const ry = cy * cX - rz * sX;
  const rz2 = cy * sX + rz * cX;
  const sc = ISO.zoom * ISO.tw / 2;
  return {
    sx: ISO.ox + ISO.camX + rx * sc,
    sy: ISO.oy + ISO.camY - ry * sc * 0.7 + rz2 * sc * 0.35,
  };
}

function screenToIso(mx, my) {
  const sc = ISO.zoom * ISO.tw / 2;
  const dx = (mx - ISO.ox - ISO.camX) / sc;
  const dy = (my - ISO.oy - ISO.camY) / sc;
  const cY = Math.cos(ISO.rotY), sY = Math.sin(ISO.rotY);
  const cX = Math.cos(ISO.rotX), sX = Math.sin(ISO.rotX);
  const det = cY * cX;
  if (Math.abs(det) < 0.01) return [2, 2];
  const rx = (dx * cX + dy * sY * sX) / det;
  const ry = (dy * cY) / det;
  return [rx + 2, ry + 2];
}

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


// ─── 3D Block Drawing ───
function drawBlock3D(ctx, cx, cy, hPx, colors, breath, opts) {
  // cx, cy = center of the block's base at ground level
  // hPx = height in pixels (positive = raised, negative = recessed)
  // breath = breathing oscillation
  
  const { tw, th } = ISO;
  const b = breath * ISO.zoom;
  
  // Determine top surface position and wall extent
  // For positive height: top surface is ABOVE ground (lower Y on canvas)
  // For negative height: top surface is BELOW ground (higher Y on canvas)
  const topY = hPx >= 0 ? cy - hPx + b : cy + b;         // upper Y (higher visual)
  const botY = hPx >= 0 ? cy + b : cy - hPx + b;         // lower Y (lower visual)
  
  // Diamond corners at top surface
  const nTop = { x: cx, y: topY - th / 2 };
  const eTop = { x: cx + tw / 2, y: topY };
  const sTop = { x: cx, y: topY + th / 2 };
  const wTop = { x: cx - tw / 2, y: topY };
  
  // Diamond corners at base (ground)
  const nBot = { x: cx, y: botY - th / 2 };
  const eBot = { x: cx + tw / 2, y: botY };
  const sBot = { x: cx, y: botY + th / 2 };
  const wBot = { x: cx - tw / 2, y: botY };
  
  // === Draw shadow (for raised blocks) ===
  if (hPx > 3) {
    const shadowOff = 6 + hPx * 0.08;
    ctx.beginPath();
    ctx.moveTo(cx + shadowOff, cy + shadowOff - th / 2);
    ctx.lineTo(cx + tw / 2 + shadowOff, cy + shadowOff);
    ctx.lineTo(cx + shadowOff, cy + shadowOff + th / 2);
    ctx.lineTo(cx - tw / 2 + shadowOff, cy + shadowOff);
    ctx.closePath();
    ctx.fillStyle = 'rgba(0,0,0,0.2)';
    ctx.fill();
  }
  
  // === Left wall (front-left face) ===
  const useForNegative = hPx < 0;
  if (hPx !== 0) {
    ctx.beginPath();
    if (hPx > 0) {
      // Raised: walls from top surface DOWN to ground
      ctx.moveTo(wTop.x, wTop.y);      // top-left corner of top surface
      ctx.lineTo(sTop.x, sTop.y);      // bottom corner of top surface
      ctx.lineTo(sBot.x, sBot.y);      // bottom corner at ground
      ctx.lineTo(wBot.x, wBot.y);      // left corner at ground
    } else {
      // Recessed: walls from ground DOWN to top surface
      ctx.moveTo(wBot.x, wBot.y);      // left corner at ground
      ctx.lineTo(sBot.x, sBot.y);      // bottom corner at ground
      ctx.lineTo(sTop.x, sTop.y);      // bottom corner of top surface
      ctx.lineTo(wTop.x, wTop.y);      // left corner of top surface
    }
    ctx.closePath();
    ctx.fillStyle = colors.left;
    ctx.fill();
    ctx.strokeStyle = 'rgba(0,0,0,0.12)';
    ctx.lineWidth = 0.5;
    ctx.stroke();
  }
  
  // === Right wall (front-right face) ===
  if (hPx !== 0) {
    ctx.beginPath();
    if (hPx > 0) {
      ctx.moveTo(sTop.x, sTop.y);
      ctx.lineTo(eTop.x, eTop.y);
      ctx.lineTo(eBot.x, eBot.y);
      ctx.lineTo(sBot.x, sBot.y);
    } else {
      ctx.moveTo(sBot.x, sBot.y);
      ctx.lineTo(eBot.x, eBot.y);
      ctx.lineTo(eTop.x, eTop.y);
      ctx.lineTo(sTop.x, sTop.y);
    }
    ctx.closePath();
    ctx.fillStyle = colors.right;
    ctx.fill();
    ctx.strokeStyle = 'rgba(0,0,0,0.12)';
    ctx.lineWidth = 0.5;
    ctx.stroke();
  }
  
  // === Top (or water) surface ===
  ctx.beginPath();
  ctx.moveTo(nTop.x, nTop.y);
  ctx.lineTo(eTop.x, eTop.y);
  ctx.lineTo(sTop.x, sTop.y);
  ctx.lineTo(wTop.x, wTop.y);
  ctx.closePath();
  
  // Determine surface color (water gets animated color)
  if (opts && opts.tt === 'water') {
    const wave = Math.sin(state.time * 2 + cx * 0.05 + cy * 0.08) * 8;
    const r = 26 + wave, g = 90 + wave * 0.5, b2 = 154 + wave * 0.3;
    ctx.fillStyle = `rgb(${Math.min(60,r)},${Math.min(120,g)},${Math.min(200,b2)})`;
  } else {
    ctx.fillStyle = colors.top;
  }
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,255,255,0.07)';
  ctx.lineWidth = 0.5;
  ctx.stroke();
}

// ─── Terrain Features ───
function drawTerrainFeature(ctx, cx, cy, hPx, tt, breath) {
  const { tw, th } = ISO;
  const topY = hPx >= 0 ? cy - hPx + breath : cy + breath;
  const b = breath;
  
  // Clip to top face diamond
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(cx, topY - th / 2);
  ctx.lineTo(cx + tw / 2, topY);
  ctx.lineTo(cx, topY + th / 2);
  ctx.lineTo(cx - tw / 2, topY);
  ctx.closePath();
  ctx.clip();
  
  switch (tt) {
    case 'plains': {
      // Subtle grass texture lines
      ctx.strokeStyle = 'rgba(90,154,74,0.15)';
      ctx.lineWidth = 0.5;
      for (let i = -2; i <= 2; i += 0.5) {
        const lx = cx + i * 8 + Math.sin(state.time * 0.5 + i) * 1;
        const ly = topY + i * 4;
        ctx.beginPath();
        ctx.moveTo(lx - 4, ly);
        ctx.lineTo(lx + 4, ly + 6);
        ctx.stroke();
      }
      break;
    }
    case 'forest': {
      // Draw 3 small tree triangles
      const treePos = [[-12, -4], [8, -6], [-2, -10]];
      for (const tp of treePos) {
        const sway = Math.sin(state.time * 1.2 + tp[0] * 0.1) * 1.5;
        const tx = cx + tp[0] + sway;
        const ty = topY + tp[1] - 5;
        // Tree trunk
        ctx.fillStyle = '#3a2a1a';
        ctx.fillRect(tx - 1.5, ty + 2, 3, 8);
        // Tree canopy (triangle)
        ctx.beginPath();
        ctx.moveTo(tx, ty - 8);
        ctx.lineTo(tx - 8, ty + 4);
        ctx.lineTo(tx + 8, ty + 4);
        ctx.closePath();
        ctx.fillStyle = '#0d5a1a';
        ctx.fill();
        ctx.strokeStyle = 'rgba(0,0,0,0.15)';
        ctx.lineWidth = 0.5;
        ctx.stroke();
      }
      break;
    }
    case 'water': {
      // Animated wave lines
      const wavePhase = state.time * 2;
      ctx.strokeStyle = 'rgba(100,180,255,0.3)';
      ctx.lineWidth = 1;
      for (let i = -2; i <= 2; i += 0.4) {
        const wy = topY + i * 6;
        const wx = cx + Math.sin(wavePhase + i * 1.5 + cx * 0.03) * 10;
        ctx.beginPath();
        ctx.moveTo(wx - 18, wy);
        ctx.quadraticCurveTo(wx, wy - 3, wx + 18, wy);
        ctx.stroke();
      }
      // Wave highlight
      const hl = Math.sin(state.time * 1.5 + cx * 0.02) * 0.3 + 0.5;
      ctx.fillStyle = `rgba(180,220,255,${hl * 0.08})`;
      ctx.fillRect(cx - tw/2, topY - 2, tw, 4);
      break;
    }
    case 'desert': {
      // Gentle dune curves
      ctx.strokeStyle = 'rgba(228,200,122,0.2)';
      ctx.lineWidth = 1;
      for (let i = -2; i <= 2; i += 0.3) {
        const dy2 = topY + i * 5 + Math.sin(i * 0.8) * 2;
        ctx.beginPath();
        ctx.moveTo(cx - 20, dy2 + 3);
        ctx.quadraticCurveTo(cx, dy2, cx + 20, dy2 + 3);
        ctx.stroke();
      }
      // Small dune sparkle
      if (Math.random() < 0.02) {
        ctx.fillStyle = 'rgba(255,255,200,0.4)';
        ctx.beginPath();
        ctx.arc(cx + (Math.random() - 0.5) * 30, topY + (Math.random() - 0.5) * 15, 1.5, 0, Math.PI * 2);
        ctx.fill();
      }
      break;
    }
    case 'mountain': {
      // Rocky peak on top
      const peakH = 18 + Math.sin(state.time * 0.3 + cx) * 2;
      const peakX = cx + Math.sin(cx * 0.5) * 2;
      const peakY = topY - th / 4 - peakH;
      // Shadow side of peak
      ctx.beginPath();
      ctx.moveTo(peakX, peakY);
      ctx.lineTo(cx + th / 4, topY - 2);
      ctx.lineTo(cx, topY - 2);
      ctx.closePath();
      ctx.fillStyle = '#4a4a5a';
      ctx.fill();
      // Sunlit side
      ctx.beginPath();
      ctx.moveTo(peakX, peakY);
      ctx.lineTo(cx, topY - 2);
      ctx.lineTo(cx - th / 4, topY - 2);
      ctx.closePath();
      ctx.fillStyle = '#7a7a8a';
      ctx.fill();
      // Snow cap
      if (peakH > 16) {
        ctx.beginPath();
        ctx.moveTo(peakX, peakY);
        ctx.lineTo(peakX - 4, peakY + 6);
        ctx.lineTo(peakX + 4, peakY + 6);
        ctx.closePath();
        ctx.fillStyle = 'rgba(200,200,220,0.5)';
        ctx.fill();
      }
      // Rocky details
      ctx.strokeStyle = 'rgba(0,0,0,0.1)';
      ctx.lineWidth = 0.5;
      for (let i = 0; i < 3; i++) {
        const rx = cx + (i - 1) * 6 + Math.sin(i * 2) * 3;
        const ry = topY - 4 - i * 4;
        ctx.beginPath();
        ctx.moveTo(rx - 3, ry);
        ctx.lineTo(rx + 3, ry + 3);
        ctx.stroke();
      }
      break;
    }
    case 'blocked': {
      // Cross-hatch pattern
      ctx.strokeStyle = 'rgba(255,0,0,0.08)';
      ctx.lineWidth = 0.5;
      for (let i = -1; i <= 1; i += 0.5) {
        const bx = cx + i * 16;
        ctx.beginPath();
        ctx.moveTo(bx - 8, topY - 12);
        ctx.lineTo(bx + 8, topY + 12);
        ctx.stroke();
      }
      for (let i = -1; i <= 1; i += 0.5) {
        const by = topY + i * 16;
        ctx.beginPath();
        ctx.moveTo(cx - 16, by - 8);
        ctx.lineTo(cx + 16, by + 8);
        ctx.stroke();
      }
      // Skull-like X
      ctx.fillStyle = 'rgba(255,68,68,0.15)';
      ctx.font = `${ISO.th * 0.3}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('✕', cx, topY + 1);
      break;
    }
  }
  
  ctx.restore();
}

// ─── Main 3D Drawing Function ───
function drawGrid3D(canvas) {
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  ISO.ox = w / 2;
  ISO.oy = h * 0.42;
  const { tw, th, hs, ox, oy } = ISO;
  
  // Clear
  ctx.fillStyle = '#0a0a0f';
  ctx.fillRect(0, 0, w, h);
  
  // Subtle background gradient
  const bgGrad = ctx.createRadialGradient(ox, oy + 120, 20, ox, oy + 120, 360);
  bgGrad.addColorStop(0, 'rgba(20,20,40,0.3)');
  bgGrad.addColorStop(0.5, 'rgba(15,15,25,0.15)');
  bgGrad.addColorStop(1, 'rgba(10,10,15,0)');
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, w, h);
  
  // Ground shadow plane
  ctx.beginPath();
  ctx.moveTo(ox, oy - th / 2 * 4);
  ctx.lineTo(ox + tw * 3, oy + th * 2);
  ctx.lineTo(ox, oy + th / 2 * 8);
  ctx.lineTo(ox - tw * 3, oy + th * 2);
  ctx.closePath();
  ctx.fillStyle = 'rgba(0,0,0,0.15)';
  ctx.fill();
  
  // Breathing oscillation
  const breath = Math.sin(state.time * 1.5) * 1.5;
  
  // Build cell data list
  const z = ISO.zoom;
  const cells = [];
  for (let y = 0; y < state.gridSize; y++) {
    for (let x = 0; x < state.gridSize; x++) {
      const tt = getTerrainAt(x, y);
      const hgt = TH[tt] || 0;
      const hPx = hgt * hs * z;
      const { sx, sy } = isoToScreen(x, y);
      const isG = state.goal[0] === x && state.goal[1] === y;
      const isR = !!state.rewards[`${x},${y}`];
      const visIdx = state.visited.findIndex(p => Math.round(p[0]) === x && Math.round(p[1]) === y);
      const isT = state.animPos[0] >= x - 0.4 && state.animPos[0] <= x + 0.4 &&
                   state.animPos[1] >= y - 0.4 && state.animPos[1] <= y + 0.4;
      
      cells.push({ x, y, tt, hgt, hPx, sx, sy, isG, isR, isT, visIdx,
        colors: TC3D[tt] || TC3D['plains'],
        isB: tt === 'blocked',
        sortKey: (x + y) * th * z / 2 + Math.max(0, hPx) + (isT ? 1000 : 0),
      });
    }
  }
  
  // Sort back-to-front by visual depth
  cells.sort((a, b) => a.sortKey - b.sortKey);
  
  // Draw cells
  for (const c of cells) {
    const { x, y, tt, hPx, sx, sy, colors, isG, isR, isT, visIdx, isB } = c;
    
    // Draw 3D block
    drawBlock3D(ctx, sx, sy, hPx, colors, breath, { tt });
    
    const topY = hPx >= 0 ? sy - hPx + breath : sy + breath;
    
    // ── TELOS B: Omega Heatmap Mode ──
    if (state.omegaHeatmap) {
      // Color cells by uncertainty contribution based on position relative to TELOS
      const pos = state.animPos || state.position;
      const dx = x - pos[0];
      const dy = y - pos[1];
      const dist = Math.sqrt(dx*dx + dy*dy) || 0.01;
      const maxDist = state.gridSize * 1.5;
      
      // Unexplored cells far from TELOS get high Ω_W (blue glow)
      const vk = `${x},${y}`;
      const visited = state.visitCounts[vk] || 0;
      const isBlocked = tt === 'blocked';
      
      let omegaColor;
      if (isBlocked) {
        omegaColor = 'rgba(40,20,20,0.7)';  // Blocked = dark red
      } else if (visited === 0) {
        // Unexplored: strong blue glow, intensity fades with distance
        const intensity = Math.max(0.2, Math.min(1.0, 1.0 - dist / maxDist));
        const alpha = 0.3 + intensity * 0.5;
        omegaColor = `rgba(40, 100, 255, ${alpha})`;
      } else if (dist < 1.5) {
        // Near TELOS: green glow (low uncertainty)
        const intensity = Math.max(0.1, 1.0 - dist * 0.5);
        omegaColor = `rgba(74, 222, 128, ${intensity * 0.4})`;
      } else {
        // Visited but not near: low transparency
        omegaColor = 'rgba(100, 100, 120, 0.15)';
      }
      
      // Draw overlay on top face
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(sx - tw/2, topY);
      ctx.lineTo(sx, topY - th/2);
      ctx.lineTo(sx + tw/2, topY);
      ctx.lineTo(sx, topY + th/2);
      ctx.closePath();
      ctx.fillStyle = omegaColor;
      ctx.fill();
      
      // Draw omega value indicator
      const omegaVal = isBlocked ? 0.9 : visited === 0 ? Math.max(0.3, 1.0 - dist / maxDist) : 0.1;
      ctx.fillStyle = 'rgba(255,255,255,0.7)';
      ctx.font = `bold ${ISO.th * 0.22}px monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('Ω:' + omegaVal.toFixed(1), sx, topY + 1);
      ctx.restore();
      
    // ── Feature 5: Heat Map Mode ──
    } else if (state.heatMode) {
      const vk = `${x},${y}`;
      const count = state.visitCounts[vk] || 0;
      let heatColor;
      if (count === 0) heatColor = 'rgba(10,10,15,0.88)';
      else if (count === 1) heatColor = 'rgba(10,26,58,0.88)';
      else if (count <= 3) heatColor = 'rgba(10,42,90,0.88)';
      else if (count <= 7) heatColor = 'rgba(58,42,26,0.88)';
      else heatColor = 'rgba(90,26,26,0.88)';
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(sx - tw/2, topY);
      ctx.lineTo(sx, topY - th/2);
      ctx.lineTo(sx + tw/2, topY);
      ctx.lineTo(sx, topY + th/2);
      ctx.closePath();
      ctx.fillStyle = heatColor;
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.06)';
      ctx.lineWidth = 0.5;
      ctx.stroke();
      ctx.fillStyle = count > 0 ? '#fff' : 'rgba(255,255,255,0.35)';
      ctx.font = `bold ${ISO.th * 0.26}px monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(count, sx, topY + 1);
      ctx.restore();
    // ── Feature 3: Cost View ──
    } else if (state.showCosts) {
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(sx - tw/2, topY);
      ctx.lineTo(sx, topY - th/2);
      ctx.lineTo(sx + tw/2, topY);
      ctx.lineTo(sx, topY + th/2);
      ctx.closePath();
      ctx.clip();
      ctx.fillStyle = 'rgba(255,255,255,0.05)';
      ctx.fillRect(sx - tw/2, topY - th/2, tw, th);
      const cost = getTerrainCost(tt);
      ctx.fillStyle = '#ffffff';
      ctx.font = `bold ${ISO.th * 0.4}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('×' + cost, sx, topY + 1);
      ctx.restore();
    } else {
      // Draw terrain feature on top
      drawTerrainFeature(ctx, sx, sy, hPx, tt, breath);
    }
    
    // Breadcrumb trail
    if (visIdx >= 0 && !isT) {
      ctx.beginPath();
      ctx.arc(sx, topY + 2, 3, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255,107,107,0.4)';
      ctx.fill();
      ctx.fillStyle = 'rgba(255,255,255,0.2)';
      ctx.font = '7px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(visIdx + 1, sx, topY + 6);
    }
    
    // Reward star with value (upgrade 3)
    if (isR && !isT) {
      const pulse = Math.sin(state.time * 3 + x + y) * 0.15 + 0.85;
      ctx.globalAlpha = pulse;
      ctx.fillStyle = "#fbbf24";
      ctx.font = `${ISO.th * 0.28}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("⭐", sx, topY - 2);
      // Show reward value
      const rewKey = `${Math.round(x)},${Math.round(y)}`;
      const rewVal = state.rewards[rewKey];
      if (rewVal && rewVal > 0) {
        ctx.fillStyle = "rgba(255,255,200,0.9)";
        ctx.font = `bold ${ISO.th * 0.18}px sans-serif`;
        ctx.fillText("+" + rewVal, sx, topY + ISO.th * 0.22);
      }
      ctx.globalAlpha = 1;
    }
  }
  

  // ── Terrain transition flash (upgrade 1) ──
  for (let y = 0; y < state.gridSize; y++) {
    for (let x = 0; x < state.gridSize; x++) {
      const key = x + "," + y;
      const flash = state.terrainFlash ? state.terrainFlash[key] : null;
      if (flash) {
        const elapsed = state.time - flash.start;
        if (elapsed < 2.0) {
          const intensity = Math.max(0, 1.0 - elapsed / 2.0);
          const { sx, sy } = isoToScreen(x, y);
          const ttt = getTerrainAt(x, y);
          const hpx = (TH[ttt] || 0) * hs;
          const topY = hpx >= 0 ? sy - hpx + breath : sy + breath;
          ctx.save();
          ctx.beginPath();
          ctx.moveTo(sx, topY - ISO.th / 2);
          ctx.lineTo(sx + ISO.tw / 2, topY);
          ctx.lineTo(sx, topY + ISO.th / 2);
          ctx.lineTo(sx - ISO.tw / 2, topY);
          ctx.closePath();
          ctx.fillStyle = `rgba(255,200,100,${intensity * 0.4})`;
          ctx.fill();
          ctx.shadowColor = "#ffc864";
          ctx.shadowBlur = 20 * intensity;
          ctx.fillStyle = `rgba(255,200,100,${intensity * 0.15})`;
          ctx.fill();
          ctx.shadowBlur = 0;
          ctx.restore();
        } else {
          delete state.terrainFlash[key];
        }
      }
    }
  }
  
  // ── Fog of War: hide cells beyond distance 2 (upgrade 2) ──
  for (let y = 0; y < state.gridSize; y++) {
    for (let x = 0; x < state.gridSize; x++) {
      const pos_x = state.animPos[0] !== undefined ? state.animPos[0] : (state.position ? state.position[0] : 0);
      const pos_y = state.animPos[1] !== undefined ? state.animPos[1] : (state.position ? state.position[1] : 0);
      const dist = Math.abs(x - Math.round(pos_x)) + Math.abs(y - Math.round(pos_y));
      if (dist > 2) {
        const { sx, sy } = isoToScreen(x, y);
        const ttt = getTerrainAt(x, y);
        const hpx = (TH[ttt] || 0) * hs;
        const topY = hpx >= 0 ? sy - hpx + breath : sy + breath;
        const fogGrad = ctx.createRadialGradient(sx, topY, 0, sx, topY, ISO.tw * 0.6);
        fogGrad.addColorStop(0, "rgba(10,10,15,0.85)");
        fogGrad.addColorStop(0.6, "rgba(8,8,12,0.90)");
        fogGrad.addColorStop(1, "rgba(5,5,8,0.95)");
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(sx, topY - ISO.th / 2);
        ctx.lineTo(sx + ISO.tw / 2, topY);
        ctx.lineTo(sx, topY + ISO.th / 2);
        ctx.lineTo(sx - ISO.tw / 2, topY);
        ctx.closePath();
        ctx.fillStyle = fogGrad;
        ctx.fill();
        ctx.strokeStyle = "rgba(20,20,30,0.3)";
        ctx.lineWidth = 0.5;
        ctx.stroke();
        // Draw "?" symbol
        ctx.fillStyle = "rgba(100,100,120,0.5)";
        ctx.font = `bold ${ISO.th * 0.3}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("?", sx, topY + 1);
        ctx.restore();
      }
    }
  }
  
  // ── Feature 4: Alternative Path Ghosts ──
  if (state.altPaths.length > 0) {
    const altColors = [
      { stroke: 'rgba(100,180,255,0.25)', fill: 'rgba(100,180,255,0.08)' },
      { stroke: 'rgba(180,100,255,0.25)', fill: 'rgba(180,100,255,0.08)' },
      { stroke: 'rgba(255,180,100,0.25)', fill: 'rgba(255,180,100,0.08)' },
    ];
    for (let ai = 0; ai < Math.min(state.altPaths.length, 3); ai++) {
      const alt = state.altPaths[ai];
      if (alt.length < 2) continue;
      ctx.save();
      ctx.globalAlpha = 0.2;
      ctx.beginPath();
      for (let pi = 0; pi < alt.length; pi++) {
        const p = alt[pi];
        const { sx, sy } = isoToScreen(p[0], p[1]);
        const ttt = getTerrainAt(p[0], p[1]);
        const hpx = (TH[ttt] || 0) * hs;
        const topY = hpx >= 0 ? sy - hpx + breath : sy + breath;
        if (pi === 0) ctx.moveTo(sx, topY);
        else ctx.lineTo(sx, topY);
      }
      ctx.strokeStyle = altColors[ai].stroke;
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 6]);
      ctx.stroke();
      ctx.setLineDash([]);
      // Endpoint marker
      const last = alt[alt.length - 1];
      const { sx: lsx, sy: lsy } = isoToScreen(last[0], last[1]);
      const ltt = getTerrainAt(last[0], last[1]);
      const lhp = (TH[ltt] || 0) * hs;
      const lty = lhp >= 0 ? lsy - lhp + breath : lsy + breath;
      ctx.beginPath();
      ctx.arc(lsx, lty, 4, 0, Math.PI * 2);
      ctx.fillStyle = altColors[ai].fill;
      ctx.fill();
      ctx.strokeStyle = altColors[ai].stroke;
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.restore();
    }
  }
  
  // === Counterfactual ghosts (drawn between cells and TELOS) ===
  if (state.visited.length > 0) {
    const last = state.visited[state.visited.length - 1];
    for (let dx = -1; dx <= 1; dx += 2) {
      for (let dy = -1; dy <= 1; dy += 2) {
        const gx = Math.round(last[0]) + dx, gy = Math.round(last[1]) + dy;
        if (gx < 0 || gx >= state.gridSize || gy < 0 || gy >= state.gridSize) continue;
        if (getTerrainAt(gx, gy) === 'blocked') continue;
        if (state.visited.some(p => Math.round(p[0]) === gx && Math.round(p[1]) === gy)) continue;
        
        const { sx, sy } = isoToScreen(gx, gy);
        const ttt = getTerrainAt(gx, gy);
        const hpx = (TH[ttt] || 0) * hs;
        const topY = hpx >= 0 ? sy - hpx + breath : sy + breath;
        
        ctx.save();
        ctx.globalAlpha = 0.2 + Math.sin(state.time * 2 + gx + gy) * 0.05;
        ctx.beginPath();
        ctx.moveTo(sx, topY - ISO.th / 3);
        ctx.lineTo(sx + ISO.tw / 3, topY);
        ctx.lineTo(sx, topY + ISO.th / 3);
        ctx.lineTo(sx - ISO.tw / 3, topY);
        ctx.closePath();
        ctx.fillStyle = 'rgba(255,107,107,0.08)';
        ctx.fill();
        ctx.strokeStyle = 'rgba(255,107,107,0.25)';
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 3]);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = 'rgba(255,200,200,0.12)';
        ctx.font = `${ISO.th * 0.18}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('?', sx, topY + 1);
        ctx.globalAlpha = 1;
        ctx.restore();
      }
    }
  }
  
  // === Trajectory line ===
  if (state.visited.length > 1) {
    ctx.beginPath();
    for (let i = 0; i < state.visited.length; i++) {
      const p = state.visited[i];
      const { sx, sy } = isoToScreen(p[0], p[1]);
      const ttt = getTerrainAt(p[0], p[1]);
      const hpx = (TH[ttt] || 0) * hs;
      const topY = hpx >= 0 ? sy - hpx + breath : sy + breath;
      if (i === 0) ctx.moveTo(sx, topY);
      else {
        const prev = state.visited[i - 1];
        const { sx: psx, sy: psy } = isoToScreen(prev[0], prev[1]);
        const ptt = getTerrainAt(prev[0], prev[1]);
        const php = (TH[ptt] || 0) * hs;
        const pty = php >= 0 ? psy - php + breath : psy + breath;
        const midX = (psx + sx) / 2;
        const midY = (pty + topY) / 2 - 2;
        ctx.quadraticCurveTo(midX, midY, sx, topY);
      }
    }
    ctx.strokeStyle = 'rgba(255,107,107,0.35)';
    ctx.lineWidth = 2;
    ctx.stroke();
    
    ctx.beginPath();
    for (let i = 0; i < state.visited.length; i++) {
      const p = state.visited[i];
      const { sx, sy } = isoToScreen(p[0], p[1]);
      const ttt = getTerrainAt(p[0], p[1]);
      const hpx = (TH[ttt] || 0) * hs;
      const topY = hpx >= 0 ? sy - hpx + breath : sy + breath;
      if (i === 0) ctx.moveTo(sx, topY);
      else ctx.lineTo(sx, topY);
    }
    ctx.strokeStyle = 'rgba(255,107,107,0.12)';
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 6]);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  
  // ── Feature 1: Shortest-Path Overlay (green dotted line with glow) ──
  if (state.shortestPath && state.shortestPath.length > 1) {
    ctx.save();
    ctx.shadowColor = '#4ade80';
    ctx.shadowBlur = 14;
    ctx.beginPath();
    for (let i = 0; i < state.shortestPath.length; i++) {
      const p = state.shortestPath[i];
      const { sx, sy } = isoToScreen(p[0], p[1]);
      const ttt = getTerrainAt(p[0], p[1]);
      const hpx = (TH[ttt] || 0) * hs;
      const topY = hpx >= 0 ? sy - hpx + breath : sy + breath;
      if (i === 0) ctx.moveTo(sx, topY);
      else ctx.lineTo(sx, topY);
    }
    ctx.strokeStyle = 'rgba(74,222,128,0.6)';
    ctx.lineWidth = 4;
    ctx.setLineDash([4, 4]);
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = '#4ade80';
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 4]);
    ctx.stroke();
    ctx.setLineDash([]);
    for (let i = 0; i < state.shortestPath.length; i++) {
      const p = state.shortestPath[i];
      const { sx, sy } = isoToScreen(p[0], p[1]);
      const ttt = getTerrainAt(p[0], p[1]);
      const hpx = (TH[ttt] || 0) * hs;
      const topY = hpx >= 0 ? sy - hpx + breath : sy + breath;
      const pulse = Math.sin(state.time * 3 + i * 0.5) * 0.2 + 0.8;
      ctx.beginPath();
      ctx.arc(sx, topY, 3 * pulse, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(74,222,128,${0.4 * pulse})`;
      ctx.fill();
    }
    ctx.restore();
  }
  
  // ── Feature 2: Hover Tooltip Info Panel ──
  if (state.hoveredCell && state.hoverPos) {
    const [hx, hy] = state.hoveredCell;
    const ttt = getTerrainAt(hx, hy);
    const cost = getTerrainCost(ttt);
    const onPath = state.shortestPath && state.shortestPath.some(p => p[0] === hx && p[1] === hy);
    let distToGoal = '\u2014';
    if (state.shortestPath && state.shortestPath.length > 0) {
      const idx = state.shortestPath.findIndex(p => p[0] === hx && p[1] === hy);
      if (idx >= 0) distToGoal = (state.shortestPath.length - 1 - idx) + ' cells';
    }
    const emojis = {plains:'🌿', forest:'🌲', water:'🌊', desert:'🏜️', mountain:'⛰️', blocked:'🧱'};
    const label = ttt.charAt(0).toUpperCase() + ttt.slice(1);
    const lines = [
      `${emojis[ttt] || '❓'} ${label} \u00b7 \u00d7${cost}`,
      `Distance to goal: ${distToGoal}`,
      onPath ? '✅ On optimal path' : '❌ Not optimal path',
    ];
    
    const { sx, sy } = state.hoverPos;
    const panelW = 188, lineH = 20, titleH = 22;
    const panelH = titleH + lines.length * lineH + 12;
    
    let px = sx + 24, py = sy - panelH / 2;
    if (px + panelW > w) px = sx - panelW - 24;
    if (py < 6) py = 6;
    if (py + panelH > h - 6) py = h - panelH - 6;
    
    ctx.save();
    ctx.shadowColor = 'rgba(0,0,0,0.6)';
    ctx.shadowBlur = 16;
    ctx.fillStyle = 'rgba(10,10,22,0.94)';
    ctx.strokeStyle = 'rgba(74,222,128,0.25)';
    ctx.lineWidth = 1;
    roundRect(ctx, px, py, panelW, panelH, 10);
    ctx.fill();
    ctx.stroke();
    ctx.shadowBlur = 0;
    
    ctx.fillStyle = '#e0e0e0';
    ctx.font = 'bold 13px sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(`📍 Cell (${hx},${hy})`, px + 12, py + 8);
    
    ctx.fillStyle = 'rgba(255,255,255,0.06)';
    ctx.fillRect(px + 12, py + titleH + 2, panelW - 24, 1);
    
    for (let i = 0; i < lines.length; i++) {
      const color = i === 2 ? (onPath ? '#4ade80' : '#ff6b6b') : '#b0b0b0';
      ctx.fillStyle = color;
      ctx.font = i === 0 ? 'bold 12px sans-serif' : '12px sans-serif';
      ctx.fillText(lines[i], px + 12, py + titleH + 10 + i * lineH);
    }
    ctx.restore();
  }
  
  // === Goal marker ===
  const gs = isoToScreen(state.goal[0], state.goal[1]);
  const gTT = getTerrainAt(state.goal[0], state.goal[1]);
  const gHPx = (TH[gTT] || 0) * hs;
  const gTopY = gHPx >= 0 ? gs.sy - gHPx + breath : gs.sy + breath;
  drawGoalMarker(ctx, gs.sx, gTopY);
  
  // === TELOS orb ===
  drawTELOS(ctx);
  drawAgent2(ctx);
  // ── Second Agent (upgrade 5) ──
  drawAgent2(ctx);
  
  // ── Inter-agent communication line ──
  if (state.position && state.agent2Pos) {
    const p1 = isoToScreen(state.position[0], state.position[1]);
    const p2 = isoToScreen(state.agent2Pos[0], state.agent2Pos[1]);
    const pulse = Math.sin(state.time * 2) * 0.3 + 0.5;
    ctx.strokeStyle = `rgba(100, 200, 255, ${pulse * 0.3})`;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 6]);
    ctx.beginPath();
    ctx.moveTo(p1.sx, p1.sy - 20);
    ctx.lineTo(p2.sx, p2.sy - 20);
    ctx.stroke();
    ctx.setLineDash([]);
    // Data packet traveling along the line
    const t = (state.time * 0.5) % 1;
    const mx = p1.sx + (p2.sx - p1.sx) * t;
    const my = (p1.sy - 20) + (p2.sy - p1.sy - 20) * t;
    ctx.fillStyle = `rgba(100, 200, 255, ${pulse * 0.8})`;
    ctx.beginPath();
    ctx.arc(mx, my, 3, 0, Math.PI * 2);
    ctx.fill();
  }
  
  // === Particles ===
  drawParticles(ctx);
}


// ─── Goal Marker ───
function drawGoalMarker(ctx, cx, cy) {
  const pulse = Math.sin(state.time * 2.5) * 0.2 + 0.8;
  const radius = 8 + Math.sin(state.time * 3) * 2;
  
  // Outer glow
  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 3);
  grad.addColorStop(0, `rgba(250,204,21,${pulse * 0.5})`);
  grad.addColorStop(0.3, `rgba(250,204,21,${pulse * 0.15})`);
  grad.addColorStop(1, 'rgba(250,204,21,0)');
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(cx, cy, radius * 3, 0, Math.PI * 2);
  ctx.fill();
  
  // Inner glow
  const innerGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
  innerGrad.addColorStop(0, `rgba(255,240,150,${pulse})`);
  innerGrad.addColorStop(0.6, `rgba(250,204,21,${pulse * 0.8})`);
  innerGrad.addColorStop(1, `rgba(200,150,10,0)`);
  ctx.fillStyle = innerGrad;
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fill();
  
  // Center
  ctx.fillStyle = `rgba(255,255,220,${pulse})`;
  ctx.beginPath();
  ctx.arc(cx, cy, radius * 0.35, 0, Math.PI * 2);
  ctx.fill();
  
  // Light rays
  ctx.strokeStyle = `rgba(250,204,21,${pulse * 0.08})`;
  ctx.lineWidth = 0.5;
  for (let i = 0; i < 8; i++) {
    const angle = i * Math.PI / 4 + state.time * 0.5;
    const len = radius * (1.5 + Math.sin(state.time * 2 + i) * 0.5);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(angle) * len, cy + Math.sin(angle) * len);
    ctx.stroke();
  }
  
  // Label
  ctx.fillStyle = `rgba(255,255,200,${0.4 + pulse * 0.3})`;
  ctx.font = 'bold 9px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'bottom';
  ctx.fillText('GOAL', cx, cy - radius - 4);
}

// ─── TELOS Character ───
function drawTELOS(ctx) {
  const { hs } = ISO;
  const { sx, sy } = isoToScreen(state.animPos[0], state.animPos[1]);
  const tt = getTerrainAt(state.animPos[0], state.animPos[1]);
  const hPx = (TH[tt] || 0) * hs;
  const breath = Math.sin(state.time * 1.5) * 1.5;
  const topY = hPx >= 0 ? sy - hPx + breath : sy + breath;
  
  // Orb floats above terrain
  const floatY = topY - 28 + Math.sin(state.time * 2) * 3;
  const orbPulse = Math.sin(state.time * 3) * 0.15 + 0.85;
  const orbRadius = 9 + Math.sin(state.time * 2.5) * 1.5;
  
  // Glow trail (trailing ghosts)
  const trailLen = 3;
  for (let i = 1; i <= trailLen; i++) {
    const t = state.time - i * 0.08;
    const trailPos = [
      state.prevPos[0] + (state.position[0] - state.prevPos[0]) * Math.max(0, 1 - i * 0.25),
      state.prevPos[1] + (state.position[1] - state.prevPos[1]) * Math.max(0, 1 - i * 0.25),
    ];
    const { sx: tsx, sy: tsy } = isoToScreen(trailPos[0], trailPos[1]);
    const ttt = getTerrainAt(trailPos[0], trailPos[1]);
    const thp = (TH[ttt] || 0) * hs;
    const tty = thp >= 0 ? tsy - thp + breath : tsy + breath;
    const tAlpha = 0.15 / i;
    const tRad = orbRadius * (0.7 - i * 0.15);
    
    const tg = ctx.createRadialGradient(tsx, tty - 28, 0, tsx, tty - 28, tRad * 2);
    tg.addColorStop(0, `rgba(255,107,107,${tAlpha})`);
    tg.addColorStop(1, 'rgba(255,107,107,0)');
    ctx.fillStyle = tg;
    ctx.beginPath();
    ctx.arc(tsx, tty - 28, tRad * 2, 0, Math.PI * 2);
    ctx.fill();
  }
  
  // Orb outer glow
  const outerGrad = ctx.createRadialGradient(sx, floatY, 0, sx, floatY, orbRadius * 4);
  outerGrad.addColorStop(0, `rgba(255,107,107,${orbPulse * 0.35})`);
  outerGrad.addColorStop(0.4, `rgba(255,107,107,${orbPulse * 0.1})`);
  outerGrad.addColorStop(1, 'rgba(255,107,107,0)');
  ctx.fillStyle = outerGrad;
  ctx.beginPath();
  ctx.arc(sx, floatY, orbRadius * 4, 0, Math.PI * 2);
  ctx.fill();
  
  // Orb body
  const orbGrad = ctx.createRadialGradient(
    sx - orbRadius * 0.3, floatY - orbRadius * 0.3, 0,
    sx, floatY, orbRadius
  );
  orbGrad.addColorStop(0, `rgba(255,200,200,${orbPulse})`);
  orbGrad.addColorStop(0.3, `rgba(255,120,120,${orbPulse * 0.9})`);
  orbGrad.addColorStop(0.7, `rgba(255,60,60,${orbPulse * 0.7})`);
  orbGrad.addColorStop(1, `rgba(200,20,20,${orbPulse * 0.3})`);
  ctx.fillStyle = orbGrad;
  ctx.beginPath();
  ctx.arc(sx, floatY, orbRadius, 0, Math.PI * 2);
  ctx.fill();
  
  // Inner core glow
  ctx.fillStyle = `rgba(255,255,255,${orbPulse * 0.5})`;
  ctx.beginPath();
  ctx.arc(sx - orbRadius * 0.2, floatY - orbRadius * 0.2, orbRadius * 0.3, 0, Math.PI * 2);
  ctx.fill();
  
  // Lightning bolts around orb
  ctx.strokeStyle = `rgba(255,200,200,${Math.sin(state.time * 4) * 0.08 + 0.1})`;
  ctx.lineWidth = 1;
  for (let i = 0; i < 3; i++) {
    const angle = i * Math.PI * 2 / 3 + state.time * 1.5;
    const r1 = orbRadius * 1.2;
    const r2 = orbRadius * 1.8 + Math.sin(state.time * 5 + i) * 3;
    const r3 = orbRadius * 1.5;
    ctx.beginPath();
    ctx.moveTo(sx + Math.cos(angle) * r1, floatY + Math.sin(angle) * r1);
    ctx.lineTo(sx + Math.cos(angle + 0.3) * r2, floatY + Math.sin(angle + 0.3) * r2);
    ctx.lineTo(sx + Math.cos(angle + 0.6) * r3, floatY + Math.sin(angle + 0.6) * r3);
    ctx.stroke();
  }
  
  // Label
  ctx.fillStyle = `rgba(255,200,200,${0.3 + Math.sin(state.time * 2) * 0.1})`;
  ctx.font = 'bold 8px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'bottom';
  ctx.fillText('TELOS', sx, floatY - orbRadius - 3);
}

// ─── Agent2 Character (Blue competitor) ───
function drawAgent2(ctx) {
  if (!state.agent2Pos) return;
  const { hs } = ISO;
  const { sx, sy } = isoToScreen(state.agent2Pos[0], state.agent2Pos[1]);
  const tt = getTerrainAt(state.agent2Pos[0], state.agent2Pos[1]);
  const hPx = (TH[tt] || 0) * hs;
  const breath = Math.sin(state.time * 1.5) * 1.5;
  const topY = hPx >= 0 ? sy - hPx + breath : sy + breath;
  const floatY = topY - 28 + Math.sin(state.time * 2 + 1.5) * 3;
  const orbPulse = Math.sin(state.time * 3 + 1) * 0.15 + 0.85;
  const orbRadius = 8 + Math.sin(state.time * 2.5 + 1) * 1.5;
  
  // Outer glow
  const grad = ctx.createRadialGradient(sx, floatY, 0, sx, floatY, orbRadius * 4);
  grad.addColorStop(0, `rgba(74,144,255,${orbPulse * 0.3})`);
  grad.addColorStop(0.4, `rgba(74,144,255,${orbPulse * 0.1})`);
  grad.addColorStop(1, 'rgba(74,144,255,0)');
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(sx, floatY, orbRadius * 4, 0, Math.PI * 2);
  ctx.fill();
  
  // Orb body
  const orbGrad = ctx.createRadialGradient(
    sx - orbRadius * 0.3, floatY - orbRadius * 0.3, 0,
    sx, floatY, orbRadius
  );
  orbGrad.addColorStop(0, `rgba(200,220,255,${orbPulse})`);
  orbGrad.addColorStop(0.3, `rgba(100,180,255,${orbPulse * 0.9})`);
  orbGrad.addColorStop(0.7, `rgba(50,120,255,${orbPulse * 0.7})`);
  orbGrad.addColorStop(1, `rgba(20,60,200,${orbPulse * 0.3})`);
  ctx.fillStyle = orbGrad;
  ctx.beginPath();
  ctx.arc(sx, floatY, orbRadius, 0, Math.PI * 2);
  ctx.fill();
  
  // Inner core
  ctx.fillStyle = `rgba(255,255,255,${orbPulse * 0.4})`;
  ctx.beginPath();
  ctx.arc(sx - orbRadius * 0.2, floatY - orbRadius * 0.2, orbRadius * 0.25, 0, Math.PI * 2);
  ctx.fill();
  
  // Label
  ctx.fillStyle = `rgba(150,200,255,${0.3 + Math.sin(state.time * 2 + 1) * 0.1})`;
  ctx.font = 'bold 8px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'bottom';
  ctx.fillText('Agent2', sx, floatY - orbRadius - 3);
}

// ─── Second Agent (blue marker, upgrade 5) ───
function drawAgent2(ctx) {
  if (!state.agent2Pos) return;
  const { hs } = ISO;
  const { sx, sy } = isoToScreen(state.agent2Pos[0], state.agent2Pos[1]);
  const tt = getTerrainAt(state.agent2Pos[0], state.agent2Pos[1]);
  const hPx = (TH[tt] || 0) * hs;
  const breath = Math.sin(state.time * 1.5) * 1.5;
  const topY = hPx >= 0 ? sy - hPx + breath : sy + breath;
  
  const floatY = topY - 24 + Math.sin(state.time * 1.8 + 1.0) * 2;
  const orbRadius = 7 + Math.sin(state.time * 2) * 1.0;
  
  // Outer glow (blue)
  const outerGrad = ctx.createRadialGradient(sx, floatY, 0, sx, floatY, orbRadius * 3.5);
  outerGrad.addColorStop(0, "rgba(74,144,255,0.3)");
  outerGrad.addColorStop(0.5, "rgba(74,144,255,0.08)");
  outerGrad.addColorStop(1, "rgba(74,144,255,0)");
  ctx.fillStyle = outerGrad;
  ctx.beginPath();
  ctx.arc(sx, floatY, orbRadius * 3.5, 0, Math.PI * 2);
  ctx.fill();
  
  // Orb body (blue)
  const orbGrad = ctx.createRadialGradient(
    sx - orbRadius * 0.3, floatY - orbRadius * 0.3, 0,
    sx, floatY, orbRadius
  );
  orbGrad.addColorStop(0, "rgba(180,210,255,0.9)");
  orbGrad.addColorStop(0.3, "rgba(74,144,255,0.8)");
  orbGrad.addColorStop(0.7, "rgba(40,90,200,0.6)");
  orbGrad.addColorStop(1, "rgba(20,50,150,0.3)");
  ctx.fillStyle = orbGrad;
  ctx.beginPath();
  ctx.arc(sx, floatY, orbRadius, 0, Math.PI * 2);
  ctx.fill();
  
  // Inner core
  ctx.fillStyle = "rgba(200,220,255,0.5)";
  ctx.beginPath();
  ctx.arc(sx - orbRadius * 0.2, floatY - orbRadius * 0.2, orbRadius * 0.25, 0, Math.PI * 2);
  ctx.fill();
  
  // Lightning bolts
  ctx.strokeStyle = "rgba(150,200,255,0.12)";
  ctx.lineWidth = 0.8;
  for (let i = 0; i < 3; i++) {
    const angle = i * Math.PI * 2 / 3 + state.time * 1.2 + 1.0;
    const r1 = orbRadius * 1.1;
    const r2 = orbRadius * 1.6 + Math.sin(state.time * 4 + i + 1) * 2;
    const r3 = orbRadius * 1.3;
    ctx.beginPath();
    ctx.moveTo(sx + Math.cos(angle) * r1, floatY + Math.sin(angle) * r1);
    ctx.lineTo(sx + Math.cos(angle + 0.3) * r2, floatY + Math.sin(angle + 0.3) * r2);
    ctx.lineTo(sx + Math.cos(angle + 0.6) * r3, floatY + Math.sin(angle + 0.6) * r3);
    ctx.stroke();
  }
  
  // Label
  ctx.fillStyle = "rgba(150,200,255,0.4)";
  ctx.font = "bold 7px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "bottom";
  ctx.fillText("Agent2", sx, floatY - orbRadius - 2);
}

// ─── Particle System ───
 function spawnParticles() {
    // Continuous particle spawning for living feel
    if (state.particles.length < 80 && Math.random() < 0.3) {
     const x = Math.random() * state.gridSize;
     const y = Math.random() * state.gridSize;
     const tt = getTerrainAt(Math.floor(x), Math.floor(y));
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
      // (solar ambient star particles removed — was copy-paste from KG closure)
   }

function drawParticles(ctx) {
  const { hs } = ISO;
  
  for (let i = state.particles.length - 1; i >= 0; i--) {
    const p = state.particles[i];
    p.life -= 0.005 * p.speed;
    if (p.life <= 0) { state.particles.splice(i, 1); continue; }
    
    // Update position (float upward and drift)
    p.x += p.drift * 0.01;
    p.y += p.drift * 0.01;
    
    const { sx, sy } = isoToScreen(p.x % state.gridSize, p.y % state.gridSize);
    const tt = getTerrainAt(Math.floor(p.x) % state.gridSize, Math.floor(p.y) % state.gridSize);
    const hPx = (TH[tt] || 0) * hs;
    const breath = Math.sin(state.time * 1.5) * 1.5;
    const topY = hPx >= 0 ? sy - hPx + breath : sy + breath;
    
    // Float upward from terrain
    const floatUp = (1 - p.life) * 30;
    const px = sx + Math.sin(state.time * 0.5 + p.x * 3) * 3;
    const py = topY - 5 - floatUp;
    
    // Glow
    const grad = ctx.createRadialGradient(px, py, 0, px, py, p.size * 2);
    grad.addColorStop(0, `hsla(${p.hue},80%,70%,${p.life * 0.5})`);
    grad.addColorStop(1, `hsla(${p.hue},80%,70%,0)`);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(px, py, p.size * 2, 0, Math.PI * 2);
    ctx.fill();
    
    // Core
    ctx.fillStyle = `hsla(${p.hue},60%,80%,${p.life * 0.6})`;
    ctx.beginPath();
    ctx.arc(px, py, p.size * 0.5, 0, Math.PI * 2);
    ctx.fill();
  }
}

function renderGrid() { const c = document.getElementById('grid-canvas'); if (c) drawGrid3D(c); }

const TERRAIN_EMOJI = { 'plains':'🌿', 'forest':'🌲', 'water':'🌊', 'desert':'🏜️', 'mountain':'⛰️' };

function toggleCostView() {
  state.showCosts = !state.showCosts;
  state.heatMode = false;
  document.getElementById('btn-cost-view').className = state.showCosts ? 'active' : '';
  document.getElementById('btn-heat-mode').className = '';
  state.shortestPath = computeShortestPath();
}

function toggleHeatMode() {
  state.heatMode = !state.heatMode;
  state.showCosts = false;
  state.omegaHeatmap = false;
  document.getElementById('btn-heat-mode').className = state.heatMode ? 'active' : '';
  document.getElementById('btn-cost-view').className = '';
  document.getElementById('btn-omega-heat').className = '';
}

function toggleOmegaHeatmap() {
  state.omegaHeatmap = !state.omegaHeatmap;
  state.showCosts = false;
  state.heatMode = false;
  document.getElementById('btn-omega-heat').className = state.omegaHeatmap ? 'active' : '';
  document.getElementById('btn-cost-view').className = '';
  document.getElementById('btn-heat-mode').className = '';
}
