(() => {
  "use strict";

  const toggle = document.querySelector("[data-nav-toggle]");
  const nav = document.querySelector("[data-nav]");

  const closeMenu = () => {
    if (!toggle || !nav) return;
    toggle.setAttribute("aria-expanded", "false");
    nav.dataset.open = "false";
    document.body.classList.remove("menu-open");
  };

  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      const isOpen = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!isOpen));
      nav.dataset.open = String(!isOpen);
      document.body.classList.toggle("menu-open", !isOpen);
    });

    nav.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", closeMenu);
    });

    window.addEventListener("resize", () => {
      if (window.innerWidth > 850) closeMenu();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeMenu();
    });
  }

  document.querySelectorAll("[data-year]").forEach((node) => {
    node.textContent = String(new Date().getFullYear());
  });

  const form = document.querySelector("[data-contact-form]");
  const draft = document.querySelector("[data-email-draft]");
  const status = document.querySelector("[data-contact-status]");
  if (form && draft && status) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const name = form.querySelector("#contact-name").value;
      const email = form.querySelector("#contact-email").value;
      const message = form.querySelector("#contact-message").value;
      const body = `Name: ${name}\nReply email: ${email}\n\n${message}`;
      draft.href = `mailto:hello@ksnxrl.dev?subject=${encodeURIComponent("Vox Rescue support")}&body=${encodeURIComponent(body)}`;
      draft.hidden = false;
      status.textContent = "Your draft is ready. Open it in your email app to review and send.";
    });
    form.addEventListener("input", () => {
      draft.hidden = true;
      draft.removeAttribute("href");
      status.textContent = "";
    });
  }

  const sections = Array.from(document.querySelectorAll("main > section[id]"));
  const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (!motionPreference.matches && "IntersectionObserver" in window) {
    // Content is visible by default; motion is a progressive enhancement.
    const targets = document.querySelectorAll(
      ".hero-logo, .hero h1, .hero .heading-rule, .hero p, .page-hero, " +
      ".section-title, .section-heading, .help-row, .feature-list, .contact-form"
    );
    const reveal = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("motion-visible");
        reveal.unobserve(entry.target);
      });
    }, { threshold: 0, rootMargin: "0px 0px -24px 0px" });
    targets.forEach((target, index) => {
      target.classList.add("motion-reveal");
      if (target.closest(".hero")) {
        target.style.setProperty("--reveal-delay", `${Math.min(index, 3) * 70}ms`);
      }
      reveal.observe(target);
    });
    const stopMotion = () => {
      if (!motionPreference.matches) return;
      reveal.disconnect();
      targets.forEach((target) => target.classList.remove("motion-reveal"));
    };
    motionPreference.addEventListener("change", stopMotion);
    // Keyboard navigation always exposes the focused field immediately.
    document.addEventListener("focusin", (event) => {
      event.target.closest(".motion-reveal")?.classList.add("motion-visible");
    });
  }
  if (nav && sections.length && "IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        nav.querySelectorAll('a[href^="#"]').forEach((link) => {
          if (link.getAttribute("href") === `#${entry.target.id}`) {
            link.setAttribute("aria-current", "location");
          } else {
            link.removeAttribute("aria-current");
          }
        });
      }
    }, { rootMargin: "-15% 0px -70% 0px" });
    sections.forEach((section) => observer.observe(section));
  }
})();
