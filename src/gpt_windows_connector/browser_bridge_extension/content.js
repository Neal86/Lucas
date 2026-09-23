(() => {
  function visible(el) {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.display !== "none" && s.visibility !== "hidden";
  }

  function findTarget(target, editable) {
    const query = String(target || "").trim();
    if (!query) throw new Error("target is required");
    try {
      const found = document.querySelector(query.startsWith("css=") ? query.slice(4) : query);
      if (found && visible(found)) return found;
    } catch (_) {}
    const selector = editable
      ? "input,textarea,select,[contenteditable=true]"
      : "button,a,[role=button],[role=link],input[type=submit],input[type=button]";
    const needle = query.toLowerCase();
    const matches = [...document.querySelectorAll(selector)].filter(visible).map(el => {
      const values = [
        el.getAttribute("aria-label"),
        el.getAttribute("name"),
        el.getAttribute("placeholder"),
        el.innerText,
        el.value,
        el.labels && el.labels[0] && el.labels[0].innerText
      ].filter(Boolean).map(value => String(value).replace(/\s+/g, " ").trim().toLowerCase());
      const score = values.some(value => value === needle) ? 100 :
        values.some(value => value.includes(needle)) ? 60 : 0;
      return [score, el];
    }).filter(item => item[0] > 0).sort((a, b) => b[0] - a[0]);
    if (!matches.length) throw new Error("No browser element matched: " + query);
    return matches[0][1];
  }

  function snapshot(params) {
    const limit = Number(params.limit || 400);
    const maxChars = Number(params.max_chars || 50000);
    const nodes = [...document.querySelectorAll(
      "button,a,input,textarea,select,[role=button],[role=link],[role=checkbox],[role=radio],[contenteditable=true]"
    )].filter(visible).slice(0, limit);
    const elements = nodes.map((el, index) => ({
      index,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute("role") || "",
      text: String(el.innerText || el.value || "").replace(/\s+/g, " ").trim().slice(0, 500),
      aria_label: el.getAttribute("aria-label") || "",
      name: el.getAttribute("name") || "",
      placeholder: el.getAttribute("placeholder") || "",
      type: el.getAttribute("type") || ""
    }));
    const text = String(document.body && document.body.innerText || "").slice(0, maxChars);
    const lower = (document.title + " " + location.href + " " + text).toLowerCase();
    const captcha = !!document.querySelector(
      'iframe[src*="recaptcha"],iframe[src*="hcaptcha"],iframe[src*="challenges.cloudflare.com"],[data-sitekey],[class*="captcha" i],[id*="captcha" i]'
    ) || /verify you are human|human verification|人机验证|安全验证/.test(lower);
    const otp = !!document.querySelector('input[autocomplete="one-time-code"]') ||
      /two[- ]factor|2fa|verification code|authenticator code|短信验证码|两步验证|双重验证/.test(lower);
    const passkey = /passkey|security key|windows hello|通行密钥|安全密钥/.test(lower);
    const identity = /verify your identity|identity verification|business verification|身份验证|实名认证|营业执照/.test(lower);
    const login = !!document.querySelector('input[type="password"]') && /login|signin|sign-in|登录/.test(lower);
    return {
      url: location.href,
      title: document.title,
      text,
      elements,
      blocker: captcha ? "captcha" : otp ? "2fa" : passkey ? "passkey" : identity ? "identity_verification" : login ? "login" : null
    };
  }

  async function run(action, params) {
    if (action === "page.snapshot") return snapshot(params);
    if (action === "page.click") {
      const el = findTarget(params.target || params.selector, false);
      el.scrollIntoView({ block: "center", inline: "center" });
      el.click();
      return { target: params.target || params.selector, url: location.href };
    }
    if (action === "page.type") {
      const el = findTarget(params.target || params.selector, true);
      el.scrollIntoView({ block: "center", inline: "center" });
      el.focus({ preventScroll: true });
      const value = params.clear === false ? String(el.value || "") + String(params.text || "") : String(params.text || "");
      el.value = value;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return { target: params.target || params.selector, characters: String(params.text || "").length, url: location.href };
    }
    if (action === "page.select") {
      const el = findTarget(params.target || params.selector, true);
      el.value = String(params.value || "");
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return { target: params.target || params.selector, value: el.value };
    }
    if (action === "page.scroll") {
      if (params.target) findTarget(params.target, false).scrollIntoView({ block: "center", inline: "center" });
      else window.scrollBy(Number(params.delta_x || 0), Number(params.delta_y || 700));
      return { url: location.href, x: scrollX, y: scrollY };
    }
    if (action === "page.hover") {
      const el = findTarget(params.target, false);
      el.scrollIntoView({ block: "center", inline: "center" });
      el.dispatchEvent(new MouseEvent("mouseover", { bubbles: true, cancelable: true, view: window }));
      return { target: params.target, url: location.href };
    }
    if (action === "page.press") {
      const el = params.target ? findTarget(params.target, true) : (document.activeElement || document.body);
      el.focus && el.focus({ preventScroll: true });
      el.dispatchEvent(new KeyboardEvent("keydown", { key: String(params.key), bubbles: true }));
      el.dispatchEvent(new KeyboardEvent("keyup", { key: String(params.key), bubbles: true }));
      if (String(params.key) === "Enter" && el.form && el.form.requestSubmit) el.form.requestSubmit();
      return { key: String(params.key), url: location.href };
    }
    if (action === "page.wait") {
      const deadline = Date.now() + Math.min(Math.max(Number(params.timeout_ms || 15000), 250), 120000);
      while (Date.now() < deadline) {
        let ok = false;
        if (params.selector) ok = !!document.querySelector(params.selector);
        else if (params.text) ok = String(document.body && document.body.innerText || "").toLowerCase().includes(String(params.text).toLowerCase());
        else if (params.url_contains) ok = location.href.includes(String(params.url_contains));
        else ok = document.readyState === "complete" || document.readyState === "interactive";
        if (ok) return { waited: true, url: location.href };
        await new Promise(resolve => setTimeout(resolve, 250));
      }
      throw new Error("Timeout waiting for page condition");
    }
    if (action === "page.network") {
      return {
        url: location.href,
        resources: performance.getEntriesByType("resource").slice(-Number(params.limit || 100)).map(item => ({
          name: String(item.name || "").slice(0, 2000),
          initiatorType: item.initiatorType || "",
          duration: Math.round(Number(item.duration || 0)),
          transferSize: Number(item.transferSize || 0)
        }))
      };
    }
    throw new Error("Unsupported content command: " + action);
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || message.type !== "lucas_command") return;
    run(message.action, message.params || {})
      .then(result => sendResponse({ ok: true, result }))
      .catch(error => sendResponse({ ok: false, error: (error.name || "Error") + ": " + (error.message || String(error)) }));
    return true;
  });
})();
