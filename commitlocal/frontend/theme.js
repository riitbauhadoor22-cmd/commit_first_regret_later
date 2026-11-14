// theme.js — the Brighter (default) / Darker colour theme. Loaded in <head> BEFORE style.css is used, so the page is
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
