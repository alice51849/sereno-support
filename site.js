(function () {
  "use strict";

  const rtlLanguages = new Set(["ar", "he", "ur"]);

  function chooseLocale(locales) {
    const requested = new URLSearchParams(window.location.search).get("locale");
    const candidates = [requested, navigator.language, ...(navigator.languages || [])]
      .filter(Boolean);
    for (const candidate of candidates) {
      if (locales[candidate]) return candidate;
      const folded = candidate.toLowerCase();
      const exact = Object.keys(locales).find((locale) => locale.toLowerCase() === folded);
      if (exact) return exact;
      const base = folded.split("-")[0];
      const regional = Object.keys(locales).find(
        (locale) => locale.toLowerCase().split("-")[0] === base
      );
      if (regional) return regional;
    }
    return "en-US";
  }

  function localeLabel(locale) {
    try {
      return new Intl.DisplayNames([locale], { type: "language" }).of(locale) || locale;
    } catch (error) {
      console.warn("Unable to localize locale label", locale, error);
      return locale;
    }
  }

  async function localize() {
    const response = await fetch("locales.json", { cache: "no-cache" });
    if (!response.ok) {
      throw new Error(`Unable to load Sereno localizations: HTTP ${response.status}`);
    }
    const locales = await response.json();
    if (Object.keys(locales).length !== 50 || !locales["en-US"]) {
      throw new Error("Sereno localization catalog must contain exact-50 locales");
    }

    const locale = chooseLocale(locales);
    const copy = locales[locale];
    document.documentElement.lang = locale;
    document.documentElement.dir = rtlLanguages.has(locale.split("-")[0]) ? "rtl" : "ltr";

    document.querySelectorAll("[data-i18n]").forEach((element) => {
      const key = element.dataset.i18n;
      if (typeof copy[key] !== "string" || !copy[key]) {
        throw new Error(`Missing ${locale}.${key}`);
      }
      element.textContent = copy[key];
    });

    const page = document.body.dataset.page;
    document.title = copy.pageTitles[page];
    document.getElementById("meta-description").setAttribute("content", copy.metaDescription);

    document.querySelectorAll("[data-page-link]").forEach((link) => {
      link.href = `${link.dataset.pageLink}?locale=${encodeURIComponent(locale)}`;
    });

    const selector = document.getElementById("locale-switcher");
    Object.keys(locales).sort().forEach((available) => {
      const option = document.createElement("option");
      option.value = available;
      option.textContent = localeLabel(available);
      option.selected = available === locale;
      selector.appendChild(option);
    });
    selector.addEventListener("change", () => {
      const params = new URLSearchParams(window.location.search);
      params.set("locale", selector.value);
      window.location.search = params.toString();
    });

    document.querySelectorAll(".reveal").forEach((element) => element.classList.add("in"));
  }

  localize().catch((error) => {
    console.error("Sereno site localization failed", error);
    document.querySelectorAll(".reveal").forEach((element) => element.classList.add("in"));
  });
}());
