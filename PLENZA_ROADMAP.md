# Plenza roadmap

Persistent product roadmap. Future sessions should read this file and continue from the recommended next phase. Do not rebuild what is already marked complete.

Last inspected: 30 Sep 2026, against the current FastAPI backend and React frontend. No features in this file have been started by writing this document.

## Current architecture

- Backend: FastAPI, SQLAlchemy, PostgreSQL, Alembic. Frontend: React, TypeScript, Vite. UI follows the existing Plenza screens. Extend `app/models`, `app/*/service.py`, and `app/api/v1` rather than adding a second stack.
- Auth: email and password, JWT bearer. Permissions are enforced on the server with `Actor.require`. The sidebar only hides screens; it is not the security boundary.
- Roles today: `platform_admin`, `pricing_admin`, `buyer`, `supplier`. Permissions in use: `pricing.view`, `pricing.edit`, `pricing.publish`, `pricing.configure`, `identity.manage`, `freight.manage`, `negotiation.buy`, `negotiation.supply`, `order.place`, `order.fulfil`.
- Organisations exist (`organisations`: code, name, type `platform|buyer|supplier`, active flag, optional dispatch PIN and label). Users belong to one organisation.
- Plenza owns catalogue products, specifications, supplier listings, asking-price averages, purchase requests, negotiations and versions, orders and status events, and freight rules. ERP is a read-only SQL Server `SELECT` into source rates. There is no ERP write, sync-back, BOM, stock, invoice, or ERP-user import. Do not copy ERP prices into supplier asking prices or freight rules.
- Price layers stay separate in storage: published benchmark, supplier asking price, asking-price average, estimated freight, negotiated offer, order `agreed_unit_price`. Order `total_value` is constrained to `round(quantity * agreed_unit_price, 2)` and must stay the material value.
- Buyer-facing market rate is the average of active eligible asking prices when those listings exist (`asking_price_averages`, overlaid on product and benchmark reads). Series with no listings keep the published benchmark. Averages are recorded when a listing is created or activated. History ranges already exist: 1D, 7D, 1M (30), 3M (90), 1Y.
- Freight estimates use saved lanes first (`freight_rules`, plus defaults). Road distance is a separate basis and only runs through the configured routing provider, with PIN coordinates and PIN-pair distances cached. Unknown distance or no rule returns freight on request. Do not invent kilometres.
- One accepted negotiation can become one order. Negotiation versions are append-only. Order status events are append-only. Fulfilment is one step at a time: placed → confirmed → processing → ready → dispatched → delivered, or cancel from placed/confirmed.

## Current completed capabilities

- Discover: marketplace, catalogue, product detail, specifications on the product, product documents, product questions and answers.
- Compare suppliers on a product: active listings show organisation, origin PIN/label, asking price, minimum quantity, and availability (`in_stock`, `limited`, `on_request`). One listing per supplier per product.
- RFQ, partial: a buyer creates a purchase request for one product, quantity, UOM, destination PIN, and message, selects one or more suppliers who list that product, and sends it. Send opens one negotiation per supplier at that supplier's asking price. It does not create an order. Cancelling the request cancels negotiations that are not already accepted.
- Negotiate: offer, counter, accept, reject, cancel. Each offer is a new `NegotiationVersion`. The room keeps the version list. A benchmark or asking-average snapshot is frozen on the negotiation and is not the offer price.
- Order: buyer places an order only from an accepted negotiation. Supplier confirms and advances status. Buyer can cancel while placed or confirmed. Tracking is the status timeline.
- Reorder: buyer can start a reorder from an eligible past order. Reorder reads the current asking average when listings exist, otherwise the published series.
- Live rates and history graph, including movement against the previous point. Admin benchmark publish, four-eyes, and pricing audit remain for series that are not driven by listings.
- Freight calculator, admin freight rules, defaults, and a per-kg road-distance rate. Negotiation and order can store destination PIN, freight status, amount, match, and basis. The amount is never added into `total_value`.
- Display-only amount payable on the order: material + estimated freight when known + 18% GST. The 18% figure is a frontend constant in `pricingFormat.ts`, not a tax record and not from ERP.
- Buyer dashboard: active orders, open negotiations, pending actions, spend as the sum of non-cancelled order material totals, recent orders and negotiations, reorder flag.
- Top bar: delivery PIN saved in this browser only (`localStorage`, not a user column). Bell lists real rows only: your turn on an open negotiation, an accepted buyer negotiation with no order, a supplier order still `placed`.
- Admin: item master, rate management, freight admin, user create/activate/role for platform admin.
- Role-based navigation. Buyers do not see admin screens. Admins do not see trading screens they cannot call.

