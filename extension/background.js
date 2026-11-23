// Creates each FF Menu meal as a Kalorické tabulky food, the way "Přidat novou potravinu" in the KT app does,
// so the scanner of the KT app can open it from a QR code (protocol of KT Android 3.14.71).
if (typeof md5 === "undefined") importScripts("md5.js");

const KT_URL = "https://www.dine4fit.com/";
// app version code and client id that the Android app sends with every request
const APP_PARAMS = { v: "621", pid: "aNdV2wl7" };
// 450 = logged out, 451 = token of another user (legacy API), 401 = JSON API without a valid hash
const SESSION_LOST = new Set([401, 450, 451]);
// waits between attempts after "503 No server is available" from KT's load balancer (see RETRY_DELAYS in ffkt/kt.py)
const RETRY_DELAYS_MS = [2000, 5000];
// the KT scanner opens the food detail for QR codes starting with this (string qr_food_prefix in the app)
const QR_FOOD_PREFIX = "https://dine4fit.com/food/";
// "Jídla a přílohy / Hotové pokrmy a polotovary" in GET api/v2/food-suggestion/category/list
const READY_MEALS_CATEGORY = 1026;
// conversion factor used by the KT app itself (DataTool.convert)
const KJ_PER_KCAL = 4.1871;

class KTError extends Error {
  constructor(code, message) {
    super(`${code}: ${message}`);
    this.code = code;
  }
}

function field(xml, name) {
  const match = xml.match(new RegExp(`<${name}>([^<]*)</${name}>`));
  if (!match) return null;
  return match[1].replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&amp;/g, "&");
}

async function fetchRetrying(url, init) {
  for (const delay of [...RETRY_DELAYS_MS, null]) {
    const response = await fetch(url, init);
    if (response.status !== 503 || delay === null) return response;
    await new Promise((resolve) => setTimeout(resolve, delay));
  }
}

async function login(email, passwordMd5) {
  const url = new URL("login.api.php", KT_URL);
  for (const [name, value] of Object.entries({ Email: email, Pass: passwordMd5, ...APP_PARAMS })) {
    url.searchParams.set(name, value);
  }
  const response = await fetchRetrying(url);
  const xml = await response.text();
  if (!response.ok) throw new KTError(response.status, response.statusText);
  const code = Number(field(xml, "code"));
  if (!(code >= 200 && code < 300)) throw new KTError(code, field(xml, "msg") || "");
  const hash = field(xml, "hash");
  if (!hash) throw new KTError(0, "přihlášení nevrátilo hash uživatele");
  return hash;
}

async function session(fresh) {
  const stored = await chrome.storage.local.get(["email", "passwordMd5", "hash"]);
  if (!stored.email || !stored.passwordMd5) {
    throw new KTError(0, "v nastavení doplňku chybí přihlášení do Kalorických tabulek");
  }
  if (stored.hash && !fresh) return stored.hash;
  const hash = await login(stored.email, stored.passwordMd5);
  await chrome.storage.local.set({ hash });
  return hash;
}

async function withSession(call) {
  try {
    return await call(await session(false));
  } catch (error) {
    if (!SESSION_LOST.has(error.code)) throw error;
    return call(await session(true));
  }
}

function wrap(ctx, text, width) {
  const lines = [""];
  for (const word of text.split(" ")) {
    const candidate = lines[lines.length - 1] ? `${lines[lines.length - 1]} ${word}` : word;
    if (ctx.measureText(candidate).width > width && lines[lines.length - 1]) lines.push(word);
    else lines[lines.length - 1] = candidate;
  }
  return lines;
}

// KT accepts a new food only with photos; FF Menu boxes have no nutrition table, so the photo is a card
// with the menu values and where they come from
async function sourceCard(meal) {
  const canvas = new OffscreenCanvas(900, 560);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#111";
  ctx.font = "bold 34px sans-serif";
  const title = wrap(ctx, `FF Menu: ${meal.name}`, 840);
  title.forEach((line, i) => ctx.fillText(line, 30, 60 + i * 44));
  ctx.font = "30px sans-serif";
  [
    `1 porce: ${meal.kj} kJ (${Math.round(meal.kj / KJ_PER_KCAL)} kcal)`,
    `Bílkoviny ${meal.protein} g, Sacharidy ${meal.carbs} g, Tuky ${meal.fat} g`,
    `Vláknina ${meal.fiber} g, Cholesterol ${meal.cholesterol} mg`,
    "Cukry a sůl FF Menu neuvádí.",
    `Zdroj: ${meal.source}`,
  ].forEach((line, i) => ctx.fillText(line, 30, 90 + title.length * 44 + i * 56));
  return canvas.convertToBlob({ type: "image/jpeg", quality: 0.9 });
}

