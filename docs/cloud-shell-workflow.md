# Flux: GitHub + GCP Cloud Shell Development Workflow (Phase 1)

This guide sets up the Flux control-plane repository and the day-to-day
development workflow using **Google Cloud Shell** as the only development
environment. Every command is written for Cloud Shell.

Replace these placeholders wherever they appear:

- `GH_USER`      your GitHub username
- `PROJECT_ID`   your GCP project id
- `REGION`       your chosen region, for example `us-central1`

Legend: **[once]** = do a single time and it persists; **[session]** = may need
repeating when a fresh Cloud Shell VM is allocated; **[browser]** = requires a
click in the browser tab that opens.

---

## 0. How Cloud Shell persistence works (read this first)

Cloud Shell gives you an ephemeral VM with a **persistent `$HOME`** (about 5 GB).
The practical rules that shape this whole workflow:

- Anything under `$HOME` (`/home/YOUR_USER`) survives across sessions. Your repo,
  your `.pyenv`, your virtualenv, your Git and `gh` credentials all live here.
- Anything installed outside `$HOME` (for example `sudo apt install ...`) is wiped
  when a new VM is allocated. So we install Python with **pyenv inside `$HOME`**,
  never with apt.
- `gcloud` is already authenticated as your Google account. `git`, `gh`, and
  `docker` are preinstalled.
- The VM stops after inactivity and you get a weekly usage allowance. Nothing in
  `$HOME` is lost when it stops.

Put the project in `$HOME` and everything else follows.

---

## 1. Open Cloud Shell and select your project  [session]

Open Cloud Shell from the Google Cloud console (the terminal icon, top right),
then point it at your project:

    gcloud config set project PROJECT_ID
    gcloud config set compute/region REGION
    gcloud config list

If you do not have a project yet:

    gcloud projects create PROJECT_ID
    gcloud config set project PROJECT_ID
    # then link billing in the console: Billing > Link a billing account

---

## 2. Configure your Git identity  [once]

This writes to `$HOME/.gitconfig`, so it persists.

    git config --global user.name  "Your Name"
    git config --global user.email "you@example.com"
    git config --global init.defaultBranch main
    git config --global pull.rebase true
    git config --global push.autoSetupRemote true
    git config --global core.editor "nano"   # or vim

`pull.rebase true` keeps a linear history; `push.autoSetupRemote` means a bare
`git push` on a new branch just works.

---

## 3. Authenticate to GitHub from Cloud Shell  [once] [browser]

Use the GitHub CLI (`gh`), which is preinstalled in Cloud Shell. It stores its
token under `$HOME/.config/gh`, so authentication persists across sessions.

    gh auth login

Answer the prompts:

- Account: **GitHub.com**
- Protocol: **HTTPS**
- Authenticate Git with your GitHub credentials: **Yes**
- How to authenticate: **Login with a web browser**

Copy the one-time code shown, open the printed URL in a new browser tab, paste the
code, and authorize. Then wire `gh` in as Git's credential helper so `git push`
and `git pull` never prompt for a password:

    gh auth setup-git
    gh auth status        # verify

You now never handle a Personal Access Token by hand. If you ever prefer SSH
instead, run `gh auth login` and choose SSH; `gh` will offer to generate and
upload a key for you.

---

## 4. Get the Flux code into Cloud Shell

You already have `flux-phase1.zip` from the build. Upload it and unpack it into
`$HOME`.

1. In the Cloud Shell toolbar, open the three-dot overflow menu and choose
   **Upload**, then select `flux-phase1.zip`. It lands in `$HOME`.
2. Unpack it:

        cd ~
        mkdir -p flux
        unzip -o flux-phase1.zip -d flux
        cd flux
        ls -la

You should see `pyproject.toml`, `src/`, `tests/`, `migrations/`, `Dockerfile`,
and the rest. The `.gitignore` is already included and already excludes `.env`,
virtualenvs, and caches, so secrets will not be committed.

---

## 5. Create the GitHub repository and push  [browser on first push]

