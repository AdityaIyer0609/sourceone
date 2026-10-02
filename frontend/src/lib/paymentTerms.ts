/** Demo rates. Advance is cheaper. Later payment costs more, and 14 days is the longest term. */
export const PAYMENT_TERMS = [
  { value: "", label: "Not specified", basisPoints: 0 },
  { value: "Advance", label: "Advance · 1% less", basisPoints: -100 },
  { value: "1-2 days", label: "1–2 days late · 0.25% more", basisPoints: 25 },
  { value: "3-4 days", label: "3–4 days late · 0.50% more", basisPoints: 50 },
  { value: "5-7 days", label: "5–7 days late · 1% more", basisPoints: 100 },
  { value: "8-14 days", label: "8–14 days late · 1.5% more", basisPoints: 150 },
] as const;

function toUnits(amount: string): bigint {
  const [whole, fraction = ""] = amount.split(".");
  return BigInt(whole || "0") * 10000n + BigInt((fraction + "0000").slice(0, 4));
}

/** Unit price after the payment term, at 4 decimal places, half up. */
export function adjustUnitPrice(amount: string, terms: string): string {
  const points = PAYMENT_TERMS.find((item) => item.value === terms)?.basisPoints ?? 0;
  if (!points || !amount.trim()) return amount;
  const adjusted = toUnits(amount) * BigInt(10000 + points);
  const divisor = 10000n;
  let result = adjusted / divisor;
  if ((adjusted % divisor) * 2n >= divisor) result += 1n;
  const text = result.toString().padStart(5, "0");
  return `${text.slice(0, -4)}.${text.slice(-4)}`;
}
