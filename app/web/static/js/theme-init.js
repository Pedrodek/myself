/* Runs before first paint (blocking, external: CSP forbids inline scripts) to avoid a theme flash. */
(function () {
  try {
    var stored = localStorage.getItem("theme");
    var dark = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle("dark", dark);
  } catch (error) {
    /* storage can be blocked; the default (light) theme is fine */
  }
})();
