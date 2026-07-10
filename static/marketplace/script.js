/* ============================================================================
   SoftMarket Kenya — v2 frontend behaviour
   - Keeps UTM capture, menu, dark-mode toggle, hero toggle, WhatsApp flow.
   - Adds: moving-shader canvas (IntersectionObserver-bound, paused off-screen),
           TextRoll letter-rolling hover animation, scroll-reveal.
   - Honours prefers-reduced-motion everywhere.
   ============================================================================ */

const BUSINESS_WHATSAPP_NUMBER = "254716343561";
const utmKeys = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"];
const urlParams = new URLSearchParams(window.location.search);
const collectedUtm = {};

utmKeys.forEach((key) => {
  const value = urlParams.get(key);
  if (value) {
    sessionStorage.setItem(key, value);
    collectedUtm[key] = value;
  } else {
    const stored = sessionStorage.getItem(key);
    if (stored) collectedUtm[key] = stored;
  }
});

function fillUtmFields(form) {
  utmKeys.forEach((key) => {
    const field = form.querySelector(`input[name="${key}"]`);
    if (field && collectedUtm[key]) field.value = collectedUtm[key];
  });
}

document.querySelectorAll("form").forEach(fillUtmFields);

const menuButton = document.querySelector(".menu-btn");
const menuPanel = document.querySelector("#menuPanel");
const menuClose = document.querySelector(".menu-close");
const themeToggle = document.querySelector(".theme-toggle");

function storeTheme(theme) {
  try {
    localStorage.setItem("softmarket-theme", theme);
  } catch (error) {}
}

function isDarkTheme() {
  return document.documentElement.dataset.theme === "dark";
}

function updateThemeButton() {
  if (!themeToggle) return;
  const dark = isDarkTheme();
  themeToggle.setAttribute("aria-pressed", String(dark));
  themeToggle.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
}

function setTheme(theme) {
  const dark = theme === "dark";
  if (dark) {
    document.documentElement.dataset.theme = "dark";
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  storeTheme(dark ? "dark" : "light");
  updateThemeButton();
  // Let theme-aware widgets (e.g. the moving shader) re-paint.
  window.dispatchEvent(new CustomEvent("softmarket:themechange"));
}

updateThemeButton();

themeToggle?.addEventListener("click", () => {
  setTheme(isDarkTheme() ? "light" : "dark");
});

function setMenuOpen(isOpen) {
  if (!menuButton || !menuPanel) return;
  menuPanel.classList.toggle("is-open", isOpen);
  menuButton.setAttribute("aria-expanded", String(isOpen));
  menuPanel.setAttribute("aria-hidden", String(!isOpen));
  document.body.classList.toggle("menu-open", isOpen);
}

menuButton?.addEventListener("click", () => {
  setMenuOpen(!menuPanel?.classList.contains("is-open"));
});

menuPanel?.querySelectorAll("a").forEach((link) => {
  link.addEventListener("click", () => {
    setMenuOpen(false);
  });
});

menuClose?.addEventListener("click", () => {
  setMenuOpen(false);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    setMenuOpen(false);
  }
});

const prefersReducedMotion =
  window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ---------- Scroll reveal (IntersectionObserver) ---------- */
const revealElements = document.querySelectorAll(".reveal");

if (prefersReducedMotion || !("IntersectionObserver" in window)) {
  revealElements.forEach((element) => element.classList.add("active"));
} else {
  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("active");
          revealObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 }
  );

  revealElements.forEach((element, index) => {
    element.style.transitionDelay = `${Math.min(index * 0.08, 0.45)}s`;
    revealObserver.observe(element);
  });
}

/* ---------- Hero "I'm hiring" / "I'm building" toggle ---------- */
const heroToggleButtons = document.querySelectorAll(".hero-toggle-btn");
if (heroToggleButtons.length) {
  const heroHeading = document.querySelector(".hero-content h1");
  const heroSub = document.querySelector(".hero-sub");
  const heroPrimary = document.querySelector(".hero-bottom .primary-btn");

  heroToggleButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const mode = button.dataset.mode;
      heroToggleButtons.forEach((other) => {
        const active = other === button;
        other.classList.toggle("is-active", active);
        other.setAttribute("aria-selected", String(active));
      });
      if (heroHeading && heroHeading.dataset[mode]) {
        heroHeading.textContent = heroHeading.dataset[mode];
      }
      if (heroSub && heroSub.dataset[mode]) {
        heroSub.innerHTML = heroSub.dataset[mode];
        if (!prefersReducedMotion) {
          heroSub.style.animation = "none";
          void heroSub.offsetWidth;
          heroSub.style.animation = "";
        }
      }
      if (heroPrimary && heroPrimary.dataset[mode]) {
        heroPrimary.innerHTML = heroPrimary.dataset[mode];
      }
    });
  });
}

