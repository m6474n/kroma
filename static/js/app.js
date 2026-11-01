// Select all / deselect all / selected counter for the bulk-action form.
(function () {
  const form = document.getElementById("bulk-form");
  if (!form) return;
  const counter = document.querySelector(form.dataset.countTarget);
  const boxes = () => Array.from(form.querySelectorAll(".row-check"));
  const update = () => { if (counter) counter.textContent = boxes().filter(b => b.checked).length; };
  form.addEventListener("change", e => { if (e.target.classList.contains("row-check")) update(); });
  form.querySelectorAll("[data-select]").forEach(btn =>
    btn.addEventListener("click", () => {
      const on = btn.dataset.select === "all";
      boxes().forEach(b => (b.checked = on));
      update();
    })
  );
  update();
})();
