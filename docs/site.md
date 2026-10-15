# The explorer site: links and frozen copies

The explorer (`ui/explorer.html`, built by `scripts/build_ui_site.py`) is published to GitHub
Pages from `main` by `.github/workflows/pages.yml`.

## Links to a view

The address holds the whole view, so a copied link opens exactly what was on screen:

    #<run>/<step>?at=<lat>,<lng>,<zoom>&on=..&off=..&feature=..&type=..&measure=..&compare=<a>,<b>

| Part | Meaning |
|---|---|
| `<run>` | the run id from `ui_data/index.json` (place, features, stand size, area and land choice) |
| `<step>` | `area`, `land`, `measure`, `superpixels`, `stands`, `types`, `profiles`, `field` |
| `at` | the map's centre and zoom |
| `on`, `off` | layer ids switched on or off against the step's own set |
| `feature` | the measurement shown in the Measures step |
| `type`, `measure` | Profiles: the stand type in focus and the box-plot measurement |
| `compare` | the one or two stand ids compared |

Only what differs from the step's defaults is written. "Copy link to this view" (next to "How this
step works") copies the address.

## Frozen copies for citing

The live site changes whenever new runs are merged, so a link to it may later show other stands.
For a write-up, cite a frozen copy instead:

1. Choose the commit on `main` whose site you want to cite (usually the latest).
2. Tag it with a name starting `paper-` and push the tag:

       git tag paper-v1 <commit>
       git push origin paper-v1

3. The Pages workflow runs on the tag and publishes that commit's site at
   `https://<user>.github.io/phd-code/v/paper-v1/` beside the live one. Every later build keeps
   it, built again from the same tagged commit, so it does not change.
4. Open the frozen copy, set up each view, and use "Copy link to this view": the link keeps the
   `/v/paper-v1/` part. The frozen page says it is a frozen copy and links to the same view on the
   live site.

Never move or delete a `paper-*` tag once cited: the copy is rebuilt from it on every deploy.
Each copy adds about 35 MB to the site (GitHub Pages allows 1 GB in all).
