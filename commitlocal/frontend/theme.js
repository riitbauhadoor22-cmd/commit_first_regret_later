// theme.js — the Brighter (default, shown as "Blue") / Darker (shown as "Dark") colour theme. Loaded in <head> BEFORE style.css is used, so the page is
// drawn in the right colours straight away (no flash). The choice is kept on this phone (localStorage "theme").
// "darker" puts data-theme="darker" on <html>; the colours themselves are CSS variables at the top of style.css.
const THEME_KEY = "theme";

function getTheme() {
  try {
    return localStorage.getItem(THEME_KEY) === "darker" ? "darker" : "brighter";
  } catch (error) {
    return "brighter"; // storage blocked (private window): the default
  }
}

function applyTheme(name) {
  if (name === "darker") document.documentElement.setAttribute("data-theme", "darker");
  else document.documentElement.removeAttribute("data-theme");
}

function setTheme(name) {
  try {
    localStorage.setItem(THEME_KEY, name);
  } catch (error) {
    // storage blocked: the theme still changes until the page is closed
  }
  applyTheme(name);
}

applyTheme(getTheme());

// Changed in another tab of the app: follow it here too (the Settings buttons are redrawn when Settings opens)
window.addEventListener("storage", (event) => {
  if (event.key === THEME_KEY) applyTheme(getTheme());
});
