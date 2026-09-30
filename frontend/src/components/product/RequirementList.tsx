export function RequirementList({ rows }: { rows: { key: string; label: string; value: string }[] }) {
  if (!rows.length) return null
  return (
    <div className="spec-grid">
      {rows.map((row) => (
        <div key={row.key}><small>{row.label}</small><strong>{row.value}</strong></div>
      ))}
    </div>
  )
}
