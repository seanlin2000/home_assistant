// Arithmatex wraps each formula in an .arithmatex element with \( \) or \[ \] delimiters; KaTeX, vendored under assets/katex/, typesets only those elements.
// Material emits document$ on the first load and again after every instant navigation, so a page reached without a full reload is typeset too.
document$.subscribe(({ body }) => {
  for (const formula of body.querySelectorAll(".arithmatex")) {
    renderMathInElement(formula, {
      delimiters: [
        { left: "\\(", right: "\\)", display: false },
        { left: "\\[", right: "\\]", display: true },
      ],
    });
  }
});
