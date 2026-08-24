document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-current-year]").forEach((element) => {
    element.textContent = new Date().getFullYear();
  });

  function labelExternalLinks(root = document) {
    root.querySelectorAll('a[target="_blank"]').forEach((link) => {
      if (!link.hasAttribute("aria-label")) {
        link.setAttribute("aria-label", `${link.textContent.trim()} (opens in a new tab)`);
      }
    });
  }

  labelExternalLinks();

  new MutationObserver(() => labelExternalLinks())
    .observe(document.body, { childList: true, subtree: true });

  document.addEventListener("click", (event) => {
    const toggle = event.target.closest(".pub-figures-toggle");
    if (!toggle) return;

    const figures = toggle.closest(".pub-figures");
    const panel = figures.querySelector(".pub-figures-panel");
    const label = toggle.querySelector("[data-figures-toggle-label]");
    const willOpen = toggle.getAttribute("aria-expanded") !== "true";

    toggle.setAttribute("aria-expanded", String(willOpen));
    panel.setAttribute("aria-hidden", String(!willOpen));
    panel.inert = !willOpen;
    panel.querySelectorAll("button, a").forEach((control) => {
      if (willOpen) {
        control.removeAttribute("tabindex");
      } else {
        control.setAttribute("tabindex", "-1");
      }
    });
    label.textContent = willOpen ? "Hide figures" : "Show figures";

    if (willOpen) {
      panel.hidden = false;
      void panel.offsetHeight;
      figures.classList.add("is-open");
    } else {
      figures.classList.remove("is-open");
      window.setTimeout(() => {
        if (!figures.classList.contains("is-open")) panel.hidden = true;
      }, 460);
    }
  });

  const lightbox = document.createElement("dialog");
  lightbox.className = "figure-lightbox";
  lightbox.setAttribute("aria-label", "Full-size publication figure");
  lightbox.innerHTML = `
    <div class="figure-lightbox-panel">
      <div class="figure-lightbox-toolbar">
        <div class="figure-lightbox-toolbar-group">
          <button type="button" data-lightbox-previous aria-label="Previous figure">← Previous</button>
          <button type="button" data-lightbox-next aria-label="Next figure">Next →</button>
        </div>
        <span class="figure-lightbox-counter" aria-live="polite"></span>
        <div class="figure-lightbox-toolbar-group">
          <button type="button" data-lightbox-zoom aria-pressed="false">Actual size</button>
          <button type="button" data-lightbox-close>Close</button>
        </div>
      </div>
      <div class="figure-lightbox-image-wrap">
        <img class="figure-lightbox-image" alt="">
      </div>
      <div class="figure-lightbox-caption">
        <p><strong data-lightbox-label></strong> <span data-lightbox-caption></span></p>
        <div class="figure-lightbox-meta">
          <a data-lightbox-source target="_blank" rel="noopener">Source article</a>
          <a data-lightbox-license target="_blank" rel="noopener"></a>
        </div>
      </div>
    </div>`;
  document.body.appendChild(lightbox);

  const lightboxImageWrap = lightbox.querySelector(".figure-lightbox-image-wrap");
  const lightboxImage = lightbox.querySelector(".figure-lightbox-image");
  const lightboxLabel = lightbox.querySelector("[data-lightbox-label]");
  const lightboxCaption = lightbox.querySelector("[data-lightbox-caption]");
  const lightboxSource = lightbox.querySelector("[data-lightbox-source]");
  const lightboxLicense = lightbox.querySelector("[data-lightbox-license]");
  const lightboxCounter = lightbox.querySelector(".figure-lightbox-counter");
  const previousButton = lightbox.querySelector("[data-lightbox-previous]");
  const nextButton = lightbox.querySelector("[data-lightbox-next]");
  const zoomButton = lightbox.querySelector("[data-lightbox-zoom]");
  let lightboxTriggers = [];
  let lightboxIndex = 0;
  let lastFigureTrigger = null;

  function setLightboxZoom(actualSize) {
    lightboxImageWrap.classList.toggle("is-actual-size", actualSize);
    zoomButton.setAttribute("aria-pressed", String(actualSize));
    zoomButton.textContent = actualSize ? "Fit to screen" : "Actual size";
    lightboxImageWrap.scrollTo(0, 0);
  }

  function showLightboxFigure(index) {
    if (!lightboxTriggers.length) return;
    lightboxIndex = (index + lightboxTriggers.length) % lightboxTriggers.length;
    const trigger = lightboxTriggers[lightboxIndex];
    const { label, caption, fullSrc, source, license, licenseUrl } = trigger.dataset;

    setLightboxZoom(false);
    lightboxImage.src = fullSrc;
    lightboxImage.alt = `${label}: ${caption}`;
    lightboxLabel.textContent = `${label}.`;
    lightboxCaption.textContent = caption;
    lightboxCounter.textContent = `${lightboxIndex + 1} / ${lightboxTriggers.length}`;

    lightboxSource.hidden = !source;
    if (source) lightboxSource.href = source;

    lightboxLicense.hidden = !license;
    lightboxLicense.textContent = license;
    if (licenseUrl) {
      lightboxLicense.href = licenseUrl;
    } else {
      lightboxLicense.removeAttribute("href");
    }

    const hasMultipleFigures = lightboxTriggers.length > 1;
    previousButton.disabled = !hasMultipleFigures;
    nextButton.disabled = !hasMultipleFigures;
  }

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest(".pub-figure-trigger");
    if (!trigger) return;

    lightboxTriggers = Array.from(
      trigger.closest(".pub-figure-grid").querySelectorAll(".pub-figure-trigger")
    );
    lastFigureTrigger = trigger;
    showLightboxFigure(lightboxTriggers.indexOf(trigger));
    lightbox.showModal();
    document.body.classList.add("figure-lightbox-open");
  });

  previousButton.addEventListener("click", () => showLightboxFigure(lightboxIndex - 1));
  nextButton.addEventListener("click", () => showLightboxFigure(lightboxIndex + 1));
  zoomButton.addEventListener("click", () => {
    setLightboxZoom(!lightboxImageWrap.classList.contains("is-actual-size"));
  });
  lightbox.querySelector("[data-lightbox-close]").addEventListener("click", () => {
    lightbox.close();
  });

  lightbox.addEventListener("click", (event) => {
    if (event.target === lightbox) lightbox.close();
  });

  lightbox.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") showLightboxFigure(lightboxIndex - 1);
    if (event.key === "ArrowRight") showLightboxFigure(lightboxIndex + 1);
    if (event.key === "Escape") {
      event.preventDefault();
      lightbox.close();
    }
  });

  lightbox.addEventListener("cancel", (event) => {
    event.preventDefault();
    lightbox.close();
  });

  lightbox.addEventListener("close", () => {
    document.body.classList.remove("figure-lightbox-open");
    lightboxImage.removeAttribute("src");
    lastFigureTrigger?.focus();
  });

  const backButton = document.querySelector(".float-back");
  const projects = document.getElementById("projects");

  if (backButton && projects) {
    const updateBackButton = () => {
      backButton.classList.toggle("hidden", projects.getBoundingClientRect().bottom >= 0);
    };

    updateBackButton();
    window.addEventListener("scroll", updateBackButton, { passive: true });
    backButton.addEventListener("click", () => backButton.classList.add("hidden"));
  }
});
