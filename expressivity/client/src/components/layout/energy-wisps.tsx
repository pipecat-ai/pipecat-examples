import { useEffect, useRef } from "react";

import { usePerceptionStore } from "@/stores/perception-store";
import { MODELS } from "@/types/perception";

/** How far above its place the drawing reaches, in pixels, so a wisp can arc over the cards. */
const BLEED = 120;
/** Wisps to each card, and the straight pieces each is drawn in. */
const WISPS = 9;
const PIECES = 48;
/** How strongly a card's wisps show: at rest, once its reading is in, and while audio is on its way. */
const LEVEL_IDLE = 0.16;
const LEVEL_READ = 0.42;
const LEVEL_FLOWING = 1;
/** How quickly a card's wisps take a new strength, per second. */
const EASE = 5;
/** The most a wisp rises above the top of its card, in pixels. */
const HEADROOM = 64;
/** How far under the top of its place a wisp turns back, with its sway, to stay off the header. */
const CLEARANCE = 18;
const TAU = Math.PI * 2;

/** One wisp's own character, fixed when the page loads. */
interface Wisp {
  /** Where it leaves the orb, in degrees up from straight right. */
  leaveDegrees: number;
  /** Whether it enters its card at the side, rather than over the top. Only the nearer card's can. */
  entersSide: boolean;
  /** Where along the card's edge it arrives, from 0 to 1. */
  arrivesAt: number;
  /** How far it billows out of the orb before turning, as a share of the orb's radius. */
  reach: number;
  /** How high it comes over the card before dropping in, from 0 to 1 of the room there is. */
  lift: number;
  /** Its sway: how wide, how many waves along it, where in the wave it starts, how fast it drifts. */
  sway: number;
  waves: number;
  phase: number;
  drift: number;
  /** How fast its bright pulses run along it, and where the first one starts. */
  pace: number;
  offset: number;
  /** Its thickness in pixels, and which of the tone's two colours it takes. */
  width: number;
  colour: 0 | 1;
}

/** Where the orb and the cards are, measured against the drawing's place. */
interface Geometry {
  width: number;
  height: number;
  orb: { x: number; y: number; radius: number };
  cards: { left: number; top: number; width: number; height: number }[];
}

/** The same random numbers every time, so the wisps keep their shapes from one visit to the next. */
function seeded(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let mixed = Math.imul(state ^ (state >>> 15), 1 | state);
    mixed = (mixed + Math.imul(mixed ^ (mixed >>> 7), 61 | mixed)) ^ mixed;
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
  };
}

function makeWisps(card: number): Wisp[] {
  const random = seeded(7 + card * 101);
  const between = (low: number, high: number) => low + random() * (high - low);
  return Array.from({ length: WISPS }, (_, index) => {
    const entersSide = card === 0 && index % 3 === 0;
    return {
      // A wisp for the card's side leaves the orb's side. The rest leave higher up, the farther
      // card's highest, and arc over the nearer card.
      leaveDegrees: entersSide
        ? between(-14, 20)
        : card === 0
          ? between(26, 50)
          : between(44, 68),
      entersSide,
      arrivesAt: between(0.12, 0.7),
      reach: entersSide ? between(0.05, 0.3) : between(0.1, 0.45),
      lift: between(0.35, 1),
      sway: entersSide ? between(4, 9) : between(5, 14),
      waves: between(1.2, 2.6),
      phase: between(0, TAU),
      drift: between(0.5, 1.3),
      pace: between(0.22, 0.42),
      offset: random(),
      width: between(0.8, 2),
      colour: index % 2 === 0 ? 0 : 1,
    };
  });
}

const smoothstep = (edge: number, value: number) => {
  const t = Math.min(Math.max(value / edge, 0), 1);
  return t * t * (3 - 2 * t);
};

/** How strongly a model's wisps show right now. */
function levelFor(model: (typeof MODELS)[number]): number {
  const { phase, readings, missed } = usePerceptionStore.getState();
  if (phase === "hearing") return LEVEL_FLOWING;
  if (phase === "reading" && !readings[model] && !missed[model]) {
    return LEVEL_FLOWING;
  }
  return readings[model] ? LEVEL_READ : LEVEL_IDLE;
}

/**
 * Wisps of light that drift out of the orb and into each model's card: the
 * same audio, going to both. Each is a thread that sways as it goes, with
 * brighter pulses running along it from the orb to the card. They are faint
 * at rest, bright while a turn is heard, and stay bright towards a card
 * whose model is still reading while the other's settle.
 *
 * Where a pulse lands there is a bloom of light, and the card is told how
 * much is landing and where, so its top edge lights up there too.
 *
 * Drawn on a canvas over the element it is placed in, behind what follows
 * it there, from where that element's `data-signal-source` and
 * `data-signal-target` descendants are. Side by side only: stacked, the
 * controls sit between the orb and the cards. With reduced motion the wisps
 * are drawn still.
 */
