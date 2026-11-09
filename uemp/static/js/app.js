/*
 * app.js — Small helpers that make pages feel responsive.
 *
 * Nothing here is needed for SECURITY or CORRECTNESS: the server re-checks
 * and re-calculates everything. These scripts only give instant feedback.
 *
 *   1. Mobile sidebar open/close
 *   2. "Are you sure?" confirmation on buttons with data-confirm
 *   3. Course registration: running unit total
 *   4. Score sheet: live total + grade preview as the lecturer types
 *   5. Login page: click a demo account to fill the form
 */

document.addEventListener("DOMContentLoaded", () => {
  // 1. Mobile sidebar ------------------------------------------------------
  const sidebar = document.querySelector(".sidebar");
  const backdrop = document.querySelector(".sidebar-backdrop");
  document.querySelectorAll("[data-toggle-sidebar]").forEach((btn) =>
    btn.addEventListener("click", () => {
      sidebar?.classList.toggle("show");
      backdrop?.classList.toggle("show");
    })
  );
  backdrop?.addEventListener("click", () => {
    sidebar.classList.remove("show");
    backdrop.classList.remove("show");
  });

  // 2. Confirmation prompts -----------------------------------------------
  document.querySelectorAll("[data-confirm]").forEach((el) =>
    el.addEventListener("click", (event) => {
      if (!window.confirm(el.dataset.confirm)) event.preventDefault();
    })
  );

  // 3. Course registration unit counter ------------------------------------
  const picker = document.querySelector("[data-course-picker]");
  if (picker) {
    const base = Number(picker.dataset.registeredUnits || 0);
    const max = Number(picker.dataset.maxUnits || 24);
    const total = document.querySelector("[data-unit-total]");
    const meter = document.querySelector("[data-unit-meter]");
    const submit = document.querySelector("[data-register-submit]");
    const update = () => {
      let units = base;
      let picked = 0;
      picker.querySelectorAll("input[type=checkbox]").forEach((box) => {
        box.closest(".course-option")?.classList.toggle("checked", box.checked);
        if (box.checked && !box.disabled) { units += Number(box.dataset.units); picked += 1; }
      });
      total.textContent = units;
      meter.style.width = Math.min(100, (units / max) * 100) + "%";
      meter.classList.toggle("over", units > max);
      if (submit) submit.disabled = picked === 0 || units > max;
    };
    picker.addEventListener("change", update);
    update();
  }

  // 4. Live grade preview on the score sheet --------------------------------
  const sheet = document.querySelector("[data-score-sheet]");
  if (sheet) {
    const scale = JSON.parse(sheet.dataset.scale); // [[min, grade, point], ...] highest first
    const gradeFor = (t) => (scale.find(([min]) => t >= min) || [0, "F"])[1];
    sheet.querySelectorAll("tr[data-entry]").forEach((row) => {
      const ca = row.querySelector("[data-ca]");
      const exam = row.querySelector("[data-exam]");
      const totalCell = row.querySelector("[data-total]");
      const gradeCell = row.querySelector("[data-grade]");
      const recalc = () => {
        [ca, exam].forEach((input) => {
          const v = input.value.trim();
          const bad = v !== "" && (isNaN(v) || Number(v) < 0 || Number(v) > Number(input.max));
          input.classList.toggle("is-invalid", bad);
        });
        if (ca.value.trim() === "" || exam.value.trim() === "") {
          totalCell.textContent = "—";
          gradeCell.innerHTML = '<span class="muted">—</span>';
          return;
        }
        const t = Number(ca.value) + Number(exam.value);
        const g = gradeFor(t);
        totalCell.textContent = Number.isInteger(t) ? t : t.toFixed(1);
        gradeCell.innerHTML = `<span class="grade grade-${g}">${g}</span>`;
      };
      [ca, exam].forEach((input) => input?.addEventListener("input", recalc));
    });
  }

  // 5. Demo account chips on the login page --------------------------------
  document.querySelectorAll("[data-demo-email]").forEach((chip) =>
    chip.addEventListener("click", () => {
      document.querySelector("#email").value = chip.dataset.demoEmail;
      document.querySelector("#password").value = chip.dataset.demoPassword;
      document.querySelector("#password").focus();
    })
  );
});