/* ---------- TextRoll: wrap text in letter spans with staggered hover roll ---------- */
function buildTextRoll(root) {
  const targets = root.matches?.(".roll")
    ? [root]
    : root.querySelectorAll(".roll");
  targets.forEach((el) => {
    if (el.dataset.rolled === "1") return;
    const text = el.textContent;
    el.textContent = "";
    [...text].forEach((char, i) => {
      const span = document.createElement("span");
      span.className = "roll-char";
      // Replace spaces with non-breaking spaces so they do not collapse.
      span.textContent = char === " " ? " " : char;
      span.style.setProperty("--roll-delay", `${i * 18}ms`);
      el.appendChild(span);
    });
    el.dataset.rolled = "1";
  });
}

if (!prefersReducedMotion && "IntersectionObserver" in window) {
  const rollObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          buildTextRoll(entry.target);
          rollObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.2 }
  );
  document.querySelectorAll(".roll").forEach((el) => rollObserver.observe(el));
} else {
  document.querySelectorAll(".roll").forEach(buildTextRoll);
}

/* ---------- Moving-shader background (canvas) ---------- */
(function initShader() {
  const canvas = document.getElementById("bg-shader");
  if (!canvas) return;

  // CSS-gradient fallback already covers the element background, so if the
  // canvas cannot run, the page still looks correct.
  const supportsCanvas =
    canvas.getContext && typeof canvas.getContext("2d") === "function";
  if (!supportsCanvas) return;

  const ctx = canvas.getContext("2d");
  const reduce = prefersReducedMotion;

  // Cap pixel density per blueprint (<= 0.5).
  const density = Math.min(window.devicePixelRatio || 1, 0.5);

  let width = 0;
  let height = 0;
  let blobs = [];

  function resize() {
    width = canvas.clientWidth || window.innerWidth;
    height = canvas.clientHeight || window.innerHeight;
    canvas.width = Math.max(1, Math.floor(width * density));
    canvas.height = Math.max(1, Math.floor(height * density));
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    seed();
  }

  // Re-seed with the theme-appropriate palette when the user toggles.
  window.addEventListener("softmarket:themechange", () => {
    seed();
    if (!running && !reduce) frame();
  });

  function seed() {
    // Palette flips with the theme so the shader reads well on both
    // the carbon (dark) and frost (light) backgrounds.
    const darkPalette = [
      "rgba(16, 185, 129, 0.55)",
      "rgba(10, 40, 28, 0.9)",
      "rgba(210, 255, 0, 0.12)",
      "rgba(8, 24, 16, 0.95)",
    ];
    const lightPalette = [
      "rgba(16, 40, 28, 0.18)",
      "rgba(120, 140, 125, 0.22)",
      "rgba(40, 60, 45, 0.14)",
      "rgba(90, 110, 95, 0.2)",
    ];
    const palette = isDarkTheme() ? darkPalette : lightPalette;
    const count = reduce ? 3 : 5;
    blobs = [];
    for (let i = 0; i < count; i++) {
      blobs.push({
        x: Math.random() * width,
        y: Math.random() * height,
        r: (0.28 + Math.random() * 0.32) * Math.max(width, height),
        vx: (Math.random() - 0.5) * (reduce ? 0 : 0.18),
        vy: (Math.random() - 0.5) * (reduce ? 0 : 0.14),
        color: palette[i % palette.length],
      });
    }
  }

  function frame() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.globalCompositeOperation = "lighter";
    for (const b of blobs) {
      if (!reduce) {
        b.x += b.vx;
        b.y += b.vy;
        if (b.x < -b.r) b.x = width + b.r;
        if (b.x > width + b.r) b.x = -b.r;
        if (b.y < -b.r) b.y = height + b.r;
        if (b.y > height + b.r) b.y = -b.r;
      }
      const grad = ctx.createRadialGradient(b.x, b.y, 0, b.x, b.y, b.r);
      grad.addColorStop(0, b.color);
      grad.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
  }

  resize();
  window.addEventListener("resize", resize);

  if (reduce) {
    frame(); // single static paint, no loop
    return;
  }

  // Bind the rAF loop to visibility: pause when tab hidden or canvas off-screen.
  let running = false;
  let rafId = null;

  function start() {
    if (running) return;
    running = true;
    const loop = () => {
      if (!running) return;
      frame();
      rafId = requestAnimationFrame(loop);
    };
    rafId = requestAnimationFrame(loop);
  }

  function stop() {
    running = false;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
  }

  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && !document.hidden) start();
          else stop();
        });
      },
      { threshold: 0 }
    );
    io.observe(canvas);
  } else {
    start();
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
    else if (canvas.getBoundingClientRect().bottom > 0) start();
  });
})();

