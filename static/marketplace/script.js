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

const revealElements = document.querySelectorAll(".reveal");
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

if (reduceMotion || !("IntersectionObserver" in window)) {
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

function formDataToObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function createWhatsappUrl(message) {
  return `https://wa.me/${BUSINESS_WHATSAPP_NUMBER}?text=${encodeURIComponent(message)}`;
}

function formatUtmLine() {
  const entries = Object.entries(collectedUtm);
  if (!entries.length) return "Campaign source: direct or unknown";
  return `Campaign source: ${entries.map(([key, value]) => `${key}=${value}`).join(", ")}`;
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
      resultElement.append(" If saving fails, use the WhatsApp link above to send the inquiry.");
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
