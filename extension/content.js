// Meal keys equal Meal.key in ffkt/ffmenu.py: "<product_variant_id>:<YYYY-MM-DD>:<card index in the day>".
const MONTHS = ["ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září",
  "října", "listopadu", "prosince"];
// the factor the KT app converts with, so the page shows the kcal the app will show
const KJ_PER_KCAL = 4.1871;

function currentVariant() {
  const fromUrl = new URL(location.href).searchParams.get("product_variant_id");
  if (fromUrl) return fromUrl;
  const active = document.querySelector("a.btn-outline-secondary.active[href*='product_variant_id']");
  return active ? new URL(active.href).searchParams.get("product_variant_id") : null;
}

function isoDay(text) {
  const match = text.replace(/\s+/g, " ").match(/(\d{1,2})\.\s*(\S+)\s+(\d{4})/);
  const month = match ? MONTHS.indexOf(match[2]) + 1 : 0;
  return month ? `${match[3]}-${String(month).padStart(2, "0")}-${match[1].padStart(2, "0")}` : null;
}

function mealCards(variant) {
  return [...document.querySelectorAll(".section-h3")].flatMap((header) => {
    const date = isoDay(header.textContent);
    const cards = [...(header.nextElementSibling?.querySelectorAll(".position-relative.product-select-container") ?? [])];
    return date ? cards.map((card, slot) => ({ card, key: `${variant}:${date}:${slot}` })) : [];
  });
}

function setBox(box, state, text) {
  box.dataset.state = state;
  box.replaceChildren(Object.assign(document.createElement("p"), { className: "ffkt-note", textContent: text }));
}

async function fillQr(box, key) {
  setBox(box, "busy", "Hledám jídlo v Kalorických tabulkách…");
  const response = await chrome.runtime.sendMessage({ type: "qr", key });
  if (!response.ok) {
    setBox(box, "error", `Nepodařilo se: ${response.error}`);
    const retry = Object.assign(document.createElement("button"), { type: "button", textContent: "Zkusit znovu" });
    retry.addEventListener("click", () => fillQr(box, key));
    box.append(retry);
    return;
  }
  const qr = qrcode(0, "M");
  qr.addData(response.result);
  qr.make();
  setBox(box, "done", "Naskenuj v aplikaci Kalorické tabulky, 100 g = 1 porce");
  box.insertAdjacentHTML("afterbegin", qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true }));
}

function showKcal(card) {
  const energy = card.querySelector(".text-large");
  const kj = Number((energy?.textContent || "").replace(/\s/g, "").match(/^\d+/)?.[0]);
  if (!kj) return;
  const kcal = Object.assign(document.createElement("span"), {
    className: "ffkt-kcal", textContent: ` (${Math.round(kj / KJ_PER_KCAL)} kcal)`,
  });
  energy.append(kcal);
}

// the server finds or creates the Kalorické tabulky food only for the meals whose QR code is asked for
function offerQr(box, key) {
  box.dataset.state = "idle";
  const show = Object.assign(document.createElement("button"), {
    type: "button", textContent: "Zobrazit QR pro Kalorické tabulky",
  });
  show.addEventListener("click", () => fillQr(box, key));
  box.replaceChildren(show);
}

function init() {
  const variant = currentVariant();
  for (const { card, key } of variant ? mealCards(variant) : []) {
    showKcal(card);
    const box = Object.assign(document.createElement("div"), { className: "ffkt-qr" });
    box.dataset.key = key;
    card.append(box);
    offerQr(box, key);
  }
}

init();
