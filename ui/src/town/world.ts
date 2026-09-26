// Atlas Town: map layout and pixel drawing. Everything is drawn with fillRect at a 384x240
// logical resolution and scaled up with CSS (image-rendering: pixelated).

export const W = 384;
export const H = 240;

export interface Look {
  shirt: string;
  hair: string;
  hat?: string;
  crown?: boolean;
}

export interface Building {
  id: string;
  name: string;
  agents: string[];
  x: number;
  y: number;
  w: number;
  h: number;
  wall: string;
  trim: string;
  roof: string;
  door: { x: number; y: number };
  zone: { x0: number; x1: number; y0: number; y1: number }; // where its residents wander
}

export const LOOKS: Record<string, Look> = {
  atlas: { shirt: "#e0a93b", hair: "#3b2a1e", crown: true },
  schedule: { shirt: "#2f9e8f", hair: "#1e1e24" },
  inbox: { shirt: "#c8483d", hair: "#6b3b1f", hat: "#2c4f9e" },
  school: { shirt: "#7b5cc4", hair: "#e3c16f" },
  coop: { shirt: "#e07b39", hair: "#2a1b12", hat: "#3a3f55" },
  planner: { shirt: "#4c9a4a", hair: "#9a4b2a" },
  triage: { shirt: "#3a7bd5", hair: "#101014", hat: "#c8483d" },
};

export const COLORS: Record<string, string> = Object.fromEntries(
  Object.entries(LOOKS).map(([k, v]) => [k, v.shirt]),
);

export const BUILDINGS: Building[] = [
  { id: "clock", name: "Clock Tower", agents: ["schedule"], x: 44, y: 16, w: 40, h: 58,
    wall: "#b9a58a", trim: "#8a7760", roof: "#4f6d8f", door: { x: 64, y: 74 }, zone: { x0: 40, x1: 100, y0: 80, y1: 134 } },
  { id: "post", name: "Post Office", agents: ["inbox", "triage"], x: 292, y: 28, w: 58, h: 44,
    wall: "#d7c9a8", trim: "#a3906a", roof: "#b3473a", door: { x: 321, y: 72 }, zone: { x0: 286, x1: 356, y0: 78, y1: 96 } },
  { id: "hq", name: "Atlas HQ", agents: ["atlas"], x: 160, y: 60, w: 64, h: 74,
    wall: "#e8e1cf", trim: "#c9a24a", roof: "#2e3a5c", door: { x: 192, y: 134 }, zone: { x0: 166, x1: 218, y0: 138, y1: 150 } },
  { id: "green", name: "Greenhouse", agents: ["planner"], x: 14, y: 94, w: 56, h: 38,
    wall: "#a9d8cf", trim: "#4f8a7a", roof: "#cfeee6", door: { x: 42, y: 132 }, zone: { x0: 12, x1: 110, y0: 136, y1: 150 } },
  { id: "library", name: "Library", agents: ["school"], x: 40, y: 162, w: 62, h: 46,
    wall: "#c9b8d8", trim: "#7b64a0", roof: "#5a3f7a", door: { x: 71, y: 208 }, zone: { x0: 44, x1: 150, y0: 212, y1: 226 } },
  { id: "career", name: "Career Center", agents: ["coop"], x: 286, y: 160, w: 64, h: 48,
    wall: "#e3cdb1", trim: "#a9774a", roof: "#6b4a33", door: { x: 318, y: 208 }, zone: { x0: 236, x1: 350, y0: 212, y1: 226 } },
];

export const HOME: Record<string, Building> = Object.fromEntries(
  BUILDINGS.flatMap((b) => b.agents.map((a) => [a, b])),
);

