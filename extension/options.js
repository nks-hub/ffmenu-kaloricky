const $ = (id) => document.getElementById(id);
const LOCAL = ["127.0.0.1", "localhost"];

chrome.storage.local.get(["serviceUrl", "token"]).then(({ serviceUrl, token }) => {
  $("url").value = serviceUrl || "http://127.0.0.1:8077";
  $("token").value = token || "";
});

$("save").addEventListener("click", async () => {
  let url;
  try {
    url = new URL($("url").value.trim());
  } catch (error) {
    $("status").textContent = "Adresa služby není platná URL.";
    return;
  }
  const fromLink = new URLSearchParams(url.hash.slice(1)).get("t");
  const token = fromLink || $("token").value.trim();
  const serviceUrl = url.origin;

  // the service may run on another machine; that origin needs its own host permission
  if (!LOCAL.includes(url.hostname) && !(await chrome.permissions.request({ origins: [`${url.origin}/*`] }))) {
    $("status").textContent = "Bez povolení přístupu k adrese služby doplněk nemůže zapisovat.";
    return;
  }
  await chrome.storage.local.set({ serviceUrl, token });
  $("url").value = serviceUrl;
  $("token").value = token;

  const { status, data } = await chrome.runtime.sendMessage({ type: "menu", date: new Date().toISOString().slice(0, 10) });
  $("status").textContent = status === 200
    ? `Uloženo. Spojení funguje, program: ${data.programs[data.program]}.`
    : `Uloženo, ale služba hlásí: ${data.error || `chyba ${status}`}`;
});
