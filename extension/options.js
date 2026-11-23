const $ = (id) => document.getElementById(id);

chrome.storage.local.get(["email", "passwordMd5"]).then(({ email, passwordMd5 }) => {
  $("email").value = email || "";
  $("password").placeholder = passwordMd5 ? "uložené, vyplň jen pro změnu" : "";
});

$("save").addEventListener("click", async () => {
  const email = $("email").value.trim();
  const password = $("password").value;
  const { passwordMd5 } = await chrome.storage.local.get("passwordMd5");
  if (!email || (!password && !passwordMd5)) {
    $("status").textContent = "Vyplň e-mail i heslo.";
    return;
  }
  // a changed login invalidates the stored KT session
  await chrome.storage.local.set({ email, passwordMd5: password ? md5(password) : passwordMd5 });
  await chrome.storage.local.remove(["hash", "unit"]);
  $("password").value = "";

  const response = await chrome.runtime.sendMessage({ type: "login" });
  $("status").textContent = response.ok
    ? `Přihlášení funguje. Energie se zapisuje v ${response.result === "kj" ? "kJ" : "kcal"}, jak máš nastavené v KT.`
    : `Přihlášení se nepovedlo: ${response.error}`;
});
