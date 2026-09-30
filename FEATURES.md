# Plenza features

A short picture of what the app does today. Supplier asking prices, the live market average, estimated freight, and the negotiated order price are stored separately.

## Who sees which screen

A role that cannot use a screen does not see it in the sidebar. New request is shown only to buyers.

| Screen | Buyer | Supplier | Pricing admin | Platform admin |
| --- | --- | --- | --- | --- |
| Marketplace, catalogue, live rates | Yes | Yes | Yes | Yes |
| Freight calculator | Yes | Yes | Yes | Yes |
| Purchase requests, negotiations, orders, tracking | Yes | Yes | — | — |
| Reorder and buyer dashboard | Yes | — | — | — |
| Item master, rate management, freight rules | — | — | Yes | Yes |
| User management | — | — | — | Yes |

## Buying a material

A buyer browses the catalogue, sends a purchase request, and negotiates with one supplier. An accepted offer becomes an order. The supplier confirms it, and both sides follow tracking. Buyers can reorder from a past order.

The bell lists work waiting on you: a negotiation that is your turn, an accepted offer that still needs an order, or a placed order the supplier has not confirmed.

## How price is built

The live rate and graph are the average of active supplier asking prices for that material. Freight is estimated only after a supplier and a delivery PIN are known, from saved lanes or road distance. The order view adds that freight, when it is known, and 18% GST to show an amount payable. The stored order total stays the negotiated material value.

The delivery PIN in the top bar is saved in this browser and filled in on freight, requests, negotiations, orders, and reorder.
