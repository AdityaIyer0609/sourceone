export function Sparkline({ down = false, large = false }: { down?: boolean; large?: boolean }) {
  return (
    <svg className={`sparkline ${large ? "sparkline--large" : ""} ${down ? "is-down" : ""}`} viewBox="0 0 110 34" aria-hidden="true">
      <path d={down ? "M2 7 C18 4 18 16 34 13 S54 17 64 18 S82 15 108 29" : "M2 27 C18 29 19 20 34 22 S54 10 66 15 S85 14 108 3"} />
    </svg>
  );
}
