// Gets the Kalorické tabulky food of a menu meal from the ffkt server (route /api/food in ffkt/app.py).
// The server holds the KT account, reads the meal from ffmenu.cz itself and creates each dish once.
const SERVER_URL = "https://ffkt.nks-hub.cz/";
// the KT scanner opens the food detail for QR codes starting with this (string qr_food_prefix in the app)
const QR_FOOD_PREFIX = "https://dine4fit.com/food/";
// same format as KEY in ffkt/app.py
const MEAL_KEY = /^\d+:\d{4}-\d\d-\d\d:\d+$/;

async function foodQr(key) {
  if (!MEAL_KEY.test(key)) throw new Error("jídlo na stránce se nepodařilo přečíst");
  const url = new URL("api/food", SERVER_URL);
  url.searchParams.set("key", key);
  const response = await fetch(url).catch(() => {
    throw new Error("server doplňku není dostupný");
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `${response.status} ${response.statusText}`);
  if (!data.url?.startsWith(QR_FOOD_PREFIX)) throw new Error("server vrátil neplatný odkaz");
  return data.url;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type !== "qr") return false;
  foodQr(message.key).then(
    (result) => sendResponse({ ok: true, result }),
    (error) => sendResponse({ ok: false, error: error.message }),
  );
  return true;
});
