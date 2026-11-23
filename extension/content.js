// Meal keys equal Meal.key in ffkt/ffmenu.py: "<product_variant_id>:<YYYY-MM-DD>:<card index in the day>".
const MONTHS = ["ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září",
  "října", "listopadu", "prosince"];
// the factor the KT app converts with, so the page shows the kcal the app will show
const KJ_PER_KCAL = 4.1871;

const send = (message) => chrome.runtime.sendMessage(message);

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

function number(text) {
  const match = (text || "").replace(/\s/g, "").replace(",", ".").match(/\d+(\.\d+)?/);
  return match ? Number(match[0]) : null;
}

function readMeal(card) {
  const values = {};
  for (const block of card.querySelectorAll(".headings-line-height")) {
    const label = block.querySelector("small")?.textContent.trim();
    if (label) values[label] = number(block.textContent.replace(label, ""));
  }
  return {
    name: card.querySelector(".mb-1.font-weight-bold")?.textContent.trim(),
    kj: number(card.querySelector(".text-large")?.textContent),
    protein: values["Bílkoviny"],
    carbs: values["Sacharidy"],
    fat: values["Tuky"],
    fiber: values["Vláknina"] ?? 0,
    cholesterol: values["Cholesterol"] ?? 0,
  };
}

function mealCards(variant) {
  return [...document.querySelectorAll(".section-h3")].flatMap((header) => {
    const date = isoDay(header.textContent);
    const cards = [...(header.nextElementSibling?.querySelectorAll(".position-relative.product-select-container") ?? [])];
    const source = `www.ffmenu.cz/jidelnicek, ${date}`;
    return date ? cards.map((card, slot) => ({
      card, key: `${variant}:${date}:${slot}`, meal: { ...readMeal(card), source },
    })) : [];
  });
}

function showBanner(text) {
  const banner = Object.assign(document.createElement("div"), { className: "ffkt-banner" });
  banner.textContent = `FF Menu do KT: ${text} `;
  const open = Object.assign(document.createElement("button"), { type: "button", textContent: "Otevřít nastavení" });
  open.addEventListener("click", () => send({ type: "openOptions" }));
  banner.append(open);
  document.querySelector("h1")?.after(banner);
}

function setBox(box, state, text) {
  box.dataset.state = state;
  box.replaceChildren(Object.assign(document.createElement("p"), { className: "ffkt-note", textContent: text }));
}

async function fillQr(box, meal) {
  setBox(box, "busy", "Hledám jídlo v Kalorických tabulkách…");
  const response = await send({ type: "qr", meal });
  if (!response.ok) {
    setBox(box, "error", `Nepodařilo se: ${response.error}`);
    const retry = Object.assign(document.createElement("button"), { type: "button", textContent: "Zkusit znovu" });
    retry.addEventListener("click", () => fillQr(box, meal));
    box.append(retry);
    return;
  }
  const qr = qrcode(0, "M");
  qr.addData(response.result);
  qr.make();
  setBox(box, "done", "Naskenuj v aplikaci Kalorické tabulky, 100 g = 1 porce");
  box.insertAdjacentHTML("afterbegin", qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true }));
}

function showKcal(card, kj) {
  const energy = card.querySelector(".text-large");
  if (!energy || !Number.isFinite(kj)) return;
  const kcal = Object.assign(document.createElement("span"), {
    className: "ffkt-kcal", textContent: ` (${Math.round(kj / KJ_PER_KCAL)} kcal)`,
  });
  energy.append(kcal);
}

// a food is found or created in Kalorické tabulky only for the meals whose QR code is asked for
function offerQr(box, meal) {
  box.dataset.state = "idle";
  const show = Object.assign(document.createElement("button"), {
    type: "button", textContent: "Zobrazit QR pro Kalorické tabulky",
  });
  show.addEventListener("click", () => fillQr(box, meal));
  box.replaceChildren(show);
}

async function init() {
  const variant = currentVariant();
  const meals = variant ? mealCards(variant) : [];
  if (!meals.length) return;

  for (const { card, key, meal } of meals) {
    showKcal(card, meal.kj);
    const box = Object.assign(document.createElement("div"), { className: "ffkt-qr" });
    box.dataset.key = key;
    card.append(box);
    offerQr(box, meal);
  }
  if (!(await send({ type: "status" })).result) {
    showBanner("nejdřív zadej přihlášení do Kalorických tabulek.");
  }
}

init();
