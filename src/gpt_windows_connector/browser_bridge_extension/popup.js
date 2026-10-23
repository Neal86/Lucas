async function render() {
  const s = await chrome.storage.local.get(["connected", "lastSeen", "paired", "pairingCode", "profileName", "profileId", "alias", "browserType"]);
  const connected = s.connected === true && Date.now() - Number(s.lastSeen || 0) < 45000;
  const st = document.getElementById("status");
  st.textContent = !connected ? "Lucas Node disconnected — start Lucas to reconnect" : s.paired ? "Connected to Lucas" : "Connected — return to Lucas Settings → Browser → Manage to pair";
  st.className = "row " + (connected && s.paired ? "ok" : "warn");
  document.getElementById("profile").textContent = [s.browserType || "Browser", s.profileName || s.alias || "", s.profileId ? "#" + s.profileId : ""].filter(Boolean).join(" · ");
  document.getElementById("code").textContent = connected && !s.paired && s.pairingCode ? "Pairing code: " + s.pairingCode : "";
}
document.getElementById("options").onclick = () => chrome.runtime.openOptionsPage();
chrome.storage.onChanged.addListener(render);
render();
setInterval(render, 3000);
