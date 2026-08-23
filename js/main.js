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