From inside `~/flux`, initialize Git and let `gh` create the remote and push in
one step.

    cd ~/flux
    git init -b main
    git add .
    git commit -m "chore: phase 1 foundation and model registry"

    gh repo create flux \
      --private \
      --source=. \
      --remote=origin \
      --push \
      --description "GPU-accelerated ML inference and model serving platform (control plane)"

`--source=.` uses the current directory, `--remote=origin` names the remote, and
`--push` uploads `main`. Confirm:

    git remote -v
    gh repo view --web     # opens the repo in your browser

Use `--public` instead of `--private` if you want it visible to reviewers now. You
can also flip visibility later with `gh repo edit --visibility public`.

---

## 6. Branch model and protecting `main`

For a solo, review-quality project, use **trunk-based development**: `main` is
always releasable, and each unit of work is a short-lived branch merged through a
Pull Request.

Naming convention (Conventional Commits style prefixes):

- `feat/...`   new capability, e.g. `feat/tenancy-management`
- `fix/...`    bug fix
- `chore/...`  tooling, deps, config
- `docs/...`   documentation
- `test/...`   tests only
- `refactor/...`

Protect `main` so history stays clean (do this once, in the browser or by CLI):

    gh api -X PUT repos/GH_USER/flux/branches/main/protection \
      -H "Accept: application/vnd.github+json" \
      -f "required_pull_request_reviews[required_approving_review_count]=0" \
      -F "enforce_admins=true" \
      -F "required_status_checks=null" \
      -F "restrictions=null"

This requires changes to arrive via PR and blocks direct force-pushes to `main`.
Once CI exists (Phase 6), add `required_status_checks` so tests must pass before a
merge is allowed.

Tag each completed phase so milestones are visible:

    git tag -a v0.1.0-phase1 -m "Phase 1: foundation + model registry"
    git push origin v0.1.0-phase1

---

## 7. Python 3.12 environment  [once for pyenv, then persists]

The project targets Python 3.12. Rather than rely on the VM's default, install
3.12 with **pyenv** inside `$HOME` so it survives VM recycling.

    curl -fsSL https://pyenv.run | bash

    cat >> ~/.bashrc <<'RC'

    # pyenv
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
    RC

    exec $SHELL          # reload the shell
    pyenv install 3.12.6
    cd ~/flux
    pyenv local 3.12.6   # writes .python-version (git-ignored is fine)
    python --version     # -> Python 3.12.6

Create the virtualenv **inside the repo under `$HOME`** and install the project
with its dev extras:

    python -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -e ".[dev]"

Add `source ~/flux/.venv/bin/activate` to the end of `~/.bashrc` if you want the
environment active automatically in new tabs. The `.venv` and `.python-version`
entries are already covered by `.gitignore`.

Run the quality gates to confirm the toolchain:

    make lint
    make typecheck
    make test

---

## 8. Environment configuration and running locally

Create your `.env` from the template and set a real pepper (never commit `.env`):

    cd ~/flux
    cp .env.example .env
    sed -i "s/^FLUX_API_KEY_PEPPER=.*/FLUX_API_KEY_PEPPER=$(openssl rand -hex 32)/" .env

Docker is available in Cloud Shell, so run Postgres with Compose, then migrate,
seed, and start the app:

    docker compose up -d db          # Postgres on localhost:5432
    make migrate                     # alembic upgrade head
    make seed                        # prints a one-time API key: copy it

    # run on 8080 so Cloud Shell Web Preview works out of the box
    uvicorn flux.api.app:app --host 0.0.0.0 --port 8080 --reload

Click **Web Preview** (the eye/screen icon in the Cloud Shell toolbar), preview on
port **8080**, and append `/docs` to the URL for the interactive API. Or from a
second Cloud Shell tab:

    curl localhost:8080/livez
    curl -H "Authorization: Bearer <API_KEY_FROM_SEED>" \
         localhost:8080/v1/models

To exercise the whole stack in containers instead:

    make compose-up      # builds the image, starts Postgres, runs migrations
    make compose-down    # tears it down and removes volumes

---

## 9. Connect GitHub to GCP (Cloud Build 2nd gen)  [once] [browser]

This establishes the link that later CI/CD (Phase 6) builds on: GCP is authorized
to read your GitHub repo, and you have an Artifact Registry to receive images. No
build triggers are created yet.

