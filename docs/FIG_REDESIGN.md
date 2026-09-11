# Fig portfolio redesign

## Design

Original implementation inspired by the section hierarchy of [Folio](https://themewagon.github.io/folio-tailwind/#about): a split introduction, capability cards, selected work, a split About section, professional background, and contact links. No template testimonials, client counts, biography, photographs, or blog entries were reused.

The site retains the full profile, all four original projects, self-contained analytical presentations, and the RiskOps source package. The newer SupportOps addition is also preserved, bringing selected work to five projects. Existing #projects and #automation bookmarks lead to selected work.

| DMC reference | Screen approximation | Role |
| --- | --- | --- |
| 336 — Navy Blue | #253B73 | Main text, controls, dark project panels |
| 553 — Violet | #A3638B | Large accents; #774268 for readable small text |
| 772 — Very Light Yellow Green | #E4ECD4 | Section background and dark-surface text |
| 900 — Dark Burnt Orange | #D15807 | Brand detail and focus accents |

Names follow [DMC's numerical color list](https://www.dmc.com/media/color_charts/DMC_Embroidery_Floss_Numerical_List_2021.pdf). Thread colors vary with lighting and screens; these are design approximations, not official measured hex values. The neutral canvas is #FAF8F2.

## RiskOps presentation

The main interface uses operational labels and concise descriptions. Repeated synthetic/AI disclaimers have been removed from prominent headings and banners. It continues to identify historical snapshots and recorded playback; no live feeds, production deployment, customer adoption, or model-service calls are claimed. The project README and source evidence preserve the actual synthetic input basis, proxy calculations, and rules-based reporting method. Data, calculations, archived logs, metric values, and test evidence are unchanged.

## Preservation and branches

- Full pre-change backup: ../Website-Backups/portfolio-before-fig-2026-09-11 relative to the repository directory.
- The backup contains 202 files, including Git history, untracked project materials, and local run state; all file hashes were compared with the original before editing.
- Previous-design branch: backup/pre-fig-2026-09-11, baseline commit d2c5466.
- Active redesign branch: main, newly created from that preserved baseline.
- Publication target: origin/main and the existing GitHub Pages site at https://bjabour.github.io/professional-projects/. The previous-design branch is retained separately for recovery.
- Existing untracked energy and housing source folders were preserved and excluded from the redesign commits.

To inspect the previous version without touching this working directory, open index.html in the full backup. For Git-based recovery, create a separate worktree from backup/pre-fig-2026-09-11. Do not reset or overwrite a dirty working directory.

## Maintenance

The homepage and full profile are static HTML/CSS/JavaScript with no dependency installation. The RiskOps README contains its separate reproducible run and build commands. Rebuild the RiskOps pages after template changes. Main navigation has keyboard-accessible mobile controls, visible focus styling, section anchors, and reduced-motion support.
