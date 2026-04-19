# Self-Hosted Runner Setup

This repository's CI workflow is configured to run on a Windows self-hosted GitHub Actions runner with the labels `self-hosted`, `Windows`, and `X64`.

## What it does

- Runs automatically on `push`
- Runs automatically on `pull_request`
- Can be started manually from the GitHub Actions page through `Run workflow`

## Set up this computer as the runner

1. Open the target GitHub repository in the browser.
2. Go to `Settings` -> `Actions` -> `Runners` -> `New self-hosted runner`.
3. Choose `Windows` and `x64`.
4. Copy the commands GitHub shows and run them on this computer inside a dedicated folder such as `C:\actions-runner\careerpilot`.
5. During configuration, keep the default labels so the runner includes `self-hosted`, `Windows`, and `X64`.
6. Install the runner as a Windows service so it starts automatically after reboot.

## Recommended commands

Use the exact download token and configuration commands shown by GitHub for your repository. A typical flow looks like this:

```powershell
mkdir C:\actions-runner\careerpilot
cd C:\actions-runner\careerpilot

# Download and extract the runner package using the commands shown by GitHub.

.\config.cmd --url https://github.com/<owner>/<repo> --token <token>
.\svc install
.\svc start
```

## Trigger behavior

- If someone opens or updates a PR, GitHub will create a workflow run automatically.
- If this computer is online and the runner service is healthy, the job runs here.
- If this computer is sleeping or shut down, the job cannot start until the machine is awake again.
- You can manually trigger the workflow later from the repository `Actions` page by opening `CI` and clicking `Run workflow`.
- Queued jobs on self-hosted runners do not wait forever. If the runner stays offline too long, the queued run will fail and you need to trigger it again manually.

## Operational notes

- To receive PR jobs reliably, change Windows power settings so the machine does not sleep while you expect jobs to arrive.
- If you reboot the machine, make sure the `actions.runner.*` Windows service returns to the `Running` state.
- If the runner shows `Offline` in GitHub, restart the Windows service on this machine.

## Security warning

Running pull requests on a self-hosted runner means workflow code executes on your own computer. Do this only for private repositories or for contributors you trust. Do not expose a personal machine to untrusted public PRs.
