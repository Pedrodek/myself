/* Site behaviour: Alpine components (CSP build, no eval), HTMX hooks and lazy "islands".
 * Loaded with `defer` before Alpine, so the alpine:init listener below is registered in time. */
(function () {
  "use strict";

  document.addEventListener("alpine:init", function () {
    Alpine.data("navMenu", function () {
      return {
        open: false,
        toggle: function () { this.open = !this.open; },
        close: function () { this.open = false; },
        get navClass() { return { "is-open": this.open }; },
      };
    });

    Alpine.data("themeToggle", function () {
      return {
        dark: document.documentElement.classList.contains("dark"),
        toggle: function () {
          this.dark = !this.dark;
          document.documentElement.classList.toggle("dark", this.dark);
          try {
            localStorage.setItem("theme", this.dark ? "dark" : "light");
          } catch (error) { /* ignore blocked storage */ }
        },
      };
    });

    Alpine.data("printPage", function () {
      return { print: function () { window.print(); } };
    });
  });

  // After an HTMX navigation: update focus and announce the new page to screen readers.
  document.addEventListener("htmx:afterSettle", function (event) {
    var config = event.detail && event.detail.requestConfig;
    if (!config || !config.boosted) { return; }
    var main = document.getElementById("main");
    if (main) { main.focus({ preventScroll: true }); }
    var announcer = document.getElementById("announcer");
    if (announcer) { announcer.textContent = document.title; }
    window.dispatchEvent(new Event("nav-close"));
  });

  // If a boosted navigation fails, fall back to a normal page load (the server renders the error).
  function fallbackToFullLoad(event) {
    var config = event.detail && event.detail.requestConfig;
    if (!config || !config.boosted || String(config.verb).toLowerCase() !== "get") { return; }
    var path = event.detail.pathInfo && event.detail.pathInfo.requestPath;
    window.location.assign(path || window.location.href);
  }
  document.addEventListener("htmx:responseError", fallbackToFullLoad);
  document.addEventListener("htmx:sendError", fallbackToFullLoad);
  document.addEventListener("htmx:timeout", fallbackToFullLoad);

  // Islands: heavy widgets are separate ES modules loaded only on the pages that use them.
  // Markup: <div data-island data-module="/static/js/islands/x.js" ...>; the module exports mount(el).
  var mounted = new WeakSet();
  function mountIslands(root) {
    var candidates = root.querySelectorAll ? root.querySelectorAll("[data-island]") : [];
    candidates.forEach(function (element) {
      if (mounted.has(element)) { return; }
      mounted.add(element);
      import(element.dataset.module).then(function (module) {
        element.__island = module.mount(element) || null;
      }).catch(function (error) {
        element.setAttribute("data-island-error", "");
        console.error("island failed to load", error);
      });
    });
  }
  document.addEventListener("htmx:load", function (event) { mountIslands(event.target); });
  document.addEventListener("htmx:beforeCleanupElement", function (event) {
    var island = event.target.__island;
    if (island && typeof island.destroy === "function") { island.destroy(); }
  });
})();
