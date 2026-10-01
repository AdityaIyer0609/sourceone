import { useEffect, useRef, useState } from "react";
import { animate, motion } from "motion/react";
import { bindBrandSound } from "./brandSound";

const WORD = "PLENZA";
const SUBTITLE = "by HCP Plastene Bulkpack Limited";
const LETTER_EASE = [0.22, 1, 0.36, 1] as const;
const FLIGHT_SAMPLES = 24;
const LETTER_START = 0.3;
const LETTER_STEP = 0.2;
const LETTER_SETTLE = 0.45;
const WORD_DONE = LETTER_START + (WORD.length - 1) * LETTER_STEP + LETTER_SETTLE;
const SUBTITLE_IN = 0.45;
const SUBTITLE_HOLD = 1;
const SUBTITLE_OUT = 0.32;
const SUBTITLE_ON = WORD_DONE;
const SUBTITLE_GONE = SUBTITLE_ON + SUBTITLE_IN + SUBTITLE_HOLD;
const PIN_AT = SUBTITLE_GONE + SUBTITLE_OUT + 0.06;
const FLY_AT = PIN_AT + 0.05;
const FLIGHT = 0.74;
const LAND_AT = FLY_AT + FLIGHT;
const REVEAL = 0.72;
const FINISH_AT = LAND_AT + REVEAL;
function flightCurve(t: number) {
  return 1 - (1 - t) ** 3;
}

/** Scale and glow stay full, then ease down over the last part of the flight. */
function lateFade(t: number) {
  if (t <= 0.46) return 0;
  return flightCurve((t - 0.46) / 0.54);
}

function wordShadow(fade: number) {
  const keep = 1 - fade;
  return `0 0 ${(18 * keep).toFixed(2)}px rgba(213,222,227,${(0.55 * keep).toFixed(3)}), 0 0 ${(42 * keep).toFixed(2)}px rgba(176,196,208,${(0.35 * keep).toFixed(3)})`;
}

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Sidebar wordmark, including when the mobile drawer is translated off-screen. */
function destinationRect(mark: HTMLElement): DOMRect {
  const rect = mark.getBoundingClientRect();
  const onScreen = rect.left >= 0 && rect.right <= window.innerWidth && rect.width > 0;
  if (onScreen) return rect;
  const sidebar = mark.closest(".sidebar");
  if (!(sidebar instanceof HTMLElement)) return rect;
  const sidebarRect = sidebar.getBoundingClientRect();
  return new DOMRect(
    sidebar.offsetLeft + (rect.left - sidebarRect.left),
    sidebar.offsetTop + (rect.top - sidebarRect.top),
    rect.width,
    rect.height,
  );
}

async function waitForKings() {
  if (!document.fonts?.load) return;
  await Promise.race([
    document.fonts.load("400 92px Kings").then(() => document.fonts.ready),
    new Promise((resolve) => window.setTimeout(resolve, 1200)),
  ]);
}

