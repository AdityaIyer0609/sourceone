const KEY = "sourceone.deliveryPin";
const EVENT = "sourceone-delivery-pin";

export function readDeliveryPin() {
  const value = window.localStorage.getItem(KEY) ?? "";
  return /^[1-9][0-9]{5}$/.test(value) ? value : "";
}

export function saveDeliveryPin(pin: string) {
  if (/^[1-9][0-9]{5}$/.test(pin)) window.localStorage.setItem(KEY, pin);
  else window.localStorage.removeItem(KEY);
  window.dispatchEvent(new Event(EVENT));
}

export function onDeliveryPinChange(listener: () => void) {
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}
