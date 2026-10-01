import accentUrl from "../../assets/brand-sound/accent.wav";
import settleUrl from "../../assets/brand-sound/settle.wav";
import tickA from "../../assets/brand-sound/tick-a.wav";
import tickE from "../../assets/brand-sound/tick-e.wav";
import tickL from "../../assets/brand-sound/tick-l.wav";
import tickN from "../../assets/brand-sound/tick-n.wav";
import tickP from "../../assets/brand-sound/tick-p.wav";
import tickZ from "../../assets/brand-sound/tick-z.wav";
import whooshUrl from "../../assets/brand-sound/whoosh.wav";

/** One place for how loud the brand moment is. Cues stay under this. */
export const BRAND_SOUND = {
  master: 0.42,
  tick: 0.62,
  accent: 0.5,
  whoosh: 0.55,
  settle: 0.38,
} as const;

const TICKS = [tickP, tickL, tickE, tickN, tickZ, tickA];
/** Extra delay after the letter appears, so the six ticks are not identical. */
const TICK_DELAY_MS = [0, 18, 8, 26, 11, 16];
const SOURCES = [...TICKS, accentUrl, whooshUrl, settleUrl];

const primed = new Map<string, HTMLAudioElement>();
let active: symbol | null = null;

function preload() {
  for (const src of SOURCES) {
    if (primed.has(src)) continue;
    const node = new Audio(src);
    node.preload = "auto";
    node.load();
    primed.set(src, node);
  }
}

function play(src: string, level: number) {
  try {
    const node = primed.get(src) ?? new Audio(src);
    node.pause();
    node.currentTime = 0;
    node.volume = Math.min(1, Math.max(0, BRAND_SOUND.master * level));
    const pending = node.play();
    if (pending) pending.catch(() => undefined);
  } catch {
    /* The animation continues if playback is blocked. */
  }
}

export type BrandSound = {
  letter: (index: number) => void;
  whoosh: () => void;
  settle: () => void;
  stop: () => void;
};

const silent: BrandSound = { letter() {}, whoosh() {}, settle() {}, stop() {} };

/** Starts only for the current intro. A second sign-in click does not stack another score. */
export function bindBrandSound(): BrandSound {
  if (active) return silent;
  const token = Symbol("brand-sound");
  active = token;
  preload();
  const timers: number[] = [];
  const heard = new Set<string>();

  const once = (key: string, run: () => void) => {
    if (active !== token || heard.has(key)) return;
    heard.add(key);
    run();
  };

  return {
    letter(index) {
      const src = TICKS[index];
      if (!src) return;
      const delay = TICK_DELAY_MS[index] ?? 0;
      const timer = window.setTimeout(() => {
        once(`tick-${index}`, () => play(src, BRAND_SOUND.tick));
        if (index === TICKS.length - 1) once("accent", () => play(accentUrl, BRAND_SOUND.accent));
      }, delay);
      timers.push(timer);
    },
    whoosh() {
      once("whoosh", () => play(whooshUrl, BRAND_SOUND.whoosh));
    },
    settle() {
      once("settle", () => play(settleUrl, BRAND_SOUND.settle));
    },
    stop() {
      if (active !== token) return;
      active = null;
      for (const timer of timers) window.clearTimeout(timer);
      for (const node of primed.values()) {
        try {
          node.pause();
          node.currentTime = 0;
        } catch {
          /* Already released. */
        }
      }
    },
  };
}