const TREES: [number, number][] = [
  [112, 26], [132, 44], [248, 22], [262, 46], [364, 20], [22, 30], [110, 94], [126, 118],
  [246, 104], [262, 122], [126, 176], [150, 196], [236, 176], [250, 198], [366, 176], [18, 190],
  [370, 96], [96, 70], [8, 226], [376, 226],
];
const FLOWERS: [number, number, string][] = [
  [100, 138, "#f06b8a"], [104, 132, "#ffd166"], [258, 138, "#ffd166"], [262, 132, "#f06b8a"],
  [150, 226, "#9ad0ff"], [226, 226, "#f06b8a"], [140, 84, "#ffd166"], [236, 84, "#9ad0ff"],
];

type Ctx = CanvasRenderingContext2D;
const rect = (c: Ctx, x: number, y: number, w: number, h: number, color: string) => {
  c.fillStyle = color;
  c.fillRect(Math.round(x), Math.round(y), w, h);
};

// --- ground -------------------------------------------------------------------------------
export function drawGround(c: Ctx, t: number) {
  rect(c, 0, 0, W, H, "#5d8f3c");
  for (let y = 0; y < H; y += 8)
    for (let x = (y / 8) % 2 ? 0 : 8; x < W; x += 16) rect(c, x, y, 8, 8, "#62953f");
  // streets and footpaths
  const path = "#d9c48f", edge = "#bfa872";
  const road = (x: number, y: number, w: number, h: number) => {
    rect(c, x - 1, y - 1, w + 2, h + 2, edge);
    rect(c, x, y, w, h, path);
  };
  road(18, 142, 348, 8);          // main street
  road(56, 214, 280, 8);          // south street
  road(188, 134, 8, 88);          // avenue
  road(152, 134, 80, 16);         // plaza
  road(60, 74, 8, 70);            // clock tower
  road(317, 72, 8, 72);           // post office
  road(38, 132, 8, 12);           // greenhouse
  road(67, 208, 8, 8);            // library
  road(314, 208, 8, 8);           // career center
  // pond
  rect(c, 310, 100, 46, 26, "#3b6fa8");
  rect(c, 312, 98, 42, 30, "#3b6fa8");
  const shimmer = Math.floor(t / 600) % 3;
  rect(c, 318 + shimmer * 6, 106, 8, 1, "#8cc0ee");
  rect(c, 334 - shimmer * 4, 116, 6, 1, "#8cc0ee");
  // fountain in the plaza
  rect(c, 186, 138, 12, 8, "#9aa7b8");
  rect(c, 188, 139, 8, 6, "#5fa2dd");
  rect(c, 191, 136 - (Math.floor(t / 250) % 2), 2, 3, "#bfe0ff");
  for (const [x, y, col] of FLOWERS) {
    rect(c, x, y, 2, 2, col);
    rect(c, x + 3, y + 2, 2, 2, col);
    rect(c, x + 1, y + 4, 2, 2, "#ffffff");
  }
}

export function drawTrees(c: Ctx) {
  for (const [x, y] of TREES) {
    rect(c, x - 5, y + 8, 12, 3, "rgba(0,0,0,0.18)");
    rect(c, x, y + 4, 3, 6, "#6b4a2b");
    rect(c, x - 5, y - 4, 13, 9, "#2f6b2f");
    rect(c, x - 3, y - 7, 9, 4, "#2f6b2f");
    rect(c, x - 3, y - 4, 5, 3, "#3f8a3a");
  }
}

