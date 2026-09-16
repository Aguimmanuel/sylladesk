/* Countdown, autosave, section advance. Vanilla JS, no dependencies. */
(function () {
  var form = document.getElementById("quiz-form");
  var countdown = document.getElementById("countdown");
  if (!form || !countdown) return;
  var expires = parseInt(countdown.dataset.expires, 10) * 1000;
  var isLast = countdown.dataset.last === "1";
  var csrf = form.querySelector("[name=csrfmiddlewaretoken]").value;
  var movedOn = false;

  function moveOn() {
    if (movedOn) return;
    movedOn = true;
    if (isLast) {
      form.submit();
    } else {
      var next = document.getElementById("advance-form");
      if (next) next.submit();
    }
  }

  function tick() {
    var left = Math.max(0, Math.floor((expires - Date.now()) / 1000));
    var m = String(Math.floor(left / 60)).padStart(2, "0");
    var s = String(left % 60).padStart(2, "0");
    countdown.textContent = m + ":" + s;
    if (left <= 0) moveOn();
  }
  tick();
  setInterval(tick, 1000);

  function save(field) {
    var body = new FormData();
    body.append("question", field.dataset.q);
    if (field.type === "radio") {
      if (!field.checked) return;
      body.append("choice", field.value);
    } else {
      body.append("text", field.value);
    }
    body.append("csrfmiddlewaretoken", csrf);
    fetch(window.location.href.replace(/\/take\/$/, "/save/"), {
      method: "POST",
      headers: { "X-Requested-With": "fetch" },
      body: body,
    }).catch(function () {});
  }

  form.addEventListener("change", function (e) {
    if (e.target.matches("[data-q]")) save(e.target);
  });
  form.addEventListener("input", function (e) {
    if (e.target.tagName === "TEXTAREA" && e.target.matches("[data-q]")) {
      clearTimeout(e.target._t);
      e.target._t = setTimeout(function () { save(e.target); }, 700);
    }
  });
})();