Enable the required APIs:

    gcloud services enable \
      cloudbuild.googleapis.com \
      artifactregistry.googleapis.com \
      secretmanager.googleapis.com

Create an Artifact Registry Docker repository (destination for future images):

    gcloud artifacts repositories create flux \
      --repository-format=docker \
      --location=REGION \
      --description="Flux container images"

Create the GitHub host connection. This prints a URL you must open to authorize
Cloud Build and install its GitHub App on your account:

    gcloud builds connections create github flux-github \
      --region=REGION
    # open the printed URL, authorize, and install the Cloud Build GitHub App

    gcloud builds connections describe flux-github --region=REGION
    # confirm installationState is COMPLETE

Link your repository to the connection:

    gcloud builds repositories create flux \
      --remote-uri=https://github.com/GH_USER/flux.git \
      --connection=flux-github \
      --region=REGION

    gcloud builds repositories list --connection=flux-github --region=REGION

The repository is now linked to GCP. When you reach Phase 6, a build trigger is a
single additional command against this linked repository, for example (do NOT run
this yet; there is no `cloudbuild.yaml` until Phase 6):

    # PHASE 6 PREVIEW, not for now:
    # gcloud builds triggers create github \
    #   --name=flux-ci \
    #   --region=REGION \
    #   --repository=projects/PROJECT_ID/locations/REGION/connections/flux-github/repositories/flux \
    #   --branch-pattern="^main$" \
    #   --build-config=cloudbuild.yaml

---

## 10. Daily development workflow (the loop)

Repeat this cycle for every unit of Phase 1 (and every later phase):

    # 1. Start from an up-to-date main
    cd ~/flux
    git switch main
    git pull

    # 2. Branch for the task
    git switch -c feat/short-description

    # 3. Make the venv active and work
    source .venv/bin/activate
    #    ...edit code...

    # 4. Run the gates locally BEFORE committing
    make lint
    make typecheck
    make test

    # 5. Stage and commit in small, meaningful steps (Conventional Commits)
    git add -p
    git commit -m "feat: add tenant provisioning use case"

    # 6. Push the branch
    git push        # autoSetupRemote creates origin/feat/... on first push

    # 7. Open a Pull Request and review your own diff
    gh pr create --fill
    gh pr view --web

    # 8. Merge (squash keeps main history tidy), then clean up
    gh pr merge --squash --delete-branch
    git switch main
    git pull

Conventional Commit prefixes to use in messages: `feat`, `fix`, `docs`, `test`,
`refactor`, `chore`, `perf`, `build`, `ci`. They read well in history and make an
automated changelog trivial later.

Guardrails:

- Never commit `.env`, the API key from `make seed`, or `.venv`. They are all in
  `.gitignore` already; keep it that way.
- Keep PRs small (one use case or one slice). Your future reviewers, and you, will
  thank you.
- Let the gates fail you locally, not in review. `make lint typecheck test` is the
  contract.

---

## 11. Cloud Shell survival notes

- **Long-running processes**: use `tmux` so a dropped connection does not kill the
  server. `tmux new -s flux`, detach with `Ctrl-b d`, reattach with
  `tmux attach -t flux`.
- **Reconnecting after a VM recycle**: your repo and `$HOME` are intact. You may
  need to re-activate the venv (`source ~/flux/.venv/bin/activate`) and restart
  `docker compose up -d db`. pyenv, Git, and `gh` credentials persist.
- **More memory for `docker compose`**: enable **Boost Mode** from the Cloud Shell
  settings if builds feel starved.
- **Editor**: run `cloudshell edit .` (or click **Open Editor**) to use the
  built-in VS Code style editor over the same files.

---

## 12. Quick reference

    # project + auth
    gcloud config set project PROJECT_ID
    gh auth status

    # environment
    source ~/flux/.venv/bin/activate
    docker compose up -d db

    # gates
    make lint && make typecheck && make test

    # run (preview on 8080)
    uvicorn flux.api.app:app --host 0.0.0.0 --port 8080 --reload

    # git loop
    git switch main && git pull
    git switch -c feat/x
    git add -p && git commit -m "feat: x"
    git push
    gh pr create --fill
    gh pr merge --squash --delete-branch