export function BrandIntro({ onReveal, onDone }: { onReveal: () => void; onDone: () => void }) {
  const markRef = useRef<HTMLDivElement>(null);
  const veilRef = useRef<HTMLDivElement>(null);
  const glowRef = useRef<HTMLDivElement>(null);
  const [word, setWord] = useState("");
  const [subtitleOn, setSubtitleOn] = useState(false);
  const [subtitleGone, setSubtitleGone] = useState(false);
  const [reducedClear, setReducedClear] = useState(false);
  const onRevealRef = useRef(onReveal);
  const onDoneRef = useRef(onDone);
  onRevealRef.current = onReveal;
  onDoneRef.current = onDone;

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.brandEnter = "1";
    const reduced = prefersReducedMotion();
    let raf = 0;
    let cancelled = false;
    let flight: { stop: () => void } | null = null;
    let glowFlight: { stop: () => void } | null = null;
    let pinned = false;
    let revealed = false;
    let tracking = false;
    let finished = false;
    let wordCount = -1;
    let revealX = window.innerWidth / 2;
    let revealY = window.innerHeight / 2;
    let revealCover = 24;

    const finish = () => {
      if (finished) return;
      finished = true;
      delete root.dataset.brandEnter;
      onDoneRef.current();
    };

    if (reduced) {
      setWord(WORD);
      setSubtitleOn(true);
      setReducedClear(true);
      onRevealRef.current();
      const timer = window.setTimeout(finish, 180);
      return () => {
        cancelled = true;
        window.clearTimeout(timer);
        if (!finished) delete root.dataset.brandEnter;
      };
    }

    const sound = bindBrandSound();

    const pin = () => {
      const mark = markRef.current;
      if (!mark || pinned) return;
      const rect = mark.getBoundingClientRect();
      mark.classList.add("is-pinned");
      mark.style.left = `${rect.left}px`;
      mark.style.top = `${rect.top}px`;
      mark.style.width = `${rect.width}px`;
      pinned = true;
    };

    const fly = () => {
      const mark = markRef.current;
      const glow = glowRef.current;
      const target = document.querySelector("[data-brand-mark]");
      if (!mark || !(target instanceof HTMLElement) || flight) return;
      sound.whoosh();
      const from = mark.getBoundingClientRect();
      const dest = destinationRect(target);
      const dx = dest.left - from.left;
      const dy = dest.top - from.top;
      const scale = from.width > 0 ? dest.width / from.width : 1;
      const times = Array.from({ length: FLIGHT_SAMPLES + 1 }, (_, index) => index / FLIGHT_SAMPLES);
      const travel = times.map(flightCurve);
      const fade = times.map(lateFade);
      flight = animate(
        mark,
        {
          x: travel.map((progress) => dx * progress),
          y: travel.map((progress) => dy * progress),
          scale: fade.map((progress) => 1 + (scale - 1) * progress),
          textShadow: fade.map(wordShadow),
        },
        { duration: FLIGHT, times, ease: "linear" },
      );
      if (!glow || glowFlight) return;
      tracking = true;
      const glowRect = glow.getBoundingClientRect();
      const current = Number(getComputedStyle(glow).opacity) || 1;
      const glowX = dest.left + dest.width / 2 - (glowRect.left + glowRect.width / 2);
      const glowY = dest.top + dest.height / 2 - (glowRect.top + glowRect.height / 2);
      glowFlight = animate(
        glow,
        {
          x: travel.map((progress) => glowX * progress),
          y: travel.map((progress) => glowY * progress),
          scale: fade.map((progress) => 1 + (0.4 - 1) * progress),
          opacity: fade.map((progress) => current * (1 - progress)),
        },
        { duration: FLIGHT, times, ease: "linear" },
      );
    };

    const openVeil = (t: number) => {
      const veil = veilRef.current;
      if (!veil) return;
      const progress = Math.min(1, (t - LAND_AT) / REVEAL);
      const radius = revealCover + (Math.hypot(window.innerWidth, window.innerHeight) - revealCover) * flightCurve(progress);
      const feather = 28 + 56 * flightCurve(progress);
      const mask = `radial-gradient(circle at ${revealX}px ${revealY}px, transparent ${radius}px, #000 ${radius + feather}px)`;
      veil.style.maskImage = mask;
      veil.style.setProperty("-webkit-mask-image", mask);
    };

    const step = (now: number, started: number) => {
      const t = (now - started) / 1000;
      const nextWord = t < LETTER_START ? 0 : Math.min(WORD.length, Math.floor((t - LETTER_START) / LETTER_STEP) + 1);
      if (nextWord !== wordCount) {
        wordCount = nextWord;
        setWord(WORD.slice(0, nextWord));
      }
      if (t >= SUBTITLE_ON) setSubtitleOn(true);
      if (t >= SUBTITLE_GONE) setSubtitleGone(true);
      const glow = glowRef.current;
      if (glow && !tracking) {
        glow.style.opacity = String(0.58 + 0.42 * (0.5 + 0.5 * Math.sin((t / 3.2) * Math.PI * 2)));
      }
      if (t >= PIN_AT) pin();
      if (t >= FLY_AT) fly();
      if (t >= LAND_AT && !revealed) {
        revealed = true;
        sound.settle();
        const target = document.querySelector("[data-brand-mark]");
        if (target instanceof HTMLElement) {
          const dest = destinationRect(target);
          revealX = dest.left + dest.width / 2;
          revealY = dest.top + dest.height / 2;
          revealCover = Math.hypot(dest.width, dest.height) / 2 + 6;
        }
        if (markRef.current) markRef.current.style.visibility = "hidden";
        delete root.dataset.brandEnter;
        openVeil(t);
        onRevealRef.current();
      } else if (revealed) {
        openVeil(t);
      }
      if (t >= FINISH_AT) {
        finish();
        return;
      }
      raf = requestAnimationFrame((frame) => step(frame, started));
    };

    void Promise.all([waitForKings(), sound.ready()]).then(() => {
      if (cancelled) return;
      sound.playLetters(LETTER_START, LETTER_STEP);
      const started = performance.now();
      raf = requestAnimationFrame((frame) => step(frame, started));
    });

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      flight?.stop();
      glowFlight?.stop();
      sound.stop();
      if (!finished) delete root.dataset.brandEnter;
    };
  }, []);

  return (
    <div className="brand-intro" role="status" aria-live="polite" aria-label={`${WORD}. ${SUBTITLE}`}>
      <div className={`brand-intro__veil${reducedClear ? " is-clear" : ""}`} ref={veilRef}>
        <div className="brand-intro__glow" ref={glowRef} />
        <div className="brand-intro__grain" />
      </div>
      <div className="brand-intro__stage">
        <div className="brand-intro__lockup">
          <div className="brand-intro__mark" ref={markRef} aria-hidden="true">
            {word.split("").map((glyph, index) => (
              <motion.span
                key={`${glyph}-${index}`}
                initial={{ opacity: 0, y: 6, filter: "blur(8px)" }}
                animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                transition={{ duration: LETTER_SETTLE, ease: LETTER_EASE }}
              >
                {glyph}
              </motion.span>
            ))}
          </div>
          <motion.div
            className="brand-intro__sub"
            aria-hidden="true"
            initial={false}
            animate={{ opacity: subtitleOn && !subtitleGone ? 1 : 0 }}
            transition={{ duration: subtitleGone ? SUBTITLE_OUT : subtitleOn ? SUBTITLE_IN : 0, ease: LETTER_EASE }}
          >
            {SUBTITLE}
          </motion.div>
        </div>
      </div>
    </div>
  );
}