## Current known limitations

- No supplier profile, verification state, response-time, on-time, acceptance, cancellation, quality, or dispute metrics. Do not invent them.
- Supplier choice is "has an active listing", not a match explanation. No lead time on a listing.
- Purchase request has no required date, payment terms, or specification checklist. Send does not pass `destination_pin` into `create_negotiation`, so the opened negotiation does not currently snapshot the request PIN or a freight estimate. Freight on the request response is calculated live by `freight_for`.
- No side-by-side comparison of supplier offers on one request. The buyer works each negotiation separately.
- Landed cost is an estimate beside the negotiation, not a stored commercial term. GST is not configurable and is not applied in the database.
- No supplier price-spread view and no quote-versus-market comparison beyond the frozen snapshot already shown in a negotiation.
- No approver, procurement, or finance role. No threshold. Placing an order does not wait for approval. Audit exists for benchmark publishing, not for the trading flow.
- Documents and specifications belong to the catalogue product. They are not attached to a request, negotiation, or order. No COA, MTC, LR, e-way bill, packing list, or POD record.
- Buyer dashboard is not a procurement command center. Spend is material `total_value` only. No savings, variance, or delivery-performance figures.
- Tracking has no transporter, vehicle, LR, ETA, delay reason, or GPS. A note on a status event is the only extra text.
- No supplier dashboard. Suppliers use the same negotiation, order, and tracking screens. Listing create/update exists on the API; there is no dedicated supplier performance page.
- Delivery PIN is per browser, not per user or organisation.
- Notifications are derived on read. There is no notification table. Empty means nothing is waiting, not a fake alert.

## Recommended next phase

The ten phases in this file are complete. Do not start a new phase until one is written here.

When a phase is finished, change its status here and move this recommendation to the next phase that is not `COMPLETE`.

---

## 1. Supplier intelligence

**Status: COMPLETE**

Shipped as a read of the existing organisation, listings, negotiations, and orders. `GET /api/v1/suppliers/{organisationId}` is linked from a listing, purchase request, negotiation, order, tracking, and reorder. Verification is set by a platform admin. Service regions are declared by that supplier and do not replace the dispatch PIN. Response time, acceptance, and order cancellation include the counts behind any percentage, and stay unavailable when there is no denominator. On-time delivery and quality stay unavailable until phases 3 and 7 store a required date and dispute records. A supplier cannot open another supplier's profile. No ERP fields are on the profile.

**Objective.** A buyer can open a supplier and see who they are, what they sell, where they dispatch from, and performance calculated only from Plenza orders and negotiations.

**Existing functionality to reuse.** `Organisation` (name, type, dispatch PIN and label). `User` (name, email, active). `SupplierListing` for products, price, availability, minimum quantity. `Negotiation` and `NegotiationVersion` for quote history and who responded. `Order` and `OrderStatusEvent` for order history and timestamps of confirmed, dispatched, and delivered. Do not add a parallel supplier table that copies these rows.

**Backend / model / API.** Add supplier profile fields that are not already on the organisation (verification status and any service regions the supplier actually declares). Add a read API that aggregates, for one supplier organisation:

