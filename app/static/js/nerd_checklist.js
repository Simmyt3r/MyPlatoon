/* NERD checklist, purely in-page. No identity inputs, uploads, storage,
 * analytics or network requests. Nothing is persisted between visits. */
(function () {
  "use strict";

  function initialise() {
    const root = document.getElementById("nerd-checklist");
    const progress = document.getElementById("nerd-progress");
    const progressLabel = document.getElementById("nerd-progress-label");
    if (!root || !progress || !progressLabel) return;

    const items = Array.from(root.querySelectorAll("input[data-nerd-checklist-item]"));
    const sectionCounts = {};

    items.forEach(function (checkbox) {
      const section = checkbox.dataset.nerdSection;
      sectionCounts[section] = (sectionCounts[section] || 0) + 1;
    });

    function updateProgress() {
      const ready = items.filter(function (item) { return item.checked; }).length;
      progress.value = ready;
      progress.max = items.length;
      progressLabel.textContent = ready + " of " + items.length + " items ready";

      Object.keys(sectionCounts).forEach(function (key) {
        const done = items.filter(function (item) {
          return item.dataset.nerdSection === key && item.checked;
        }).length;
        const label = document.getElementById("nerd-count-" + key);
        if (label) label.textContent = done + " of " + sectionCounts[key] + " ready";
      });
    }

    root.addEventListener("change", function (event) {
      if (event.target && event.target.matches("input[data-nerd-checklist-item]")) {
        updateProgress();
      }
    });

    const printButton = document.getElementById("nerd-print");
    if (printButton) printButton.addEventListener("click", function () {
      window.print();
    });

    const resetButton = document.getElementById("nerd-reset");
    if (resetButton) resetButton.addEventListener("click", function () {
      if (items.some(function (item) { return item.checked; }) &&
          !window.confirm("Clear all your checklist ticks?")) return;
      items.forEach(function (item) { item.checked = false; });
      updateProgress();
    });

    updateProgress();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialise);
  } else {
    initialise();
  }
})();
