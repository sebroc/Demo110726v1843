# Lecture notes PreTeXt preview

Run `python3 Notes/pretext/preview.py` from the project root. The script builds
the PreTeXt book, prints its local preview URL, and rebuilds whenever
one of the original `Notes/Chap*/Chap*-lectures.tex` files changes.

The original TeX files remain the source. `build.py` generates `source/*.ptx`.
Do not edit those generated files; changes will be overwritten on the next build.

For GitHub Pages, include the chapter TeX files and PNGs, this directory's
Python scripts, requirements and `project.ptx`, and the workflow at
`.github/workflows/pretext-pages.yml`. In the GitHub repository, select
**Settings → Pages → Source → GitHub Actions**. Run **Publish lecture notes**
from the Actions tab for the first deployment. Later pushes to the default
branch rebuild the site when the notes or build files change. The workflow
publishes only the generated HTML and its assets, including activity solutions.
