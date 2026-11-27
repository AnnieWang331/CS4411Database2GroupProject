# Final report

This folder is our final report. It's LaTeX made to look like the course's overleaf template, same
as our proposal. Edit the files here and open a PR like any other change in the repo.

## Where things are

```
main.tex                    Title page, abstract, contents and the order of the sections
01-introduction.tex ...     One file per section, so we can work on different ones at once
12-conclusion.tex
appendix-*.tex              Appendix A (reproducing our results) and B (all access patterns)
references.bib              All our references, cited with \cite{key}
IEEEtran.bst                The IEEE reference style, here so the report builds anywhere
figures/                    Images that only the report uses (the Western logo)
```

Each section starts with `\section{...}\label{sec:...}`. To point at another section, use
`Section~\ref{sec:...}`, for example `Section~\ref{sec:data-model}`. New references go in
`references.bib` with the page's title and link.

## Getting the PDF

Easiest first:

- No installs: ci builds the report on every PR and push to `main`. Open the run in the Actions
  tab and download `report-pdf` under Artifacts.
- With LaTeX installed (TeX Live, MacTeX or MiKTeX):

  ```sh
  cd report
  latexmk -pdf main.tex
  ```

  No `latexmk`? Run `pdflatex main`, `bibtex main`, then `pdflatex main` twice.
- With podman or docker, no LaTeX install needed:

  ```sh
  podman run --rm -v "$PWD/report:/w:Z" -w /w docker.io/texlive/texlive:latest-medium \
    latexmk -pdf main.tex
  ```

- On overleaf: upload everything in this folder to a blank project. It's only for viewing, so
  copy any changes back here or they'll get lost.

Build files (`main.pdf`, `*.aux`, `*.log` etc.) aren't committed.
