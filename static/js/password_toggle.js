/* UX-6: "Show/Hide" on every password input (login, set, change pages).
   Progressive enhancement: wraps each input and adds a small toggle button. */
(function () {
  function enhance(input) {
    if (input.dataset.toggleReady) return;
    input.dataset.toggleReady = "1";
    var wrap = document.createElement("span");
    wrap.className = "pw-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pw-toggle";
    btn.textContent = "Show";
    btn.setAttribute("aria-label", "Show password");
    btn.addEventListener("click", function () {
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.textContent = show ? "Hide" : "Show";
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });
    wrap.appendChild(btn);
  }
  document.querySelectorAll("input[type=password]").forEach(enhance);
})();