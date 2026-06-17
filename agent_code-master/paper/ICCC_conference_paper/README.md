# ICCC Conference Paper

The paper follows the supplied IEEE conference template.

## Build

```powershell
pdflatex -interaction=nonstopmode conference_paper.tex
bibtex conference_paper
pdflatex -interaction=nonstopmode conference_paper.tex
pdflatex -interaction=nonstopmode conference_paper.tex
```

## Files

- `conference_paper.tex`: complete conference manuscript.
- `references.bib`: bibliography used by the manuscript.
- `IEEEtran.cls`: class file copied from the supplied template.
- `template_original.tex`: unmodified source template for reference.
- `figures/`: English publication-ready figures generated from the code and
  experiment JSON.

The author block is intentionally anonymous because no author or affiliation
information was provided. Replace it before a camera-ready submission.

The compiled manuscript is six IEEE conference pages. All manuscript figures
use single-column placement. The complete load--failure heatmap is retained as
`figures/scheduler_pressure.png`; the main manuscript uses a compact
pressure-test table to keep the paper dense.