// --- buildings ------------------------------------------------------------------------------
export function drawBuilding(c: Ctx, b: Building, lit: boolean, active: boolean, closed: boolean, t: number) {
  const { x, y, w, h } = b;
  rect(c, x + 3, y + h - 2, w, 5, "rgba(0,0,0,0.2)");         // shadow
  const roofH = b.id === "clock" ? 14 : 12;
  rect(c, x, y + roofH, w, h - roofH, b.wall);
  rect(c, x, y + h - 3, w, 3, b.trim);
  // stepped roof
  for (let i = 0; i < roofH; i++) {
    const inset = Math.max(0, roofH - i - 6);
    rect(c, x - 3 + inset, y + i, w + 6 - inset * 2, 1, i % 3 === 0 ? shade(b.roof) : b.roof);
  }
  // windows
  for (const [wx, wy] of windowsOf(b)) {
    rect(c, wx - 1, wy - 1, 7, 6, b.trim);
    rect(c, wx, wy, 5, 4, windowColor(lit, active));
  }
  // door
  rect(c, b.door.x - 5, y + h - 13, 10, 10, b.trim);
  rect(c, b.door.x - 4, y + h - 12, 8, 9, closed ? "#3a2a22" : "#5b3b28");
  rect(c, b.door.x + 2, y + h - 8, 1, 1, "#e6c35a");
  if (closed) {  // CLOSED sign
    rect(c, b.door.x - 7, y + h - 18, 14, 5, "#c0392b");
    rect(c, b.door.x - 5, y + h - 16, 10, 1, "#f5d0c5");
  }
  decorate(c, b, t, active);
}

export function windowColor(lit: boolean, active: boolean): string {
  return lit ? (active ? "#ffe07a" : "#f3c969") : active ? "#cfe3ff" : "#3c4d6b";
}

/** Top-left corners of a building's 5x4 window panes. */
export function windowsOf(b: Building): [number, number][] {
  const roofH = b.id === "clock" ? 14 : 12;
  const rows = Math.max(1, Math.floor((b.h - roofH - 18) / 12));
  const out: [number, number][] = [];
  for (let r = 0; r < rows; r++)
    for (let wx = b.x + 6; wx + 6 < b.x + b.w - 4; wx += 12) {
      if (Math.abs(wx + 3 - b.door.x) < 8 && r === rows - 1) continue;
      out.push([wx + 1, b.y + roofH + 6 + r * 12]);
    }
  return out;
}

function shade(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const f = (v: number) => Math.max(0, Math.round(v * 0.82));
  return `rgb(${f(n >> 16)},${f((n >> 8) & 255)},${f(n & 255)})`;
}

function decorate(c: Ctx, b: Building, t: number, active: boolean) {
  const { x, y, w } = b;
  if (b.id === "clock") {  // clock face with moving hand
    const cx = x + w / 2, cy = y + 22;
    rect(c, cx - 6, cy - 6, 13, 13, "#6b5a45");
    rect(c, cx - 5, cy - 5, 11, 11, "#f4ecd8");
    const a = (t / 1000) * (active ? 6 : 0.6);
    for (let i = 0; i < 4; i++) rect(c, cx + Math.round(Math.cos(a) * i), cy + Math.round(Math.sin(a) * i), 1, 1, "#222");
    rect(c, cx, cy - 3, 1, 3, "#222");
  } else if (b.id === "post") {  // mailbox + flag
    rect(c, b.door.x + 12, b.door.y - 9, 6, 5, "#2c4f9e");
    rect(c, b.door.x + 14, b.door.y - 4, 2, 4, "#555");
    if (active) rect(c, b.door.x + 18, b.door.y - 11, 1, 4, "#e74c3c");
    rect(c, x + 8, y + 14, w - 16, 5, "#f4ecd8");
    rect(c, x + 10, y + 16, w - 20, 1, "#b3473a");
  } else if (b.id === "hq") {  // tower, flag, gold trim
    rect(c, x + w / 2 - 10, y - 14, 20, 16, b.wall);
    rect(c, x + w / 2 - 12, y - 18, 24, 5, b.roof);
    rect(c, x + w / 2, y - 30, 1, 13, "#555");
    const wave = Math.floor(t / 300) % 2;
    rect(c, x + w / 2 + 1, y - 30 + wave, 8, 5, "#e0a93b");
    rect(c, x + w / 2 - 6, y - 8, 12, 6, active ? "#ffe07a" : "#3c4d6b");
    rect(c, x, y + 30, w, 2, b.trim);
  } else if (b.id === "green") {  // glass panes + plants
    for (let gx = x + 4; gx < x + w - 2; gx += 8) rect(c, gx, y + 12, 1, 26, "#4f8a7a");
    rect(c, x + 6, y + 30, 6, 4, "#3f8a3a");
    rect(c, x + w - 14, y + 30, 6, 4, "#3f8a3a");
  } else if (b.id === "library") {  // columns + book sign
    for (const cx of [x + 6, x + w - 10]) rect(c, cx, y + 14, 4, 30, "#efe6f5");
    rect(c, x + w / 2 - 6, y + 15, 12, 6, "#f4ecd8");
    rect(c, x + w / 2 - 1, y + 15, 2, 6, "#7b64a0");
  } else if (b.id === "career") {  // briefcase sign
    rect(c, x + w / 2 - 7, y + 14, 14, 9, "#6b4a33");
    rect(c, x + w / 2 - 3, y + 12, 6, 2, "#6b4a33");
    rect(c, x + w / 2 - 6, y + 17, 12, 1, "#e0a93b");
  }
}

