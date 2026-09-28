export function ProductVisual({ glyph, dark = false }: { glyph: string; dark?: boolean }) {
  return (
    <div className={`product-visual ${dark ? "product-visual--dark" : ""}`}>
      <span className={`material-shape material-shape--${glyph.toLowerCase()}`} />
      <small>{glyph}</small>
    </div>
  );
}
