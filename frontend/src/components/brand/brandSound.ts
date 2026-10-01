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
/** A few milliseconds of difference, on top of the even letter spacing. */
const TICK_DELAY_MS = [0, 18, 8, 26, 11, 16];
const ONE_SHOTS = [whooshUrl, settleUrl];

const primed = new Map<string, HTMLAudioElement>();
let active: symbol | null = null;
let context: AudioContext | null = null;
let tickBuffers: AudioBuffer[] | null = null;
let accentBuffer: AudioBuffer | null = null;
let preparing: Promise<void> | null = null;

function preloadOneShots() {
  for (const src of ONE_SHOTS) {
    if (primed.has(src)) continue;
    const node = new Audio(src);
    node.preload = "auto";
    node.load();
    primed.set(src, node);
  }
}

async function decode(url: string, audio: AudioContext) {
  const response = await fetch(url);
  const data = await response.arrayBuffer();
  return audio.decodeAudioData(data);
}

function prepare() {
  if (!preparing) {
    preparing = (async () => {
      const audio = new AudioContext();
      context = audio;
      if (audio.state === "suspended") await audio.resume().catch(() => undefined);
      tickBuffers = await Promise.all(TICKS.map((url) => decode(url, audio)));
      accentBuffer = await decode(accentUrl, audio);
    })().catch(() => undefined);
  }
  return preparing;
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
  ready: () => Promise<void>;
  /** Queue every letter tick on the audio clock. A late frame cannot bunch them. */
  playLetters: (startSec: number, stepSec: number) => void;
  whoosh: () => void;
  settle: () => void;
  stop: () => void;
};

const silent: BrandSound = { ready: () => Promise.resolve(), playLetters() {}, whoosh() {}, settle() {}, stop() {} };

function level(cue: number) {
  return Math.min(1, Math.max(0, BRAND_SOUND.master * cue));
}

/** Starts only for the current intro. A second sign-in click does not stack another score. */
export function bindBrandSound(): BrandSound {
  if (active) return silent;
  const token = Symbol("brand-sound");
  active = token;
  preloadOneShots();
  const preparing = prepare();
  const voices: AudioBufferSourceNode[] = [];
  const timers: number[] = [];
  let lettersQueued = false;

  const onceWhoosh = { played: false };
  const onceSettle = { played: false };

  const cue = (buffer: AudioBuffer, at: number, gainValue: number) => {
    if (!context || active !== token) return;
    const gain = context.createGain();
    gain.gain.value = gainValue;
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(gain);
    gain.connect(context.destination);
    voices.push(source);
    try {
      source.start(at);
    } catch {
      /* The animation continues if playback is blocked. */
    }
  };

  return {
    ready: () => preparing,
    playLetters(startSec, stepSec) {
      if (active !== token || lettersQueued) return;
      lettersQueued = true;
      if (context && context.state === "running" && tickBuffers && accentBuffer) {
        const base = context.currentTime + startSec;
        tickBuffers.forEach((buffer, index) => {
          const at = base + index * stepSec + (TICK_DELAY_MS[index] ?? 0) / 1000;
          cue(buffer, at, level(BRAND_SOUND.tick));
          if (index === tickBuffers!.length - 1 && accentBuffer) cue(accentBuffer, at, level(BRAND_SOUND.accent));
        });
        return;
      }
      TICKS.forEach((src, index) => {
        const ms = (startSec + index * stepSec) * 1000 + (TICK_DELAY_MS[index] ?? 0);
        timers.push(window.setTimeout(() => {
          if (active !== token) return;
          play(src, BRAND_SOUND.tick);
          if (index === TICKS.length - 1) play(accentUrl, BRAND_SOUND.accent);
        }, ms));
      });
    },
    whoosh() {
      if (onceWhoosh.played) return;
      onceWhoosh.played = true;
      play(whooshUrl, BRAND_SOUND.whoosh);
    },
    settle() {
      if (onceSettle.played) return;
      onceSettle.played = true;
      play(settleUrl, BRAND_SOUND.settle);
    },
    stop() {
      if (active !== token) return;
      active = null;
      for (const timer of timers) window.clearTimeout(timer);
      for (const source of voices) {
        try {
          source.stop();
        } catch {
          /* Already finished. */
        }
      }
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