// The body mirrors OkHttp's: "data" is a JSON field without a filename, then the three photos the app
// sends (package, nutrition table, ingredients). FormData would add filename="blob" to "data".
function multipart(data, photo) {
  const boundary = `ffkt${crypto.randomUUID().replaceAll("-", "")}`;
  const parts = [`--${boundary}\r\nContent-Disposition: form-data; name="data"\r\n`
    + `Content-Type: application/json; charset=utf-8\r\n\r\n${JSON.stringify(data)}`];
  for (const n of [1, 2, 3]) {
    parts.push(`\r\n--${boundary}\r\nContent-Disposition: form-data; name="images"; filename="ffmenu-${n}.jpg"\r\n`
      + "Content-Type: image/jpeg\r\n\r\n", photo);
  }
  parts.push(`\r\n--${boundary}--\r\n`);
  return { body: new Blob(parts), type: `multipart/form-data; boundary=${boundary}` };
}

async function createFood(hash, meal, title) {
  // FF Menu gives values per portion without its weight, so one portion is declared as 100 g.
  // KT rejects a food without category, sugar and salt; FF Menu publishes neither of the two, so they are 0.
  const { body, type } = multipart({
    title,
    foodstuff_type_id: READY_MEALS_CATEGORY,
    unit_name: "porce",
    unit_multiplier: "100",
    foodstuff_unit: "100g",
    energy: String(meal.kj),
    energy_unit: "kj",
    protein: String(meal.protein),
    carbohydrate: String(meal.carbs),
    sugar: "0",
    fat: String(meal.fat),
    salt: "0",
    fiber: String(meal.fiber),
    cholesterol: String(meal.cholesterol),
  }, await sourceCard(meal));
  const response = await fetchRetrying(new URL("api/v1/food-suggestion/foodstuff?force=true", KT_URL), {
    method: "POST",
    headers: { hash, version: APP_PARAMS.v, pid: APP_PARAMS.pid, lang: "cs", "Content-Type": type },
    body,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new KTError(response.status, data.error || data.message || response.statusText);
  if (!data.foodstuff_guid) throw new KTError(0, "Kalorické tabulky nevrátily ID nové potraviny");
  return data.foodstuff_guid;
}

function validMeal(meal) {
  const numbers = ["kj", "protein", "carbs", "fat", "fiber", "cholesterol"];
  return meal && typeof meal.name === "string" && meal.name.trim() && typeof meal.source === "string"
    && numbers.every((n) => Number.isFinite(meal[n]) && meal[n] >= 0);
}

async function foodQr(meal) {
  if (!validMeal(meal)) throw new KTError(0, "jídlo na stránce se nepodařilo přečíst");
  // the same dish comes back in later weeks with the same values; it reuses its food
  const values = [meal.name, meal.kj, meal.protein, meal.carbs, meal.fat, meal.fiber, meal.cholesterol];
  const key = `food:${md5(JSON.stringify(values))}`;
  let guid = (await chrome.storage.local.get(key))[key];
  if (!guid) {
    // the portion energy tells programs apart; KT answers 500 for a title it already has, so a repeat
    // (another user's food, or this dish created before the browser data was cleared) gets a suffix
    const title = `FF Menu: ${meal.name} (${meal.kj} kJ)`;
    try {
      guid = await withSession((hash) => createFood(hash, meal, title));
    } catch (error) {
      if (error.code !== 500) throw error;
      guid = await withSession((hash) => createFood(hash, meal, `${title} · ${crypto.randomUUID().slice(0, 4)}`));
    }
    await chrome.storage.local.set({ [key]: guid });
  }
  return QR_FOOD_PREFIX + guid;
}

async function credentialsSet() {
  const { email, passwordMd5 } = await chrome.storage.local.get(["email", "passwordMd5"]);
  return Boolean(email && passwordMd5);
}

const handlers = {
  qr: (m) => foodQr(m.meal),
  status: () => credentialsSet(),
  login: async () => Boolean(await session(true)),
  openOptions: () => chrome.runtime.openOptionsPage(),
};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const handler = handlers[message.type];
  if (!handler) return false;
  Promise.resolve(handler(message))
    .then((result) => sendResponse({ ok: true, result }))
    .catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});

chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());