// --- people and birds -----------------------------------------------------------------------
export function drawPerson(c: Ctx, x: number, y: number, look: Look, frame: number, faded: boolean, selected: boolean) {
  const px = Math.round(x) - 3, py = Math.round(y) - 11;
  c.globalAlpha = faded ? 0.55 : 1;
  if (selected) {
    rect(c, px - 2, py + 11, 11, 2, "#ffe07a");
    rect(c, px - 1, py + 13, 9, 1, "#ffe07a");
  } else {
    rect(c, px - 1, py + 11, 9, 2, "rgba(0,0,0,0.22)");
  }
  const skin = "#f1c9a0", pants = faded ? "#6d6f7a" : "#34384f";
  const shirt = faded ? "#8a8d98" : look.shirt;
  // legs
  if (frame % 2) {
    rect(c, px + 1, py + 8, 2, 3, pants);
    rect(c, px + 4, py + 8, 2, 2, pants);
  } else {
    rect(c, px + 1, py + 8, 2, 2, pants);
    rect(c, px + 4, py + 8, 2, 3, pants);
  }
  // body and arms
  rect(c, px, py + 4, 7, 4, shirt);
  rect(c, px - 1, py + 5, 1, 2, skin);
  rect(c, px + 7, py + 5, 1, 2, skin);
  // head
  rect(c, px + 1, py, 5, 4, skin);
  rect(c, px + 1, py - 1, 5, 2, look.hair);
  rect(c, px + 2, py + 2, 1, 1, "#222");
  rect(c, px + 4, py + 2, 1, 1, "#222");
  if (look.hat) rect(c, px, py - 2, 7, 2, look.hat);
  if (look.crown) {
    rect(c, px + 1, py - 3, 5, 1, "#f5c542");
    rect(c, px + 1, py - 4, 1, 1, "#f5c542");
    rect(c, px + 3, py - 4, 1, 1, "#f5c542");
    rect(c, px + 5, py - 4, 1, 1, "#f5c542");
  }
  c.globalAlpha = 1;
}

export function drawLetter(c: Ctx, x: number, y: number, color: string) {
  rect(c, x - 3, y - 2, 7, 5, "#fbf6e9");
  rect(c, x - 3, y - 2, 7, 1, color);
  rect(c, x - 1, y, 3, 1, "#c9bda0");
}

export function drawSparkle(c: Ctx, x: number, y: number, age: number, color: string) {
  const r = Math.round(age * 6);
  c.globalAlpha = 1 - age;
  for (const [dx, dy] of [[r, 0], [-r, 0], [0, r], [0, -r]]) rect(c, x + dx, y + dy, 1, 1, color);
  c.globalAlpha = 1;
}

/** 0 by day, up to ~0.5 at night, following the viewer's local clock. */
export function darkness(date: Date): number {
  const h = date.getHours() + date.getMinutes() / 60;
  if (h >= 7 && h < 18) return 0;
  if (h >= 18 && h < 20.5) return ((h - 18) / 2.5) * 0.5;
  if (h >= 5.5 && h < 7) return ((7 - h) / 1.5) * 0.5;
  return 0.5;
}
