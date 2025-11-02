document.addEventListener("DOMContentLoaded", () => {
  // Footer year
  const y = document.getElementById("year");
  if (y) y.textContent = new Date().getFullYear();

  // Theme toggle
  const toggle = document.getElementById("themeToggle");
  const root = document.documentElement;
  const stored = localStorage.getItem("theme");
  if (stored === "light") root.classList.add("light");
  toggle?.addEventListener("click", () => {
    root.classList.toggle("light");
    localStorage.setItem("theme", root.classList.contains("light") ? "light" : "dark");
  });

  // Tabs: Research / Music
  const buttons = Array.from(document.querySelectorAll(".tab-btn"));
  const panels = Array.from(document.querySelectorAll(".panel"));

  function activate(targetSel){
    buttons.forEach(b => b.classList.toggle("active", b.dataset.target === targetSel));
    panels.forEach(p => p.classList.toggle("active", `#${p.id}` === targetSel));
    const activePanel = document.querySelector(targetSel);
    activePanel?.focus({ preventScroll: false });
  }

  // Default to first tab
  if (buttons.length) {
    buttons[0].classList.add("active");
    panels[0]?.classList.add("active");
  }

  buttons.forEach(btn => {
    btn.addEventListener("click", () => activate(btn.dataset.target));
  });
});
