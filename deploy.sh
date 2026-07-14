# One-shot deploy for Windows PowerShell. Requires git + gh (GitHub CLI), authenticated.
$ErrorActionPreference = "Stop"
$repo = "ys-game"
$owner = (gh api user --jq .login)
Write-Host "Creating public repo $owner/$repo and pushing..."
git init | Out-Null
git add -A
git -c commit.gpgsign=false commit -m "YS Proto v0.22 - PWA" | Out-Null
git branch -M main
gh repo create $repo --public --source=. --remote=origin --push --description "YS action prototype (PWA)"
Write-Host "Enabling GitHub Pages (main / root)..."
try { gh api -X POST "repos/$owner/$repo/pages" -f "source[branch]=main" -f "source[path]=/" } catch { Write-Host "Enable Pages manually: Settings -> Pages -> Branch main / root" }
Write-Host "Done: https://$owner.github.io/$repo/"