- products from active listings
- dispatch origin already stored
- response time from negotiation version timestamps (first supplier version after the buyer's offer)
- quote and order counts from negotiations and orders
- on-time delivery only where a required date exists; until phase 3 stores a required date, return this metric as unavailable, not as a percentage
- acceptance and cancellation counts from negotiation status and order cancellations
- quality and disputes only after phase 7 stores those events; until then, unavailable

Compute in a service on read, or store snapshots only when the underlying row changes. Never seed fake percentages.

**Frontend.** A supplier profile reached from a listing, request, negotiation, and order, using the current page layout. Show empty or "not enough history" instead of zeros that imply a measurement.

**Data / ownership.** Plenza-owned. ERP customer or vendor rows are not a supplier profile and must not be shown. Metrics are visible to buyers and to that supplier; another supplier does not see them.

**Dependencies.** None to start profiles and the metrics that already have source rows. On-time delivery waits on a required date (phase 3). Quality and disputes wait on phase 7.

**Acceptance criteria.**

- Profile shows real organisation, origin, and listings.
- Every percentage is traceable to stored negotiations or orders, and the API includes the counts behind it.
- A new supplier with no orders does not show 100% or 0% on-time.
- No ERP fields appear on the profile.

**Implementation notes.** Implemented in `app/suppliers/service.py` and `SupplierProfilePage`. Do not add a second supplier table. Verification is a Plenza status, not an ERP flag. Do not backfill history with demo numbers. Dispatch PIN remains the freight origin. On-time delivery and quality must stay unavailable until phases 3 and 7.

---

## 2. Smart supplier matching

**Status: COMPLETE**

`GET /api/v1/products/{productCode}/supplier-matches` returns only active listings. Each row explains the listing, minimum quantity, availability, dispatch PIN, saved-lane freight (or on request), and phase 1 rates, which stay "not calculated yet" when the source rows do not exist. Rows sort by asking price, then whether freight is estimated. There is no score. The purchase-request supplier picker and the product supply tab use this list. Road distance is not called. A supplier with no listing for the product is absent.

**Objective.** When a buyer states product, quantity, and destination, Plenza lists eligible suppliers and states the factual reason each one is included or excluded.

**Existing functionality to reuse.** `eligible_listings` (active listing, supplier has `negotiation.supply`). Listing availability and minimum quantity. Organisation dispatch PIN. `freight.estimate` (lane, then explicit road-distance basis). Do not add a score column.

**Backend / model / API.** A match query on top of listings: product, quantity, UOM, destination PIN. Return each candidate with reasons drawn from data, for example: lists this product, minimum quantity met or not, availability, freight estimated or on request, origin PIN. Lead time only if the listing gains a real lead-time field. Historical performance only by embedding phase 1 metrics, each marked unavailable when the source is missing. Sort by explicit keys the user can see (asking price, then freight status), not by a hidden rank.

**Frontend.** Use this list when choosing suppliers on a purchase request and on the product page. Show the reason next to each supplier. No "recommended" badge without those reasons.

**Data / ownership.** Read-only view over listings, freight, and phase 1 metrics. Matching does not create a negotiation.

**Dependencies.** Phase 1 for performance reasons. Freight estimate already exists. Lead time does not exist yet; omit it until a supplier records one.

**Acceptance criteria.**

- A supplier without an active listing for the product is absent, with no fabricated alternative.
- Each shown supplier has at least one concrete reason.
- Changing quantity or PIN changes freight or eligibility without inventing a distance.
- No numeric AI score.

**Implementation notes.** Implemented in `app/suppliers/matching.py`. Extend this read if lead time is added later. Do not create a second "RFQ supplier" entity or a numeric rank.

---

## 3. Advanced RFQ engine

**Status: COMPLETE**

The purchase request remains the RFQ. It now stores an optional required date, payment terms, freight basis, and a snapshot of the product specifications that had values when the request was created. Older requests keep a null required date and a null snapshot. Send copies the destination PIN, freight basis, required date, and payment terms onto each negotiation and still opens one negotiation per supplier without creating an order. The request screen compares asking price, latest offer, material value, frozen or live freight, and a landed estimate (material plus freight only). Counters stay in the negotiation room so versions remain append-only. An accepted row can place the order through the existing order API.

**Objective.** One buyer requirement can invite several suppliers, collect independent responses, compare them, and continue one accepted offer into the current negotiation version history and then one order.

**Already complete. Do not duplicate.**

- `PurchaseRequest` plus `PurchaseRequestSupplier`: product, quantity, UOM, destination PIN, message, many suppliers.
- Send creates one `Negotiation` per supplier and stores `negotiation_id` on the supplier row. Status moves draft → sent → in negotiation → converted or cancelled.
- Negotiations already support independent counters. Versions are immutable. Accept freezes `accepted_version_id`.
- Order create from that accepted version. One order per negotiation.
- Direct negotiation from the product page remains valid for a single chosen supplier.

**Gaps.**

- No required date. No payment terms. No specification set on the request (product specifications are catalogue-wide only).
- Send does not copy destination PIN or a freight snapshot onto the negotiation.
- No comparison of the latest offer, asking price, freight, and landed estimate across the suppliers on one request.
- Buyer still answers inside each negotiation room rather than from a comparison.

**Backend / model / API.** Add required date and payment terms on `PurchaseRequest` and copy them onto the negotiation as a snapshot. Pass `destination_pin` (and the freight basis the buyer chose) into `create_negotiation` inside `send_request`. Add a comparison read for one request: one row per supplier with latest version, negotiation status, frozen or live freight, and the material offer. Comparison is not a new offer table. Suppliers still respond through `POST /negotiations/{id}/offers`.

**Frontend.** Extend the purchase-request screen: required date, payment terms, and a comparison of responses. From a row, open the existing negotiation room or place the order when that negotiation is accepted. Keep the current room and version list.

**Data / ownership.** The request and its negotiations stay Plenza-owned. Suppliers see only their own negotiation, which is already how list visibility works. The buyer sees every supplier on their request.

**Dependencies.** Phase 4 for the landed columns in the comparison. Phase 2 can replace the manual supplier picker. Phase 1 metrics can appear as extra columns later. The RFQ itself does not wait on those.

**Acceptance criteria.**

- Sending still opens one negotiation per selected listing supplier and still does not create an order.
- Two suppliers can counter different prices; versions stay append-only.
- Comparison shows those prices side by side and links to the existing negotiation.
- Accepted offer still creates the order through the current order API.
- Required date, once stored, is the date phase 1 on-time delivery will use. Do not invent a date for old requests.

**Implementation notes.** Implemented on `PurchaseRequest` and `send_request`. Do not add an `Rfq` model. Landed estimate on the comparison is not GST and is not written onto the offer. `total_value` stays material only. On-time delivery in phase 1 can use `required_by` once an order stores that date; it is snapshotted on the negotiation but not yet on the order.

---

## 4. Total cost / landed cost

**Status: COMPLETE**

`app/pricing/charges.py` is the display rule: 18% GST extra on the material value, and on estimated freight when that freight is known. The purchase-request comparison and the order read both return material, freight, GST, the basis sentence, and payable. None of those figures is written onto the offer, `agreed_unit_price`, or `total_value`. Freight still comes only from a saved lane or an explicit road-distance estimate. Payment terms stay the text chosen on the request.

**Objective.** A buyer can see material, estimated freight, and a payable estimate separately, for one supplier and across suppliers, without freight ever becoming the order price.

**Already complete. Do not duplicate.**

- `freight.estimate`: saved lane match, else on request. Road distance only when basis is `distance` and the routing provider returns a kilometre value. Cache in `pin_coordinates` and `road_distances`.
- Negotiation and order store freight status, amount, match, and basis beside the price.
- Order UI shows material, estimated freight, GST 18%, and amount payable. `total_value` remains material.
- Product page and create-order modal can preview freight for a PIN.
- Admin maintains lanes, a default, and a per-kg distance rate.

**Gaps.**

- GST rate is a frontend constant, not stored commercial data, and is not configurable.
- Request send does not snapshot freight onto each negotiation (see phase 3).
- No single comparison payload of asking price + freight + payable per supplier.
- "Applicable commercial terms" beyond that GST display do not exist (payment terms are phase 3).

**Backend / model / API.** Keep `estimate` as the only freight calculator. Add a landed breakdown DTO used by the request comparison and the order read: material value, freight estimate or on request, tax lines that are actually configured, payable estimate. If GST stays 18% for now, store it as an explicit display rule with its basis (GST extra on material, plus freight when freight is estimated), not as a new price written onto the offer. Do not add freight into `agreed_unit_price` or `total_value`.

**Frontend.** Reuse the order cost block and the landed-cost preview. Put the same breakdown on the phase 3 comparison. Label freight and tax as estimates.

**Data / ownership.** Freight rules are Plenza data, never ERP freight. Failed routing returns on request.

**Dependencies.** Phase 3 comparison is the screen that needs the multi-supplier breakdown. Single-supplier estimate already works.

**Acceptance criteria.**

- A known lane returns that lane's amount. A missing lane does not invent one.
- Road distance is unchanged unless the user selects that basis and the provider returns kilometres.
- Order `total_value` still equals quantity times agreed unit price after any UI change.
- Material, freight, and payable are visible as separate figures.

**Implementation notes.** Implemented in `app/pricing/charges.py`. Do not add a Haversine fallback. Do not let a landed or payable figure overwrite a negotiation version or `total_value`. The 18% rate is a Plenza display rule, not an ERP tax code.

---

## 5. Price intelligence

**Status: COMPLETE**

The market view now includes the min and max of the same active asking prices used for the average. Fewer than two asks leaves the spread unavailable. A negotiation and a purchase-request comparison show the offer, the frozen snapshot, the current average, and each difference. A difference is omitted when either side is missing. None of these figures is written onto the offer.

**Objective.** Show the market from real asking prices, how it moved, how wide supplier prices are, and how an offer sits against that market. Keep benchmark, ask, negotiated price, and order price distinct.

**Already complete. Do not duplicate.**

- `AskingPriceAverage` recorded from active eligible listings. Current average, supplier count, and history points.
- Buyer product and benchmark reads overlay that average when listings or prior snapshots exist. No listings and no snapshots: published benchmark stays. Snapshots but no active listings: rate on request rather than a stale average presented as live.
- History ranges include 7 days, 30 days, and 90 days. Movement versus the previous point. Sparkline and live-rate chart.
- Negotiation stores the snapshot basis (`ASKING_AVERAGE` or the published benchmark basis) separately from `offered_price`.
- Admin publish and four-eyes still own benchmark rows. Listing changes do not publish a `BenchmarkRate`.

**Gaps.** None for this phase. Trend language stays movement versus the previous stored point. Do not add a forecast.

**Backend / model / API.** Extend the market view with spread from the same active listings used for the average. If fewer than two asks, spread is unavailable. Add offer-versus-market on the negotiation read: offered price, snapshot value, current average if one exists, and the difference. Omit the difference when either side is missing. Do not create a statistics row when `record()` skipped because nothing changed or because there are zero listings.

**Frontend.** On live rates and product detail, show the spread next to the average when it exists. On the negotiation and the phase 3 comparison, show offer against the snapshot and, separately, against the current average. Keep the existing captions that freight is not inside the average.

**Data / ownership.** Averages are Plenza data derived from listings. Published benchmarks remain admin-published reference rates. ERP source rates stay in the pricing admin timeline, not on the buyer average.

**Dependencies.** None for spread and quote comparison. Phase 3 is where the comparison screen should consume the quote-versus-market fields.

**Acceptance criteria.**

- One active ask: average equals that ask, spread unavailable.
- Two or more asks: spread equals the actual min and max.
- Deactivating the last listing does not invent a new average point.
- Offer, average, benchmark snapshot, and order price can all be named on one negotiation without being stored as the same number.

**Implementation notes.** History already carries forward the last point. Do not fill missing days with generated prices. Demo history that was seeded for testing is not a reason to synthesise points in the service.

---

## 6. Company accounts and approvals

**Status: COMPLETE**

A company threshold is a material amount and currency on the organisation. An order whose material `total_value` is above that amount is stored as an approval request and does not create an `orders` row until a different person in the same company, with `order.approve`, approves it. The threshold is not compared with the payable estimate. Declining leaves the negotiation accepted. Rejecting the deal cancels it. The approval row is the audit: who submitted, who decided, the threshold, the amount, and the negotiation.

**Objective.** A company has users with different jobs, and an order above a company threshold waits for an approver before it is placed. The decision is audited.

**Already complete. Do not duplicate.**

- Organisation, user, role, permission, user-role assignment.
- Platform admin can create a user, activate or deactivate, and assign a role.
- Server-side checks on every trading and admin action.
- Pricing audit events for benchmark edits and publish. Four-eyes already blocks a publisher from publishing their own edit when required.

**Gaps.** None for this phase. Procurement and finance are not separate roles; the approver role holds `order.approve`. The decision is stored on the approval request, not in the pricing audit table.

**Backend / model / API.** Add permissions such as `order.approve` rather than a second identity system. Allow more than one user on a buyer organisation, which the schema already allows. Store an organisation threshold (currency and amount, compared with material `total_value` unless the product decision explicitly says payable). On order create, if the amount is above the threshold, write an approval request and do not create the order until an approver in that organisation approves. Reject returns the negotiation to its accepted state so the buyer can change course without a fake order. Append an audit row: who submitted, who decided, threshold, amount, negotiation id.

**Frontend.** Company users and threshold on a screen the buyer admin can open, in the existing operations layout. Pending approvals in the buyer navigation. The current "place order" action becomes "submit for approval" when the threshold applies. Approvers get a real bell item from this queue, not a synthetic one.

**Data / ownership.** Thresholds and decisions are Plenza data. ERP users are not imported. An approver sees only their organisation's requests.

**Dependencies.** Current order-from-negotiation flow. The threshold is compared with the material `total_value`, not the payable estimate.

**Acceptance criteria.**

- Below the threshold, the buyer still places the order as today.
- Above it, no `orders` row exists until approval.
- The approver cannot approve their own submission when they are also the buyer (same four-eyes idea as benchmarks).
- Reject does not cancel the accepted negotiation unless the approver explicitly rejects the deal.
- Audit lists the decision after the fact.

**Implementation notes.** Do not split buyer organisations into a new tenant service. Extend `Organisation` and the order service.

---

## 7. Quality and documents

**Status: COMPLETE**

A negotiation stores the requirement rows at creation, copied from the purchase request when the request is sent. The order copies that snapshot and the database refuses a later change to it. The supplier answers each frozen requirement with met or not met. Fulfilment files live on the order, with a type and a status of submitted, accepted, or rejected. Only the buyer and supplier on that order can open a file. A row whose file is missing is left off the list. Rejected documents are the supplier quality count. Catalogue product files stay separate.

**Objective.** Requirements travel with the RFQ and the order, suppliers answer them, and fulfilment documents are stored with access limited to the parties.

**Already complete. Do not duplicate.**

- Product `specifications` JSON and the fixed display rows (grade, producer, MFI, density, application, quality, UOM, description).
- `ProductDocument` files for a catalogue product, hidden when inactive, uploaded by an authorised user.
- Product questions and supplier answers.

**Gaps.** None for this phase. There is still no separate dispute record. On-time delivery stays unavailable until an order stores a required date.

**Backend / model / API.** Snapshot the requirement rows onto the purchase request and copy that snapshot to the order. Supplier responses hang off the negotiation or the request-supplier row, not off the live product. Add an order document model: type, filename, uploader, status (submitted, accepted, rejected), and the parties allowed to read it. Reuse the product-document storage approach. Download checks buyer or supplier on that order, or a pricing admin only where the existing admin document APIs already apply. Do not mark a certificate present if no file was uploaded.

**Frontend.** Requirements on the request, negotiation, and order, using the current specification list style. Upload and review actions on the order. Missing documents stay an empty list.

**Data / ownership.** Files are Plenza files. Do not pull certificates from ERP. A supplier uploads only onto their own order. The other supplier on a different negotiation cannot read them.

**Dependencies.** Phase 3 for the request snapshot. Order documents can start from the existing order once the snapshot decision is made. Phase 1 quality metrics should count only accepted disputes or rejected documents stored here.

**Acceptance criteria.**

- Editing the product specification later does not change an existing order's requirements.
- A supplier can attach a typed document to their order and the buyer can open it.
- A user who is not a party receives a permission error.
- The UI never shows a certificate that has no stored file.

**Implementation notes.** Keep catalogue documents for product marketing files. Do not overload `ProductDocument` with LR and POD.

---

## 8. Procurement workspace and analytics

**Status: COMPLETE**

**Objective.** A buyer opens one workspace and sees open work, spend, supplier performance, and reorder signals computed from their own orders and negotiations.

**Already complete. Do not duplicate.**

- `GET /dashboard` for a buyer: active order count, open negotiations, open purchase requests, pending actions, material spend by currency from non-cancelled `total_value`, spend by product and supplier, variance against the negotiation snapshot, delivery only when a required date and a delivered event both exist, supplier rates from this buyer's rows, alerts matching the bell plus pending approvals, orders by status, five recent orders, five recent negotiations, reorder availability.
- Reorder list and start.
- Bell items derived from negotiations and orders.

**Gaps.** None for this phase. There is no separate price-trend chart. The supplier profile's on-time metric stays unavailable because the order row still has no required-date column; the dashboard delivery figure uses `negotiation.required_by` only. Visibility stays the existing buyer-user lists, not every user in the organisation.

**Backend / model / API.** `buyer_dashboard` was extended. No second analytics store and no migration. Variance is agreed unit price minus `benchmark_rate_snapshot`, and the order is omitted when that snapshot is null. Freight is not in the difference. Delivery is unavailable when no delivered order has a required date.

**Frontend.** `DashboardWorkspace` labels the spend card material spend and lists alerts, spend slices, variance, delivery, and supplier rates. Empty history stays empty.

**Data / ownership.** A buyer sees only their own rows. Suppliers do not see this buyer dashboard. Platform admins do not get a cross-tenant spend view.

**Dependencies.** Phase 1 rates, phase 3 required date, phase 6 approvals.

**Acceptance criteria.**

- Every figure on the page matches a query over that buyer's rows.
- Variance is omitted when the negotiation has no snapshot.
- No alert is created without an underlying negotiation or approval.
- Material spend is labelled as material spend.

**Implementation notes.** Cancelled orders stay out of spend. Freight is not averaged in.

---

## 9. Advanced shipment tracking

**Status: COMPLETE**

**Objective.** After dispatch, the order can record how it is moving, using only facts a user or a real integration supplied.

**Already complete. Do not duplicate.**

- Status machine and `OrderStatusEvent` (who, when, optional note), plus one supplier-set `in_transit` step between dispatched and delivered.
- Tracking screen and timeline show LR, transporter, vehicle, and ETA when the supplier saved them, and a POD link when that order document exists.
- Delay is shown only when `negotiation.required_by` is stored, that date has passed, and the order is not delivered or cancelled.
- Supplier advances one step. Buyer can cancel only before processing. No coordinates are stored or returned.

**Gaps.** None for this phase. The decorative route on the tracking screen is not a live position. There is still no GPS provider.

**Backend / model / API.** `orders.shipment_lr`, `shipment_transporter`, `shipment_vehicle`, and `shipment_eta` are written when the supplier marks dispatched, and can be corrected while the order is dispatched or in transit. The status event stays the audit of who moved the status. POD remains an `order_documents` row of type `pod`.

**Frontend.** `TrackingView`, the order timeline, and the order screen show the saved shipment and the delay sentence. Empty facts stay empty.

**Data / ownership.** The supplier on the order writes shipment facts. The buyer reads them.

**Dependencies.** Phase 3 required date. Phase 7 POD file.

**Acceptance criteria.**

- An order can move to delivered without LR, and the timeline shows the status with no fake LR.
- When LR and ETA are saved, both parties see them on tracking.
- Delay appears only when a required date is stored and has passed.
- No latitude or longitude is returned from this service.

**Implementation notes.** Do not replace `OrderStatusEvent`. Do not infer in transit from the clock.

---

## 10. Supplier workspace

**Status: COMPLETE**

**Objective.** A supplier has one place for work they must do: answer RFQs, negotiate, confirm orders, dispatch, maintain listings and prices, and see their own performance and documents.

**Already complete. Do not duplicate.**

- `GET /supplier-dashboard` counts requests awaiting this supplier, negotiations where it is their turn, placed orders, and listings that are inactive or on request. Those counts are the lengths of the lists on the same response.
- Alerts match the bell: your turn, and confirm a placed order. Empty when nothing is waiting.
- Performance is the phase 1 aggregate for the supplier's organisation. On-time delivery stays unavailable. Documents are the fulfilment files stored on their orders.
- `GET /listings` returns only that supplier's listings, including inactive ones. `PATCH /listings/{id}` can change asking price, minimum quantity, availability, and the active flag. A new asking-price average is recorded only when the active average changes. No benchmark is published.
- Supplier nav has this home and a listings screen. Actions open the existing request, negotiation, order, and listing screens.

**Gaps.** None for this phase. Suppliers still do not get rate management or freight admin.

**Backend / model / API.** `supplier_dashboard` sits beside `buyer_dashboard`. Listing updates stay on the listings service.

**Frontend.** `SupplierHome` and `ListingsWorkspace` use the same operations layout as the buyer dashboard.

**Data / ownership.** A supplier sees their own listings and the work assigned to them. They do not see another supplier's orders. The public asking-price average on a product remains visible with `pricing.view`.

**Dependencies.** Phase 1 performance. Phase 7 documents.

**Acceptance criteria.**

- Supplier home counts match the list APIs.
- Updating an asking price changes the listing and, when the average changes, the next market snapshot. It does not publish a benchmark.
- A supplier cannot open another supplier's orders.
- Empty queues render as empty, with no sample RFQ.

**Implementation notes.** Do not give suppliers rate-management or freight-admin screens.

---

## Working rules for every phase

- Inspect this file and the code before adding a model. If a section says complete, extend that service.
- RBAC stays on the server. New actions need a permission, not only a hidden button.
- ERP stays read-only forever.
- Do not fabricate metrics, distances, certificates, locations, savings, or alerts.
- Preserve the current Figma layout. New information goes into existing workspaces, modals, and tables.
- Freight and tax estimates never overwrite negotiated unit price or `total_value`.
- After finishing a phase, set its status to `COMPLETE` or leave it `PARTIAL` with the remaining gaps edited in place, and update "Recommended next phase".
