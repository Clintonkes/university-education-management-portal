/*
 * app.js — Small helpers that make pages feel fast and responsive.
 *
 * Nothing here is needed for SECURITY or CORRECTNESS: the server re-checks
 * and re-calculates everything. These scripts only give instant feedback.
 *
 * HOW PAGES LOAD
 *   htmx (see base.html) swaps only the main panel when a link or form is
 *   used. So page features are set up in `initPage(root)`, which runs on the
 *   first load AND after every swap (the htmx:load event).
 *
 *   1. Fast navigation glue: sidebar highlight, mobile menu, full reload
 *      when a response is not an app page (e.g. the login screen)
 *   2. Modal confirmation, toast notifications, and submit feedback
 *   3. Filters that apply themselves (data-auto-filter forms)
 *   4. Course registration: running unit total
 *   5. Score sheet: live total + grade preview as the lecturer types
 *   6. Login page: click a demo account to fill the form
 *   7. Password visibility
 */

(function () {
  "use strict";

  // ---------------------------------------------------------------------------
  // 1. Fast navigation glue
  // ---------------------------------------------------------------------------
  const sidebar = () => document.querySelector(".sidebar");
  const backdrop = () => document.querySelector(".sidebar-backdrop");

  function closeMobileMenu() {
    sidebar()?.classList.remove("show");
    backdrop()?.classList.remove("show");
  }

  // Highlight the sidebar item named by the page that was just loaded.
  function syncSidebar() {
    const main = document.querySelector("#app-main");
    if (!main) return;
    const active = main.dataset.activeNav || "";
    document.querySelectorAll(".side-link[data-nav]").forEach((link) =>
      link.classList.toggle("active", link.dataset.nav === active)
    );
  }

  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-toggle-sidebar]")) {
      sidebar()?.classList.toggle("show");
      backdrop()?.classList.toggle("show");
    } else if (event.target.closest(".sidebar-backdrop") || event.target.closest(".side-link")) {
      closeMobileMenu();
    }
  });

  // If the server answers with something that is not an app page (the login
  // screen after a session timeout, a print page...), load it normally.
  document.addEventListener("htmx:beforeSwap", (event) => {
    const text = event.detail.xhr.responseText || "";
    const isAppPage = text.indexOf('id="app-main"') !== -1;
    if (!isAppPage) {
      event.detail.shouldSwap = false;
      window.location.href = event.detail.xhr.responseURL || event.detail.pathInfo.requestPath;
    }
  });

  // A network failure (offline, server restarting): fall back to a normal load.
  document.addEventListener("htmx:sendError", (event) => {
    window.location.href = event.detail.pathInfo.requestPath;
  });

  document.addEventListener("htmx:afterSettle", () => {
    syncSidebar();
    closeMobileMenu();
  });

  // ---------------------------------------------------------------------------
  // 2. Modal confirmations (delegated so they also work after an HTMX swap)
  // ---------------------------------------------------------------------------
  let pendingConfirmation = null;
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-confirm]");
    if (!trigger) return;
    event.preventDefault();
    const modalElement = document.querySelector("#confirmation-modal");
    if (!modalElement) return;
    pendingConfirmation = {
      form: trigger.closest("form"),
      submitter: trigger.matches("button, input") ? trigger : null,
    };
    modalElement.querySelector("[data-confirmation-message]").textContent = trigger.dataset.confirm;
    bootstrap.Modal.getOrCreateInstance(modalElement).show();
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-confirmation-accept]")) return;
    const modalElement = document.querySelector("#confirmation-modal");
    const { form, submitter } = pendingConfirmation || {};
    pendingConfirmation = null;
    if (modalElement) bootstrap.Modal.getOrCreateInstance(modalElement).hide();
    if (!form?.isConnected) return;
    // htmx learns which button was pressed from click/focus events, and the
    // modal took the focus away. Copy the button's name=value (for example
    // action=submit) into a hidden field so the server still receives it.
    let carrier = null;
    if (submitter?.name) {
      carrier = document.createElement("input");
      carrier.type = "hidden";
      carrier.name = submitter.name;
      carrier.value = submitter.value;
      form.append(carrier);
    }
    form.requestSubmit(submitter?.isConnected ? submitter : undefined);
    carrier?.remove(); // the form data was already collected during requestSubmit
  });

  // ---------------------------------------------------------------------------
  // Page features — run for the first page and every swapped-in page
  // ---------------------------------------------------------------------------
  function initPage(root) {
    initToasts(root);
    initFormFeedback(root);
    initPasswordToggle(root);
    initAutoFilters(root);
    initCoursePicker(root);
    initScoreSheet(root);
    initDemoChips(root);
  }

  function initToasts(root) {
    root.querySelectorAll(".toast").forEach((toast) => {
      if (toast.dataset.ready) return;
      toast.dataset.ready = "1";
      bootstrap.Toast.getOrCreateInstance(toast).show();
    });
  }

  function initFormFeedback(root) {
    root.querySelectorAll("form").forEach((form) => {
      if (form.dataset.feedbackReady) return;
      form.dataset.feedbackReady = "1";
      form.addEventListener("submit", (event) => {
        if (form.dataset.submitting) {
          event.preventDefault();
          return;
        }
        form.dataset.submitting = "true";
        const submitter = event.submitter || form.querySelector('button[type="submit"], button:not([type])');
        if (!submitter) return;
        submitter.setAttribute("aria-busy", "true");
        const spinner = document.createElement("span");
        spinner.className = "spinner-border spinner-border-sm ms-2";
        spinner.setAttribute("aria-hidden", "true");
        submitter.append(spinner);
      });
    });
  }

  // 3. Filters: changing a drop-down applies it at once; typing in a search
  //    box applies it after a short pause. (htmx keeps the cursor in the box.)
  function initAutoFilters(root) {
    root.querySelectorAll("form[data-auto-filter]").forEach((form) => {
      if (form.dataset.ready) return;
      form.dataset.ready = "1";
      const submit = () => {
        // A changed filter means "start again from page 1".
        form.querySelector("input[name=page]")?.remove();
        form.requestSubmit();
      };
      form.querySelectorAll("select").forEach((s) => s.addEventListener("change", submit));
      let timer;
      form.querySelectorAll("input[type=search], input[data-live]").forEach((input) =>
        input.addEventListener("input", () => {
          clearTimeout(timer);
          timer = setTimeout(submit, 450);
        })
      );
      form.querySelectorAll("input[type=date]").forEach((d) => d.addEventListener("change", submit));
    });
  }

  // 4. Course registration unit counter
  function initCoursePicker(root) {
    const picker = root.querySelector("[data-course-picker]");
    if (!picker || picker.dataset.ready) return;
    picker.dataset.ready = "1";
    const base = Number(picker.dataset.registeredUnits || 0);
    const max = Number(picker.dataset.maxUnits || 24);
    const total = root.querySelector("[data-unit-total]");
    const meter = root.querySelector("[data-unit-meter]");
    const submit = root.querySelector("[data-register-submit]");
    const update = () => {
      let units = base;
      let picked = 0;
      picker.querySelectorAll("input[type=checkbox]").forEach((box) => {
        box.closest(".course-option")?.classList.toggle("checked", box.checked);
        if (box.checked && !box.disabled) { units += Number(box.dataset.units); picked += 1; }
      });
      if (total) total.textContent = units;
      if (meter) {
        meter.style.width = Math.min(100, (units / max) * 100) + "%";
        meter.classList.toggle("over", units > max);
      }
      if (submit) submit.disabled = picked === 0 || units > max;
    };
    picker.addEventListener("change", update);
    update();
  }

  // 5. Live grade preview on the score sheet
  function initScoreSheet(root) {
    const sheet = root.querySelector("[data-score-sheet]");
    if (!sheet || sheet.dataset.ready) return;
    sheet.dataset.ready = "1";
    const scale = JSON.parse(sheet.dataset.scale); // [[min, grade, point], ...]
    scale.sort((a, b) => b[0] - a[0]);
    const gradeFor = (t) => (scale.find(([min]) => t >= min) || [0, "F"])[1];
    sheet.querySelectorAll("tr[data-entry]").forEach((row) => {
      const ca = row.querySelector("[data-ca]");
      const exam = row.querySelector("[data-exam]");
      const totalCell = row.querySelector("[data-total]");
      const gradeCell = row.querySelector("[data-grade]");
      if (!ca || !exam) return;
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
      [ca, exam].forEach((input) => input.addEventListener("input", recalc));
    });
  }

  // 6. Demo account chips on the login page
  function initDemoChips(root) {
    root.querySelectorAll("[data-demo-email]").forEach((chip) => {
      if (chip.dataset.ready) return;
      chip.dataset.ready = "1";
      chip.addEventListener("click", () => {
        document.querySelector("#email").value = chip.dataset.demoEmail;
        document.querySelector("#password").value = chip.dataset.demoPassword;
        document.querySelector("#password").focus();
      });
    });
  }

  function initPasswordToggle(root) {
    root.querySelectorAll("[data-password-toggle]").forEach((button) => {
      if (button.dataset.ready) return;
      button.dataset.ready = "1";
      button.addEventListener("click", () => {
        const input = document.getElementById(button.getAttribute("aria-controls"));
        if (!input) return;
        const visible = input.type === "password";
        input.type = visible ? "text" : "password";
        button.setAttribute("aria-label", visible ? "Hide password" : "Show password");
        button.querySelector("i").className = visible ? "bi bi-eye-slash" : "bi bi-eye";
      });
    });
  }

  // First page: run as soon as the HTML is ready. Later pages: htmx:load.
  document.addEventListener("DOMContentLoaded", () => {
    syncSidebar();
    initPage(document);
  });
  document.addEventListener("htmx:load", (event) => initPage(event.detail.elt));
})();