/* ---------- Autoplay demo loops when they scroll into view ---------- */
const loopVideos = document.querySelectorAll(".loop-video");
if (loopVideos.length && "IntersectionObserver" in window && !prefersReducedMotion) {
  const videoObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        const video = entry.target;
        const card = video.closest(".media-row, .voice-card");
        if (entry.isIntersecting) {
          const playPromise = video.play();
          if (playPromise && typeof playPromise.catch === "function") {
            playPromise.catch(() => {});
          }
          if (card) card.classList.add("is-playing");
        } else {
          video.pause();
          if (card) card.classList.remove("is-playing");
        }
      });
    },
    { threshold: 0.35 }
  );
  loopVideos.forEach((video) => videoObserver.observe(video));
}

/* ---------- Hero scroll cue ---------- */
const heroScrollCue = document.querySelector(".hero-scroll-cue");
if (heroScrollCue) {
  heroScrollCue.addEventListener("click", (event) => {
    event.preventDefault();
    const target = document.querySelector("#services");
    if (target) target.scrollIntoView({ behavior: prefersReducedMotion ? "auto" : "smooth" });
  });
}

/* ---------- Quote form -> WhatsApp + Django backup ---------- */
function formDataToObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function createWhatsappUrl(message) {
  return `https://wa.me/${BUSINESS_WHATSAPP_NUMBER}?text=${encodeURIComponent(message)}`;
}

function formatUtmLine() {
  const entries = Object.entries(collectedUtm);
  if (!entries.length) return "Campaign source: direct or unknown";
  return `Campaign source: ${entries
    .map(([key, value]) => `${key}=${value}`)
    .join(", ")}`;
}

function submitDjangoBackup(form, resultElement) {
  const formData = new FormData(form);
  return fetch(form.action || "/", {
    method: "POST",
    body: formData,
  })
    .then((response) => {
      if (!response.ok) throw new Error("Backup submission failed");
      resultElement.append(" Your inquiry was saved.");
      form.reset();
      fillUtmFields(form);
    })
    .catch(() => {
      resultElement.append(
        " If saving fails, use the WhatsApp link above to send the inquiry."
      );
    });
}

function openPreparedMessage(message, resultElement, form) {
  const url = createWhatsappUrl(message);
  const link = document.createElement("a");
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = "Open prepared WhatsApp message";
  link.className = "prepared-link";

  resultElement.textContent = "";
  resultElement.append(link);
  window.open(url, "_blank", "noopener");
  return submitDjangoBackup(form, resultElement);
}

document.querySelector("#quoteForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const result = document.querySelector("#quoteResult");
  const submitButton = form.querySelector('button[type="submit"]');
  const data = formDataToObject(form);

  const message = [
    "Hello SoftMarket Kenya, I would like to discuss a project.",
    `Name: ${data.name}`,
    `Email: ${data.email}`,
    `Phone: ${data.phone}`,
    `Service: ${data.service}`,
    `Budget: ${data.budget}`,
    `Timeline: ${data.timeline}`,
    `Project details: ${data.details}`,
    formatUtmLine(),
  ].join("\n");

  submitButton.disabled = true;
  openPreparedMessage(message, result, form).finally(() => {
    submitButton.disabled = false;
  });
});
