// Sets the colour theme before the first paint, so a dark-mode user never sees a white flash (src/app/theme.ts
// keeps it in step after that). An external file because the CSP allows no inline scripts.
(function () {
  var theme = null;
  try {
    theme = localStorage.getItem("sabha.theme");
  } catch (e) {
    /* storage blocked: follow the device */
  }
  if (theme !== "light" && theme !== "dark") {
    theme = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.dataset.theme = theme;
})();
