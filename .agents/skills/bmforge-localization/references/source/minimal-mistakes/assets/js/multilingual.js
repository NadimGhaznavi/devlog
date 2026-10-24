/* Page translations: no dependencies or locale registry required. */
(function () {
  "use strict";

  var selector = document.getElementById("language-selector");
  if (!selector) return;

  var options = Array.prototype.slice.call(selector.options);
  var current = new URL(window.location.href);

  function normalize(locale) {
    return String(locale || "").replace(/_/g, "-").toLowerCase();
  }

  // Only fall back to explicitly provided parent languages, never a sibling
  // region/script (for example, zh-CN must not implicitly select zh-TW).
  function match(locale) {
    var candidate = normalize(locale);
    while (candidate) {
      for (var i = 0; i < options.length; i++) {
        if (normalize(options[i].getAttribute("data-lang")) === candidate) {
          return options[i];
        }
      }
      var separator = candidate.lastIndexOf("-");
      candidate = separator < 0 ? "" : candidate.slice(0, separator);
    }
    return null;
  }

  function destination(option) {
    var target = new URL(option.value, current);
    target.search = current.search;
    target.hash = current.hash;
    return target;
  }

  selector.addEventListener("change", function () {
    var option = selector.options[selector.selectedIndex];
    var locale = option.getAttribute("data-lang");
    var target = destination(option);
    // Carry the explicit choice through the redirect.
    target.searchParams.set("mm_lang", locale);
    window.location.assign(target.href);
  });

  var preferred = current.searchParams.get("mm_lang");

  var selected = null;
  if (preferred) {
    selected = match(preferred);
  } else {
    var languages = window.navigator.languages || [window.navigator.language];
    for (var i = 0; i < languages.length && !selected; i++) {
      selected = match(languages[i]);
    }
  }
  selected = selected || match(selector.getAttribute("data-default-lang"));

  // Missing defaults leave the current page usable. replace() keeps automatic
  // selection out of browser history; comparing paths prevents redirect loops.
  if (selected) {
    var target = destination(selected);
    if (target.pathname !== current.pathname) {
      window.location.replace(target.href);
    }
  }
})();
