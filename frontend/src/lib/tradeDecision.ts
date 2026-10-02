export type TradeAction = "place" | "negotiate" | "ask";

export function tradeDecision(
  match: { askingPrice: { amount: string }; availability: string; minimumQuantity: string; maximumQuantity: string | null },
  quantity: number,
  buyerPrice: string,
  baseline: string,
  several: boolean,
): { action: TradeAction; unit: string } {
  const asking = Number(match.askingPrice.amount);
  const buyer = Number(buyerPrice);
  const untouched = buyerPrice.trim() !== "" && Number.isFinite(buyer) && Math.abs(buyer - Number(baseline)) < 0.00005;
  const minimum = Number(match.minimumQuantity);
  const stock = match.maximumQuantity == null ? null : Number(match.maximumQuantity);
  const inRange = quantity >= minimum && stock != null && quantity <= stock;
  const sellable = match.availability !== "on_request" && inRange;
  if (match.availability === "on_request") return { action: "ask", unit: untouched ? match.askingPrice.amount : buyerPrice };
  if (!several) {
    if (untouched && sellable) return { action: "place", unit: match.askingPrice.amount };
    return { action: "negotiate", unit: buyerPrice };
  }
  if (untouched) {
    if (sellable) return { action: "place", unit: match.askingPrice.amount };
    return { action: "negotiate", unit: match.askingPrice.amount };
  }
  if (asking <= buyer && sellable) return { action: "place", unit: match.askingPrice.amount };
  return { action: "negotiate", unit: buyerPrice };
}
