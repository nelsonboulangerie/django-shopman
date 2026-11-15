// Rotas lado a lado, como linhas de metrô (dono, 14/11/2026): onde duas
// corridas passam pelo mesmo trecho, as linhas correm paralelas, encostadas, e
// nenhuma some debaixo da outra. Fora do trecho comum, cada uma volta ao seu eixo.
//
// Puro, em pixels da tela (o deslocamento é em px, não em grau de mapa).
export interface Pt {
  x: number;
  y: number;
}
export interface Line {
  id: number;
  points: Pt[];
}

const PARALLEL = Math.sin((10 * Math.PI) / 180); // até 10° conta como paralelo
const NEAR = 7; // px: mais perto que isso, o trecho é o mesmo

function sub(a: Pt, b: Pt): Pt {
  return { x: a.x - b.x, y: a.y - b.y };
}
function len(v: Pt) {
  return Math.hypot(v.x, v.y) || 1;
}
function unit(v: Pt): Pt {
  const l = len(v);
  return { x: v.x / l, y: v.y / l };
}

/** Os dois trechos correm juntos? (quase paralelos, colados e com sobreposição) */
function shared(a: [Pt, Pt], b: [Pt, Pt]): boolean {
  const da = unit(sub(a[1], a[0]));
  const db = unit(sub(b[1], b[0]));
  if (Math.abs(da.x * db.y - da.y * db.x) > PARALLEL) return false;
  // distância de b à reta de a
  const dist = (p: Pt) => Math.abs((p.x - a[0].x) * da.y - (p.y - a[0].y) * da.x);
  if (dist(b[0]) > NEAR && dist(b[1]) > NEAR) return false;
  if (Math.min(dist(b[0]), dist(b[1])) > NEAR) return false;
  // sobreposição das projeções ao longo de a
  const proj = (p: Pt) => (p.x - a[0].x) * da.x + (p.y - a[0].y) * da.y;
  const la = len(sub(a[1], a[0]));
  const [b0, b1] = [proj(b[0]), proj(b[1])].sort((m, n) => m - n) as [number, number];
  return Math.min(la, b1) - Math.max(0, b0) > NEAR * 2;
}

/**
 * Cada linha devolvida com o deslocamento de faixa em cada trecho compartilhado.
 * ``gap`` é a distância entre eixos (a espessura do traço mais um respiro).
 */
export function metroLines(lines: Line[], gap: number): Line[] {
  const segs = lines.map((l) => l.points.slice(1).map((p, i) => [l.points[i]!, p] as [Pt, Pt]));
  return lines.map((line, li) => {
    const offsets = segs[li]!.map((seg) => {
      const group = [line.id];
      lines.forEach((other, oi) => {
        if (oi !== li && segs[oi]!.some((s) => shared(seg, s) || shared(s, seg))) group.push(other.id);
      });
      if (group.length < 2) return 0;
      group.sort((m, n) => m - n);
      return (group.indexOf(line.id) - (group.length - 1) / 2) * gap;
    });
    // O sentido da normal acompanha o sentido do trecho: duas linhas que saem da loja
    // no mesmo rumo ficam do mesmo lado de quem as compara.
    const shifted = segs[li]!.map(([p, q], i) => {
      const d = unit(sub(q, p));
      const n = { x: -d.y, y: d.x };
      const o = offsets[i]!;
      return [{ x: p.x + n.x * o, y: p.y + n.y * o }, { x: q.x + n.x * o, y: q.y + n.y * o }] as [Pt, Pt];
    });
    if (!shifted.length) return line;
    const points: Pt[] = [shifted[0]![0]];
    for (let i = 0; i < shifted.length - 1; i++) {
      // a junta: onde os dois trechos deslocados se cruzam (ou o meio, se paralelos)
      const [a0, a1] = shifted[i]!;
      const [b0, b1] = shifted[i + 1]!;
      const r = sub(a1, a0), s = sub(b1, b0);
      const den = r.x * s.y - r.y * s.x;
      if (Math.abs(den) < 1e-6) points.push({ x: (a1.x + b0.x) / 2, y: (a1.y + b0.y) / 2 });
      else {
        const t = ((b0.x - a0.x) * s.y - (b0.y - a0.y) * s.x) / den;
        points.push({ x: a0.x + r.x * t, y: a0.y + r.y * t });
      }
    }
    points.push(shifted[shifted.length - 1]![1]);
    // As pontas (a loja e a parada) não se mexem: a linha encosta no círculo.
    points[0] = line.points[0]!;
    points[points.length - 1] = line.points[line.points.length - 1]!;
    return { id: line.id, points };
  });
}