export function EnergyWisps() {
  // The drawing, whose parent is measured.
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const frame = canvas?.parentElement;
    const context = canvas?.getContext("2d");
    if (!canvas || !frame || !context) return;
    const source = frame.querySelector("[data-signal-source]");
    const targets = [...frame.querySelectorAll("[data-signal-target]")];
    if (!source || targets.length === 0) return;
    // The tone's two colours are set on the page's scope, and fade from one tone to the next there.
    const scope = canvas.closest(".tone-scope") ?? document.documentElement;
    const isStill = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    const wisps = targets.map((_, card) => makeWisps(card));
    const levels = targets.map(() => LEVEL_IDLE);
    // How much light each card's edge is showing, and whereabouts along it.
    const received = targets.map(() => 0);
    const receivedAt = targets.map(() => 0.4);
    // Each card's wisps keep their own time, which runs faster the brighter they are.
    const clocks = targets.map((_, card) => card * 3.7);
    let geometry: Geometry | null = null;
    let scale = 1;

    const measure = () => {
      const box = frame.getBoundingClientRect();
      const orb = source.getBoundingClientRect();
      scale = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(box.width * scale);
      canvas.height = Math.round((box.height + BLEED) * scale);
      geometry = {
        width: box.width,
        height: box.height,
        orb: {
          x: orb.left - box.left + orb.width / 2,
          y: orb.top - box.top + orb.height / 2,
          radius: orb.width / 2,
        },
        cards: targets.map((target) => {
          const card = target.getBoundingClientRect();
          return {
            left: card.left - box.left,
            top: card.top - box.top,
            width: card.width,
            height: card.height,
          };
        }),
      };
    };
    // An observer reports each element once as it starts watching, so the first measure comes from it too.
    const observer = new ResizeObserver(measure);
    for (const element of [frame, source, ...targets]) {
      observer.observe(element);
    }

    const drawWisp = (
      wisp: Wisp,
      card: number,
      level: number,
      clock: number,
      colours: [string, string],
      shape: Geometry,
    ) => {
      const { orb } = shape;
      const target = shape.cards[card];
      if (!target) return 0;
      const angle = (wisp.leaveDegrees * Math.PI) / 180;
      const outX = Math.cos(angle);
      const outY = -Math.sin(angle);
      // It starts inside the orb's glow, billows outward, then turns for its card.
      const startX = orb.x + orb.radius * 0.72 * outX;
      const startY = orb.y + orb.radius * 0.72 * outY;
      const firstX = orb.x + orb.radius * (1.1 + wisp.reach) * outX;
      // How far above the card a wisp may go: the page's header is not far over it.
      const ceiling = Math.max(
        Math.min(target.top - HEADROOM, orb.y - orb.radius),
        CLEARANCE,
      );
      const firstY = Math.max(
        orb.y + orb.radius * (1.1 + wisp.reach) * outY,
        ceiling,
      );
      let endX: number;
      let endY: number;
      let secondX: number;
      let secondY: number;
      if (wisp.entersSide) {
        // In at the card's side, level.
        endX = target.left + 6;
        endY = target.top + target.height * (0.1 + wisp.arrivesAt * 0.5);
        secondX = endX - orb.radius * 0.3;
        secondY = endY;
      } else {
        // Over the top of the card, as high as there is room for, then down into it.
        endX = target.left + target.width * wisp.arrivesAt;
        endY = target.top + 6;
        secondX = endX - target.width * 0.12;
        secondY = Math.max(endY - 24 - wisp.lift * 70, ceiling);
      }

      const pulse = ((clock * wisp.pace + wisp.offset) % 1) * 1.4 - 0.2;
      let fromX = startX;
      let fromY = startY;
      for (let piece = 1; piece <= PIECES; piece += 1) {
        const t = piece / PIECES;
        const u = 1 - t;
        const x =
          u * u * u * startX +
          3 * u * u * t * firstX +
          3 * u * t * t * secondX +
          t * t * t * endX;
        const y =
          u * u * u * startY +
          3 * u * u * t * firstY +
          3 * u * t * t * secondY +
          t * t * t * endY;
        // Which way it is heading here, to sway across it.
        const headingX =
          3 * u * u * (firstX - startX) +
          6 * u * t * (secondX - firstX) +
          3 * t * t * (endX - secondX);
        const headingY =
          3 * u * u * (firstY - startY) +
          6 * u * t * (secondY - firstY) +
          3 * t * t * (endY - secondY);
        const length = Math.hypot(headingX, headingY) || 1;
        // The sway is nothing at either end, so every wisp leaves the orb and reaches its card where it should.
        const sway =
          wisp.sway *
          Math.sin(Math.PI * t) *
          (Math.sin(wisp.waves * TAU * t + wisp.phase - clock * wisp.drift) +
            0.45 *
              Math.sin(
                wisp.waves * 2.3 * TAU * t + wisp.phase * 2 + clock * 0.7,
              ));
        const toX = x - (headingY / length) * sway;
        const toY = y + (headingX / length) * sway;

        // It comes up out of the orb, thins towards the card, and is brightest where a pulse is.
        const distance = (t - pulse) / 0.07;
        const glow = Math.exp(-0.5 * distance * distance);
        const alpha =
          level * smoothstep(0.14, t) * (1 - 0.65 * t) * (0.2 + 0.95 * glow);
        if (alpha > 0.004) {
          context.strokeStyle = colours[wisp.colour];
          context.beginPath();
          context.moveTo(fromX, fromY);
          context.lineTo(toX, toY);
          // A wide, faint stroke for its haze, and a fine one for its thread.
          context.globalAlpha = Math.min(alpha * 0.16, 1);
          context.lineWidth = wisp.width * (5 + 5 * glow);
          context.stroke();
          context.globalAlpha = Math.min(alpha, 1);
          context.lineWidth = wisp.width * (1 + 0.8 * glow);
          context.stroke();
        }
        fromX = toX;
        fromY = toY;
      }

      // How much of a pulse is landing on the card right now, and a bloom of light where it does.
      const landing = (1 - pulse) / 0.12;
      const arrival = level * Math.exp(-0.5 * landing * landing);
      if (arrival > 0.01) {
        const radius = 14 + 34 * arrival;
        const bloom = context.createRadialGradient(
          endX,
          endY,
          0,
          endX,
          endY,
          radius,
        );
        bloom.addColorStop(0, colours[wisp.colour]);
        bloom.addColorStop(1, "transparent");
        context.globalAlpha = Math.min(arrival * 0.55, 1);
        context.fillStyle = bloom;
        context.fillRect(endX - radius, endY - radius, radius * 2, radius * 2);
      }
      return arrival;
    };

    /** Tell a card how much is landing on it and where, for its edge to light up (lane-card in index.css). */
    const receive = (
      target: Element,
      amount: number,
      at: number,
      colour: string,
    ) => {
      if (!(target instanceof HTMLElement)) return;
      target.style.setProperty("--receive", amount.toFixed(3));
      target.style.setProperty("--receive-at", `${(at * 100).toFixed(1)}%`);
      target.style.setProperty("--receive-colour", colour);
    };

    let last = performance.now();
    let request = 0;
    const draw = (now: number) => {
      request = requestAnimationFrame(draw);
      const elapsed = Math.min((now - last) / 1000, 0.05);
      last = now;
      // Hidden where the page is stacked: nothing to draw.
      if (!geometry || canvas.offsetParent === null) return;

      const style = getComputedStyle(scope);
      const colours: [string, string] = [
        style.getPropertyValue("--tone-now").trim() || "#c4c4cc",
        style.getPropertyValue("--tone-now-2").trim() || "#8e8e99",
      ];
      context.setTransform(scale, 0, 0, scale, 0, BLEED * scale);
      context.clearRect(0, -BLEED, geometry.width, geometry.height + BLEED);
      // Light adds up where wisps cross.
      context.globalCompositeOperation = "lighter";
      context.lineCap = "butt";
      for (const [card, cardWisps] of wisps.entries()) {
        const wanted = levelFor(MODELS[card] ?? MODELS[0]);
        const before = levels[card] ?? LEVEL_IDLE;
        const level = before + (wanted - before) * Math.min(elapsed * EASE, 1);
        levels[card] = level;
        const clock =
          (clocks[card] ?? 0) + (isStill ? 0 : elapsed * (0.35 + level * 1.5));
        clocks[card] = clock;
        // What lands on the card's top edge, and whereabouts along it, weighing each wisp by how much of it is.
        let landed = 0;
        let along = 0;
        for (const wisp of cardWisps) {
          const arrival = drawWisp(wisp, card, level, clock, colours, geometry);
          if (!wisp.entersSide) {
            landed += arrival;
            along += arrival * wisp.arrivesAt;
          }
        }
        const target = targets[card];
        if (target) {
          // A little light whenever anything is flowing, and more with each pulse that lands.
          const amount = Math.min(level * 0.1 + landed * 0.26, 1);
          const before = received[card] ?? 0;
          const eased = before + (amount - before) * Math.min(elapsed * 14, 1);
          received[card] = eased;
          const at = landed > 0.001 ? along / landed : 0.4;
          const wasAt = receivedAt[card] ?? 0.4;
          const easedAt = wasAt + (at - wasAt) * Math.min(elapsed * 6, 1);
          receivedAt[card] = easedAt;
          receive(target, eased, easedAt, colours[0]);
        }
      }
    };
    request = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(request);
      observer.disconnect();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      // Taller than its place by the bleed, which is above it.
      style={{ top: -BLEED, height: `calc(100% + ${BLEED}px)` }}
      className="pointer-events-none absolute inset-x-0 hidden w-full lg:block"
    />
  );
}
