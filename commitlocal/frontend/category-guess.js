// category-guess.js — guesses an expense category from its note ("KFC 350" → "Food & drinks") using the keyword
// list from the backend (backend/category_keywords.py = the ONE list to edit; the phone keeps a copy so this works
// offline). Same matching as the backend: no case, no accents, no punctuation, whole words, longest keyword first.
// No screen code here, so it runs in the browser and in Node tests (tests/frontend/category-guess.test.js).
(function () {
  // "McDonald’s Été!" → "mcdonalds ete"
  function normalise(text) {
    return String(text || "")
      .normalize("NFKD").replace(/[̀-ͯ]/g, "") // é → e
      .toLowerCase()
      .replace(/['’`]/g, "")                             // McDonald's = McDonalds
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  }

  // keywords = {category: [words]} → the category, or null when nothing matches
  function matchKeywords(text, keywords) {
    const padded = " " + normalise(text) + " "; // spaces around = whole words only
    const pairs = [];
    Object.keys(keywords || {}).forEach((category) => {
      (keywords[category] || []).forEach((word) => pairs.push([normalise(word), category]));
    });
    pairs.sort((a, b) => b[0].length - a[0].length); // "metro express" before "metro"
    const found = pairs.find((pair) => pair[0] && padded.includes(" " + pair[0] + " "));
    return found ? found[1] : null;
  }

  const CategoryGuess = { normalise, matchKeywords };
  if (typeof window !== "undefined") window.CategoryGuess = CategoryGuess; // browser
  if (typeof module !== "undefined" && module.exports) module.exports = CategoryGuess; // Node tests
})();
